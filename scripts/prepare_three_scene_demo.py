#!/usr/bin/env python3
"""Build a clearly labelled teaching pack directly from preserved source ZIPs."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "att_lighting_three_scenes/"
SCENES = {
    "backlight": ("01_逆光_CLAHE", "CLAHE（逆光）"),
    "uneven": ("02_光照不均_Retinex", "Retinex（光照不均）"),
    "low_light": ("03_低照度_Gamma", "Gamma 校正（低照度）"),
}


def uneven_light(image: np.ndarray, seed: int) -> np.ndarray:
    """Simulate broad side lighting; keep identity, pose and geometry unchanged."""
    rng = np.random.default_rng(seed)
    height, width = image.shape[:2]
    yy, xx = np.mgrid[-1 : 1 : complex(height), -1 : 1 : complex(width)]
    side = rng.choice([-1, 1])
    field = side * xx + 0.18 * yy - rng.uniform(-0.12, 0.12)
    gain = 0.035 + 1.065 / (1 + np.exp(-5.5 * field))
    linear = (image.astype(np.float32) / 255) ** 2.2
    output = np.clip(linear * gain[:, :, None], 0, 1) ** (1 / 2.2)
    return np.rint(output * 255).astype(np.uint8)


def decode(raw: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid source PNG")
    return image


def encode(image: np.ndarray) -> bytes:
    ok, blob = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encoding failed")
    return blob.tobytes()


def seed_for(identity: str, filename: str) -> int:
    key = f"lumiface-three-scenes-v1/uneven/{identity}/{filename}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def preview(images: dict) -> bytes:
    chinese_font = Path("/mnt/c/Windows/Fonts/msyh.ttc")
    font = (
        ImageFont.truetype(str(chinese_font), 18)
        if chinese_font.exists()
        else ImageFont.load_default()
    )
    labels = ["正常光照（对照）", "逆光 · CLAHE", "光照不均 · Retinex", "低照度 · Gamma"]
    if not chinese_font.exists():
        labels = ["Normal", "Backlight / CLAHE", "Uneven / Retinex", "Low light / Gamma"]
    canvas = Image.new("RGB", (1000, 680), "white")
    draw = ImageDraw.Draw(canvas)
    for row, identity in enumerate(["ATT_s01", "ATT_s05"]):
        for col, scene in enumerate(["normal", *SCENES]):
            x, y = col * 250 + 13, row * 330 + 15
            draw.text((x, y), labels[col], fill="#243447", font=font)
            draw.text((x, y + 26), f"{identity} / 06.png", fill="#526071", font=font)
            canvas.paste(
                Image.open(io.BytesIO(images[identity, scene])).convert("RGB"), (x, y + 58)
            )
    stream = io.BytesIO()
    canvas.save(stream, "PNG")
    return stream.getvalue()


def build(source: Path, old_simulation: Path, output: Path) -> dict:
    if output.resolve() in {source.resolve(), old_simulation.resolve()}:
        raise ValueError("Output must not overwrite either preserved source archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_suffix(".partial.zip")
    records, pictures = [], {}
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def write(bundle: zipfile.ZipFile, name: str, raw: bytes) -> None:
        info = zipfile.ZipInfo(PREFIX + name, date_time=(2026, 10, 19, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100600 << 16
        bundle.writestr(info, raw)

    try:
        with zipfile.ZipFile(source) as originals, zipfile.ZipFile(old_simulation) as old:
            with zipfile.ZipFile(staged, "w") as bundle:
                for subject in range(1, 41):
                    identity = f"ATT_s{subject:02d}"
                    for index in range(1, 4):
                        path = f"gallery/{identity}/{index:02d}.png"
                        write(bundle, path, originals.read("att_faces_demo/" + path))
                    for index in range(4, 11):
                        filename = f"{index:02d}.png"
                        baseline = old.read(
                            f"att_lighting_simulation/query/normal/{identity}/{filename}"
                        )
                        normal = decode(baseline)
                        write(bundle, f"reference/正常光照/{identity}/{filename}", baseline)
                        if identity in {"ATT_s01", "ATT_s05"} and index == 6:
                            pictures[identity, "normal"] = baseline
                        for scene, (folder, algorithm) in SCENES.items():
                            seed = seed_for(identity, filename) if scene == "uneven" else None
                            raw = (
                                encode(uneven_light(normal, seed))
                                if scene == "uneven"
                                else old.read(
                                    f"att_lighting_simulation/query/{scene}/{identity}/{filename}"
                                )
                            )
                            path = f"query/{folder}/{identity}/{filename}"
                            write(bundle, path, raw)
                            records.append(
                                {
                                    "file": path,
                                    "identity": identity,
                                    "scene": scene,
                                    "recommended_method": algorithm,
                                    "seed": seed,
                                    "source_file": f"query/{identity}/{filename}",
                                    "role": "calibration" if index <= 5 else "test",
                                    "sha256": hashlib.sha256(raw).hexdigest(),
                                }
                            )
                            if identity in {"ATT_s01", "ATT_s05"} and index == 6:
                                pictures[identity, scene] = raw
                for role, name in [("calibration", "astronaut"), ("test", "hopper")]:
                    baseline = old.read(f"att_lighting_simulation/unknown/{role}/normal/{name}.png")
                    for scene, (folder, _) in SCENES.items():
                        raw = (
                            encode(uneven_light(decode(baseline), seed_for(name, "unknown")))
                            if scene == "uneven"
                            else old.read(
                                f"att_lighting_simulation/unknown/{role}/{scene}/{name}.png"
                            )
                        )
                        write(bundle, f"unknown/{folder}/{role}/{name}.png", raw)
                protocol = {
                    "version": "three-scenes-v1",
                    "real_capture": False,
                    "identities": 40,
                    "gallery_images": 120,
                    "query_images": 840,
                    "normal_reference_images": 280,
                    "unknown_images": 6,
                    "scene_folders": {scene: folder for scene, (folder, _) in SCENES.items()},
                    "source_archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "previous_simulation_sha256": hashlib.sha256(
                        old_simulation.read_bytes()
                    ).hexdigest(),
                    "generator_sha256": script_hash,
                    "notes": [
                        "Simulation inputs, not enhanced outputs or real scene acquisitions",
                        "Gallery is byte-identical to original reference photos",
                        "Low light and backlight are byte-identical to the previous simulation",
                        "Uneven lighting is newly simulated, not renamed pseudo-infrared",
                        "Source 01-03 gallery, 04-05 calibration, 06-10 test; preserve all variants in one split",
                        "Recommended methods are processing suggestions, not score improvement guarantees",
                        "Prior experimental results do not evaluate the new uneven-lighting images",
                    ],
                    "images": records,
                }
                write(
                    bundle,
                    "protocol.json",
                    json.dumps(protocol, ensure_ascii=False, indent=2).encode(),
                )
                readme = """三类模拟光照演示包（40 个匿名身份）

gallery：清晰注册照片，每人 3 张；仅选择此目录批量注册。已有同名身份会跳过，无需删除重建。
query/01_逆光_CLAHE：280 张模拟逆光输入，建议使用 CLAHE。
query/02_光照不均_Retinex：280 张新生成的侧光/阴影输入，建议使用 Retinex。
query/03_低照度_Gamma：280 张模拟暗光输入，建议使用 Gamma 校正。
reference/正常光照：280 张同编号正常对照图，不用于重复注册。
unknown：各类未注册人员示例，astronaut 用于校准，hopper 用于测试。

同一个人、同一个编号可以跨场景对照。例如三个 query 子目录中的 ATT_s05/06.png 是同一源图的不同模拟版本。
先选场景照片，在网页选择括号对应算法，再点击处理；query 是待增强输入，不是已经执行了算法的输出。
文件夹按生成场景标记，网页的自动光照分类是启发式判断，可能给出不同标签。

注册照片保持原样；低照度和逆光图沿用旧版，光照不均由正常图施加平滑方向照明生成，没有重画人脸。
不包含 pseudo_infrared；未把伪红外改名冒充光照不均。
所有特殊光照均为软件模拟，不代表真实采集，也不保证增强后相似度上升。
旧实验报告不包含新生成的光照不均数据，本包不是实验评估页直接导入的标注 ZIP。

来源与致谢：AT&T Laboratories Cambridge。详细来源、处理规则、逐图摘要见 SOURCES.md 与 protocol.json。
"""
                write(bundle, "使用说明.txt", readme.encode("utf-8-sig"))
                write(bundle, "SOURCES.md", old.read("att_lighting_simulation/SOURCES.md"))
                write(bundle, "三类光照对照.png", preview(pictures))
        with zipfile.ZipFile(staged) as bundle:
            if bundle.testzip() is not None:
                raise ValueError("Archive integrity validation failed")
        staged.replace(output)
        return {key: value for key, value in protocol.items() if key != "images"}
    finally:
        staged.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "datasets/att_faces_demo.zip")
    parser.add_argument(
        "--previous", type=Path, default=ROOT / "datasets/att_lighting_simulation.zip"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "datasets/att_lighting_three_scenes.zip"
    )
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.previous, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
