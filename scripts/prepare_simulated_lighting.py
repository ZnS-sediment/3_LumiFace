#!/usr/bin/env python3
"""Deterministic, identity-preserving illumination simulations from existing photos.
No generated faces, no real-capture claims. Source photos split BEFORE augmentation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCENES = ["normal", "low_light", "backlight", "pseudo_infrared"]
LABELS = {
    "normal": "原始基线（统一尺寸）",
    "low_light": "模拟低照度",
    "backlight": "模拟强逆光",
    "pseudo_infrared": "模拟灰度补光（非真实红外）",
}


def simulate(image: np.ndarray, scene: str, seed: int) -> np.ndarray:
    """Approximate exposure, spatial light fields, sensor grain and glare; no feature synthesis."""
    if scene == "normal":
        return image.copy()
    rng = np.random.default_rng(seed)
    h, w = image.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x = (xx - w * 0.5) / (w * 0.5)
    y = (yy - h * 0.49) / (h * 0.5)
    radius = x * x + y * y
    linear = (image.astype(np.float32) / 255) ** 2.2
    side = float(rng.choice([-1, 1]))
    phase = float(rng.uniform(-0.2, 0.2))
    if scene == "low_light":
        exposure = float(rng.uniform(0.12, 0.23))
        shadow = 0.57 + 0.43 / (1 + np.exp(-4 * (side * x + phase)))
        light = exposure * shadow * np.clip(1 - 0.22 * radius, 0.35, 1)
        linear = linear * light[:, :, None]
        photons = 360.0
        read_noise = 0.0015
        blur = 0.32
    elif scene == "backlight":
        # Approximate exposure compensation plus broad optical glare; retain every face pixel's structure.
        shadow = 0.50 + 0.50 / (1 + np.exp(-4 * (side * x + phase)))
        linear = linear * float(rng.uniform(0.23, 0.36)) * shadow[:, :, None]
        flare = 0.42 * np.exp(-((x - side * 1.02) ** 2 / 0.16 + (y + 0.9) ** 2 / 0.34))
        flare += 0.025 * np.exp(-((x - side * 0.45) ** 2 + (y + 0.3) ** 2) / 0.8)
        linear = np.clip(linear + flare[:, :, None], 0, 1)
        photons = 1800.0
        read_noise = 0.0006
        blur = 0.28
    elif scene == "pseudo_infrared":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        spotlight = np.exp(-((x + 0.06) ** 2 / 0.8 + (y + 0.02) ** 2 / 1.15))
        linear = (gray**2.2 * (0.34 + 0.82 * spotlight))[:, :, None]
        linear = np.repeat(linear, 3, axis=2)
        photons = 1000.0
        read_noise = 0.0010
        blur = 0.42
    else:
        raise ValueError("Unknown scene")
    # Grayscale AT&T inputs: share the stochastic sensor field across channels.
    gray = linear.mean(axis=2)
    noisy = rng.poisson(np.clip(gray, 0, 1) * photons) / photons + rng.normal(0, read_noise, (h, w))
    encoded = np.clip(noisy, 0, 1) ** (1 / 2.2)
    result = np.repeat(np.rint(encoded[:, :, None] * 255).astype(np.uint8), 3, axis=2)
    return cv2.GaussianBlur(result, (0, 0), blur)


def seed_for(subject: str, filename: str, scene: str) -> int:
    return int(
        hashlib.sha256(f"lumiface-sim-v1/{subject}/{filename}/{scene}".encode()).hexdigest()[:8], 16
    )


def save(path: Path, image: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, blob = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encode failed")
    data = blob.tobytes()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def zip_paths(archive: Path, base: Path, files: list[Path], prefix: str = "") -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for p in files:
            bundle.write(p, prefix + str(p.relative_to(base)))
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("ZIP validation failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if args.api not in ("http://127.0.0.1:8000", "http://localhost:8000"):
        raise ValueError("Use the local application API")
    source = ROOT / "datasets/att_faces_demo"
    out = ROOT / "datasets/att_lighting_simulation"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    subjects = sorted(p.name for p in (source / "gallery").iterdir() if p.is_dir())
    assert len(subjects) == 40
    for subject in subjects:
        for path in sorted((source / "gallery" / subject).glob("*.png")):
            destination = out / "gallery" / subject / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        for path in sorted((source / "query" / subject).glob("*.png")):
            original = cv2.imread(str(path))
            assert original is not None
            original = cv2.resize(
                original[64:-64, 64:-64], (184, 224), interpolation=cv2.INTER_CUBIC
            )
            original = cv2.copyMakeBorder(
                original, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=(100, 100, 100)
            )
            role = "calibration" if int(path.stem) <= 5 else "test"
            original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            for scene in SCENES:
                target = out / "query" / scene / subject / path.name
                seed = seed_for(subject, path.name, scene)
                digest = save(target, simulate(original, scene, seed))
                records.append(
                    {
                        "file": str(target.relative_to(out)),
                        "subject": subject,
                        "source": str(path.relative_to(source)),
                        "source_sha256": original_hash,
                        "sha256": digest,
                        "scene": scene,
                        "role": role,
                        "seed": seed,
                        "width": original.shape[1],
                        "height": original.shape[0],
                    }
                )
    # Unknown examples have different source identities for calibration and test.
    for role, name in [("calibration", "astronaut"), ("test", "hopper")]:
        src = ROOT / f"work/{name}.png"
        original = cv2.imread(str(src))
        assert original is not None
        original = cv2.resize(original, (220, 240), interpolation=cv2.INTER_AREA)
        for scene in SCENES:
            target = out / "unknown" / role / scene / (name + ".png")
            seed = seed_for(name, "unknown", scene)
            digest = save(target, simulate(original, scene, seed))
            records.append(
                {
                    "file": str(target.relative_to(out)),
                    "subject": "public-" + name,
                    "source": str(src.relative_to(ROOT)),
                    "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                    "sha256": digest,
                    "scene": scene,
                    "role": role,
                    "seed": seed,
                    "unknown": True,
                    "width": original.shape[1],
                    "height": original.shape[0],
                }
            )
    protocol = {
        "name": "AT&T 模拟复杂光照压力测试 v1",
        "real_capture": False,
        "scenes": LABELS,
        "identities": 40,
        "gallery_images": 120,
        "query_images": 1120,
        "unknown_images": 8,
        "source": "AT&T Laboratories Cambridge; public astronaut/Hopper functional samples",
        "source_url": "https://www.cl.cam.ac.uk/research/dtg/attarchive/facedatabase.html",
        "attribution": "AT&T Laboratories Cambridge",
        "split": "gallery source files 01-03; calibration 04-05; test 06-10; all descendants of one source stay in one role",
        "unknown_split": "public-astronaut calibration; public-hopper test; one source identity per unknown split, inadequate for FAR certification",
        "capture_independence": "source_image_disjoint; independent acquisition sessions not established",
        "query_canvas": "AT&T 92x112 face crop enlarged 2x with bicubic interpolation and 20px fixed context; identical geometry for every scene",
        "numpy_version": np.__version__,
        "opencv_version": cv2.__version__,
        "localization_protocol": "single_face_presence; image extent in bbox is an unused schema placeholder, not manual face boxes",
        "limitations": [
            "Software simulations, not actual low-light/backlight/NIR acquisitions",
            "AT&T is already grayscale; pseudo_infrared does not reproduce spectral response",
            "Multiple simulated scenes derived from a source image are correlated",
            "Cannot verify real-world 95%/90%/95% targets",
        ],
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "images": records,
    }
    (out / "protocol-frozen.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2))
    (out / "README.zh-CN.md").write_text(
        "AT&T 模拟复杂光照演示包\\n\\n本包为软件生成的模拟光照，不是真实特殊光照采集，也不是真实红外。人脸内容来自原始照片，未使用 AI 重画人脸。\\n\\nWindows 解压后，批量身份导入只选择 gallery。已有同名身份会跳过。身份确认时从 query/normal、low_light、backlight、pseudo_infrared 中选同一人员照片，身份标签仍是 ATT_s01–ATT_s40。\\n\\n例如 query/low_light/ATT_s01/06.png 和 query/backlight/ATT_s01/06.png 均属于 ATT_s01。请比较原图与算法处理后图像，不保证任何方法总能成功。\\n\\n图库为原文件 01–03，校准为 04–05，测试为 06–10，同源变体不跨划分。已有研究统计与真实实景验收结果不会被此包覆盖。只有两个公开未知样例来源，不能据此宣称可靠 FAR 保证。\\n\\n来源致谢 AT&T Laboratories Cambridge。细节、随机种子、参数及摘要见 protocol-frozen.json。\\n".replace(
            "\\n", "\n"
        )
    )
    files = [
        p for p in out.rglob("*") if p.is_file() and "evaluation" not in p.relative_to(out).parts
    ]
    zip_paths(ROOT / "datasets/att_lighting_simulation.zip", out, files, "att_lighting_simulation/")
    try:
        with urllib.request.urlopen(args.api + "/api/person", timeout=5) as response:
            people = json.load(response)["data"]
        ids = {p["name"]: p["id"] for p in people}
        if any(subject not in ids for subject in subjects):
            raise ValueError("Import gallery before creating evaluation packages")
    except Exception as exc:
        print("演示包已生成；未导出实验清单：", exc)
        return
    evaluation = out / "evaluation"
    evaluation.mkdir(exist_ok=True)
    for old in evaluation.glob("*.zip"):
        old.unlink()
    (evaluation / "person-ids.json").write_text(
        json.dumps({s: ids[s] for s in subjects}, ensure_ascii=False, indent=2)
    )
    for role in ["calibration", "test"]:
        selected = [r for r in records if r["role"] == role]
        parts = max(1, (len(selected) + 499) // 500)
        for part in range(1, parts + 1):
            chunk = selected[part - 1 :: parts]
            manifest = {
                "name": f"AT&T 模拟光照 {role} {part}（非实景）",
                "split": role,
                "source": "AT&T source photos + deterministic software illumination v1",
                "license": "AT&T Laboratories Cambridge attribution; functional example upstream terms preserved in project docs",
                "real_capture": False,
                "localization_protocol": "single_face_presence",
                "protocol": {
                    "name": "模拟光照；同源图像不跨划分；非实景验收",
                    "capture_independence": "unknown",
                },
                "items": [],
            }
            for row in chunk:
                scene = "infrared" if row["scene"] == "pseudo_infrared" else row["scene"]
                manifest["items"].append(
                    {
                        "file": row["file"],
                        "scene": scene,
                        "capture_id": f"simulation-{role}-{row['subject']}-{Path(row['source']).stem}",
                        "faces": [
                            {
                                "subject": row["subject"],
                                "person_id": None if row.get("unknown") else ids[row["subject"]],
                                "bbox": [0, 0, row["width"], row["height"]],
                            }
                        ],
                    }
                )
            dest = evaluation / f"{role}-{part}.zip"
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
                for row in chunk:
                    bundle.write(out / row["file"], row["file"])
            with zipfile.ZipFile(dest) as bundle:
                assert bundle.testzip() is None
    print(
        json.dumps(
            {
                "identities": 40,
                "gallery": 120,
                "queries": 1120,
                "unknown_images": 8,
                "main_zip": str(ROOT / "datasets/att_lighting_simulation.zip"),
                "evaluation_packages": [p.name for p in evaluation.glob("*.zip")],
                "real_capture": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
