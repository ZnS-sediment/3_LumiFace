#!/usr/bin/env python3
"""Run the real detector/recognizer on a frozen synthetic-lighting image protocol.
Results are simulations only. Test rows never select generator parameters or thresholds.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
METHODS = ["original", "gamma", "clahe", "retinex", "adaptive"]
TEMPLATES = []
BASE = ROOT / "datasets/att_lighting_simulation"


def initialize(templates):
    global TEMPLATES
    TEMPLATES = templates
    import cv2
    import warnings

    cv2.setNumThreads(1)
    warnings.filterwarnings("ignore", category=FutureWarning)
    from app.algorithms.face_detector import engine

    engine.load()


def infer(job):
    row, method = job
    import cv2
    from app.algorithms.face_detector import engine
    from app.algorithms.face_recognizer import match
    from app.algorithms.enhancement import enhance
    from app.schemas.contracts import EnhanceOptions

    image = cv2.imread(str(BASE / row["file"]))
    start = time.perf_counter()
    processed, steps = enhance(image, EnhanceOptions(method=method))
    faces = engine.infer(processed)
    best = match(faces[0]["embedding"], TEMPLATES, -1) if len(faces) == 1 else None
    return {
        "file": row["file"],
        "subject": row["subject"],
        "scene": row["scene"],
        "unknown": row.get("unknown", False),
        "method": method,
        "truth_person_id": None if row.get("unknown") else int(row["subject"].split("s")[-1]),
        "candidate_id": best["candidates"][0]["person_id"] if best and best["candidates"] else None,
        "score": best["similarity"] if best else None,
        "known": not row.get("unknown", False),
        "detected_faces": len(faces),
        "elapsed_ms": (time.perf_counter() - start) * 1000,
        "steps": steps,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2, choices=[1, 2])
    parser.add_argument("--detector-size", type=int, default=320, choices=[320, 640])
    args = parser.parse_args()
    os.environ["LUMIFACE_DETECTION_SIZE"] = str(args.detector_size)
    from app.algorithms.face_detector import engine
    from app.algorithms.face_recognizer import unit
    from app.algorithms.metrics import calibrate, wilson
    import cv2
    import numpy as np

    cv2.setNumThreads(1)
    out = ROOT / "experiments/results/simulated-att-lighting"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "summary.json").exists():
        raise SystemExit("Completed report already exists; do not silently overwrite it")
    protocol_path = BASE / "protocol-frozen.json"
    protocol = json.loads(protocol_path.read_text())
    frozen = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "real_capture": False,
        "field_validation": False,
        "detector_size": args.detector_size,
        "methods": METHODS,
        "workers": args.workers,
        "generator_protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "benchmark_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "split": protocol["split"],
        "limitations": protocol["limitations"],
        "calibration_target_far": 0.01,
        "localization_protocol": "single_face_presence; no IoU truth",
        "threshold_selection": "calibration images only, per method",
    }
    (out / "protocol-frozen.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2))
    engine.load()
    templates = []
    enrollment = []
    for folder in sorted((BASE / "gallery").iterdir()):
        embeddings = []
        for path in sorted(folder.glob("*.png")):
            faces = engine.infer(cv2.imread(str(path)))
            enrollment.append({"file": str(path.relative_to(BASE)), "faces": len(faces)})
            if len(faces) == 1:
                embeddings.append(unit(faces[0]["embedding"]))
        if embeddings:
            templates.append(
                {
                    "id": int(folder.name.split("s")[-1]),
                    "name": folder.name,
                    "embedding": unit(np.mean(embeddings, axis=0)).tolist(),
                }
            )
    (out / "enrollment.json").write_text(json.dumps(enrollment, ensure_ascii=False, indent=2))
    frozen["model_fingerprint"] = engine.fingerprint
    (out / "protocol-frozen.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2))
    print(
        "Gallery templates", len(templates), "of 40; every query remains in denominator", flush=True
    )
    thresholds = {}
    all_rows = {}
    with ProcessPoolExecutor(
        max_workers=args.workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=initialize,
        initargs=(templates,),
    ) as pool:
        for role in ["calibration", "test"]:
            if role == "test":
                (out / "thresholds-frozen.json").write_text(
                    json.dumps(thresholds, ensure_ascii=False, indent=2)
                )
            selected = [r for r in protocol["images"] if r["role"] == role]
            jobs = [(r, m) for r in selected for m in METHODS]
            rows = []
            with (out / f"{role}-predictions.jsonl").open("w") as log:
                for i, result in enumerate(pool.map(infer, jobs, chunksize=4), 1):
                    rows.append(result)
                    log.write(json.dumps(result, ensure_ascii=False) + "\n")
                    if i % 200 == 0 or i == len(jobs):
                        print(role, i, "/", len(jobs), flush=True)
            all_rows[role] = rows
            if role == "calibration":
                for method in METHODS:
                    thresholds[method] = calibrate([r for r in rows if r["method"] == method], 0.01)
    summary = {}

    def counts(rows, threshold):
        known = [r for r in rows if r["known"]]
        unknown = [r for r in rows if not r["known"]]
        correct = sum(
            r["score"] is not None
            and r["score"] >= threshold
            and r["candidate_id"] == r["truth_person_id"]
            for r in known
        )
        false_accept = sum(r["score"] is not None and r["score"] >= threshold for r in unknown)
        return {
            "known": len(known),
            "correct": correct,
            "confirmation_rate": correct / len(known) if known else None,
            "confirmation_ci95": wilson(correct, len(known)),
            "unknown": len(unknown),
            "false_accept": false_accept,
            "unknown_far": false_accept / len(unknown) if unknown else None,
            "no_single_face": sum(r["detected_faces"] != 1 for r in rows),
            "mean_ms": sum(r["elapsed_ms"] for r in rows) / len(rows) if rows else None,
        }

    for method in METHODS:
        rows = [r for r in all_rows["test"] if r["method"] == method]
        threshold = thresholds[method]["threshold"]
        scenes = {
            scene: counts([r for r in rows if r["scene"] == scene], threshold)
            for scene in ["normal", "low_light", "backlight", "pseudo_infrared"]
        }
        combined = counts([r for r in rows if r["scene"] != "pseudo_infrared"], threshold)
        summary[method] = {
            "threshold": threshold,
            "scenes": scenes,
            "pooled_visible_three_scenes": combined,
            "all_simulated_scenes": counts(rows, threshold),
            "field_targets_status": "未验证：输入为模拟光照，非真实场景采集",
        }
    report = {
        "name": "AT&T 模拟复杂光照压力测试",
        "real_capture": False,
        "field_validation": False,
        "model_fingerprint": engine.fingerprint,
        "gallery_subjects": len(templates),
        "test_known": 800,
        "test_unknown": 4,
        "unknown_test_subjects": 1,
        "calibration_unknown_subjects": 1,
        "limitations": protocol["limitations"]
        + [
            "Only one unknown source subject per split; FAR estimates are not a safety guarantee",
            "Timing is concurrent CPU wall time, not a dedicated-hardware benchmark",
        ],
        "summary": summary,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (out / "results.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "method",
                "scene",
                "correct",
                "known",
                "confirmation_rate",
                "false_accept",
                "unknown",
                "unknown_far",
                "real_capture",
            ]
        )
        for method, group in summary.items():
            for scene, result in group["scenes"].items():
                writer.writerow(
                    [
                        method,
                        scene,
                        result["correct"],
                        result["known"],
                        result["confirmation_rate"],
                        result["false_accept"],
                        result["unknown"],
                        result["unknown_far"],
                        False,
                    ]
                )
    print(
        json.dumps(
            {
                m: {s: round(v["confirmation_rate"], 4) for s, v in group["scenes"].items()}
                for m, group in summary.items()
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
