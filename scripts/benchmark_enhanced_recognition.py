#!/usr/bin/env python3
"""Paired real-model regression on public images with simulated lighting, not field validation.

Does not import the database, change downloaded data, or tune thresholds/weights.
Run from the project root; raw LFW and the existing lighting ZIP must already exist.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/recognition-benchmark.json")
    parser.add_argument("--unknown-subjects", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.unknown_subjects <= 1000:
        parser.error("unknown-subjects must be 1–1000")
    with tempfile.TemporaryDirectory(prefix="lumiface-benchmark-") as storage:
        os.environ["LUMIFACE_DATA"] = storage
        os.environ["LUMIFACE_RECOGNIZER"] = "w600k_r50"
        os.environ["MPLCONFIGDIR"] = str(Path(storage) / "matplotlib")
        import cv2
        import numpy as np
        from app.algorithms.enhancement import enhance
        from app.algorithms.face_detector import engine
        from app.algorithms.face_recognizer import match, unit
        from app.algorithms.recognition import fuse_faces, ENHANCED_WEIGHT, LEGACY_FUSION_POLICY
        from app.schemas.contracts import EnhanceOptions
        from prepare_lfw_lighting import simulate, SCENES

        engine.load()
        methods = {"backlight": "clahe", "uneven": "retinex", "low_light": "gamma"}
        scenes = {folder: scene for scene, folder in SCENES.items()}
        bundle_path = ROOT / "datasets/lfw_120_lighting.zip"
        raw_path = ROOT / "datasets/raw/lfw/lfw-funneled.tgz"
        summaries, results = {}, {}

        def decode(content):
            image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Invalid source image")
            return image

        def gallery(references):
            return [
                {"id": i + 1, "name": name, "embedding": unit(np.mean(vectors, axis=0)).tolist()}
                for i, (name, vectors) in enumerate(sorted(references.items()))
            ]

        def evaluate(part, templates, cases, unknown=False):
            people = {p["name"]: p["id"] for p in templates}
            stats = defaultdict(Counter)
            rows = []
            for index, (name, scene, filename, image) in enumerate(cases):
                raw_faces = engine.infer(image)
                enhanced, _ = enhance(image, EnhanceOptions(method=methods[scene], auto_parameters=True))
                enhanced_faces = engine.infer(enhanced)
                fused = fuse_faces(raw_faces, enhanced_faces, engine.aligned_embeddings(enhanced, raw_faces))
                decisions = {}
                for variant, faces in {
                    "original": raw_faces,
                    "previous_enhancement": enhanced_faces,
                    "aligned_fusion_v2": fused,
                }.items():
                    matches = [match(f["embedding"], templates, .45) for f in faces]
                    accepted = [m for m in matches if m["confirmed"]]
                    correct = not unknown and any(m["person_id"] == people[name] for m in accepted)
                    count = stats[(scene, variant)]
                    count.update(images=1, correct=int(correct), multiple_faces=int(len(faces) > 1))
                    count["false_accept"] += int(unknown and bool(accepted))
                    count["legacy_strict_correct"] += int(correct and len(faces) == 1)
                    decisions[variant] = {"correct": correct, "face_count": len(faces), "matches": matches}
                rows.append({"person": name, "scene": scene, "file": filename, "decisions": decisions})
                if (index + 1) % 60 == 0:
                    print(f"{part}: {index + 1} images", flush=True)
            summary = {}
            for (scene, variant), count in stats.items():
                summary.setdefault(scene, {})[variant] = {
                    **count,
                    "confirmation_rate": None if unknown else count["correct"] / count["images"],
                    "false_accept_rate": count["false_accept"] / count["images"] if unknown else None,
                }
            summaries[part], results[part] = summary, rows

        with zipfile.ZipFile(bundle_path) as bundle:
            references = defaultdict(list)
            for filename in sorted(bundle.namelist()):
                if "/gallery/" in filename and filename.endswith(".png"):
                    faces = engine.infer(decode(bundle.read(filename)))
                    if len(faces) != 1:
                        raise ValueError(f"Reference requires exactly one face: {filename}")
                    references[filename.split("/")[-2]].append(faces[0]["embedding"])
            package_gallery = gallery(references)
            cases = []
            for filename in sorted(bundle.namelist()):
                if "/query/" in filename and filename.endswith(".png"):
                    scene = scenes[filename.split("/")[-3]]
                    if scene in methods:
                        cases.append((filename.split("/")[-2], scene, filename, decode(bundle.read(filename))))
            evaluate("downloaded_package", package_gallery, cases)

        with tarfile.open(raw_path) as archive:
            groups = defaultdict(list)
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith(".jpg"):
                    groups[member.name.split("/")[-2]].append(member)
            eligible = sorted(name for name, items in groups.items() if len(items) >= 5 and "LFW_" + name not in references)
            independent_refs, split_cases, exclusions = {}, defaultdict(list), []

            def simulated_cases(name, members):
                for member in members:
                    original = cv2.cvtColor(decode(archive.extractfile(member).read()), cv2.COLOR_BGR2RGB)
                    seed = int(hashlib.sha256(member.name.encode()).hexdigest()[:8], 16)
                    for scene in methods:
                        image = cv2.cvtColor(simulate(original, scene, seed), cv2.COLOR_RGB2BGR)
                        yield name, scene, member.name, image

            for index, name in enumerate(eligible[:60]):
                members = sorted(groups[name], key=lambda m: m.name)[:5]
                detected = [engine.infer(decode(archive.extractfile(m).read())) for m in members[:2]]
                if any(len(faces) != 1 for faces in detected):
                    exclusions.append({"person": name, "reference_face_counts": [len(f) for f in detected]})
                    continue
                independent_refs[name] = [faces[0]["embedding"] for faces in detected]
                split = "development" if index < 30 else "validation"
                split_cases[split].extend(simulated_cases(name, members[2:]))
            independent_gallery = gallery(independent_refs)
            for split, cases in split_cases.items():
                evaluate(split, independent_gallery, cases)
            excluded_names = set(independent_refs) | {name.removeprefix("LFW_") for name in references}
            unknown_names = sorted(
                (name for name in groups if name not in excluded_names),
                key=lambda name: hashlib.sha256(("unknown-v2:" + name).encode()).hexdigest(),
            )[:args.unknown_subjects]
            unknown_cases = [case for name in unknown_names for case in simulated_cases(name, sorted(groups[name], key=lambda m: m.name)[:1])]
            evaluate("unknown", package_gallery, unknown_cases, unknown=True)

        report = {
            "threshold": .45, "enhanced_weight": ENHANCED_WEIGHT,
            "recognition_policy": LEGACY_FUSION_POLICY,
            "scoring_policy": "image_identity_presence",
            "model": engine.status(),
            "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (bundle_path, raw_path)},
            "independent_gallery_people": len(independent_gallery),
            "excluded_reference_subjects": exclusions,
            "limitation": "Software lighting only; no field target validated. All query failures retained. Additional faces count only by confirmed exact identity. Fixed weight .3 selected on development queries, never tuned on validation/package queries. No threshold calibration claim.",
            "summary": summaries, "results": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "summary": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
