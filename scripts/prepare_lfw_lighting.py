#!/usr/bin/env python3
"""Package the existing LFW identities with clearly labelled simulated lighting inputs."""

import hashlib
import io
import json
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCENES = {
    "normal": "00_正常光照",
    "backlight": "01_逆光_CLAHE",
    "uneven": "02_光照不均_Retinex",
    "low_light": "03_低照度_Gamma",
}


def simulate(image: np.ndarray, scene: str, seed: int) -> np.ndarray:
    if scene == "normal":
        return image.copy()
    height, width = image.shape[:2]
    yy, xx = np.mgrid[:height, :width].astype(np.float32)
    x = (xx - (width - 1) / 2) / 60
    y = (yy - (height - 1) / 2) / 77.5
    linear = (image.astype(np.float32) / 255) ** 2.2
    if scene == "low_light":
        output = linear * 0.045
    elif scene == "uneven":
        side = 1 if seed % 2 else -1
        gain = 0.025 + 0.975 / (1 + np.exp(np.clip(-6 * side * x, -60, 60)))
        output = linear * gain[:, :, None]
    elif scene == "backlight":
        mask = (1 / (1 + np.exp(np.clip(12 * (np.abs(x) - 1), -60, 60)))) * (
            1 / (1 + np.exp(np.clip(12 * (np.abs(y) - 1), -60, 60)))
        )
        output = linear * (0.12 * mask + 0.6 * (1 - mask))[:, :, None] + 0.65 * (
            1 - mask[:, :, None]
        )
    else:
        raise ValueError("Unknown lighting scene")
    return np.rint(np.clip(output, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


def png(image: np.ndarray) -> bytes:
    output = io.BytesIO()
    Image.fromarray(image).save(output, format="PNG")
    return output.getvalue()


def preview(images: list[list[np.ndarray]]) -> bytes:
    canvas = Image.new("RGB", (1064, 680), "white")
    draw = ImageDraw.Draw(canvas)
    font_path = Path("/mnt/c/Windows/Fonts/msyh.ttc")
    font = (
        ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    )
    labels = (
        ["正常光照", "逆光 · CLAHE", "光照不均 · Retinex", "低照度 · Gamma"]
        if font_path.exists()
        else ["Normal", "Backlight / CLAHE", "Uneven / Retinex", "Low light / Gamma"]
    )
    for row, pictures in enumerate(images):
        for column, image in enumerate(pictures):
            x, y = 14 + column * 266, 12 + row * 330
            draw.text((x, y), labels[column], font=font, fill="#243447")
            canvas.paste(Image.fromarray(image), (x, y + 31))
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def build(source: Path, destination: Path) -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError("Do not overwrite the source download")
    staged = destination.with_suffix(".tmp.zip")
    provenance, examples = [], []
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as output,
    ):
        gallery = [n for n in original.namelist() if "/gallery/" in n and n.endswith(".png")]
        queries = [n for n in original.namelist() if "/query/" in n and n.endswith(".png")]
        identities = {n.split("/")[-2] for n in gallery}
        persons = len(identities)
        from collections import Counter
        if (not persons or Counter(n.split("/")[-2] for n in gallery) != Counter({n: 2 for n in identities})
            or Counter(n.split("/")[-2] for n in queries) != Counter({n: 3 for n in identities})):
            raise ValueError("每个身份必须有 2 张注册图和 3 张独立查询图")
        PREFIX = f"lfw_{persons}_lighting/"
        source_protocol = json.loads(original.read(original.namelist()[0].split("/")[0] + "/protocol.json"))
        for name in sorted(original.namelist()):
            if "/gallery/" in name:
                output.writestr(PREFIX + name.split("/", 1)[1], original.read(name))
        for index, name in enumerate(
            sorted(n for n in original.namelist() if "/query/" in n and n.endswith(".png"))
        ):
            content = original.read(name)
            image = np.array(Image.open(io.BytesIO(content)).convert("RGB"))
            identity, filename = name.split("/")[-2:]
            seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
            pictures = []
            for scene, folder in SCENES.items():
                result = simulate(image, scene, seed)
                raw = content if scene == "normal" else png(result)
                target = f"query/{folder}/{identity}/{filename}"
                output.writestr(PREFIX + target, raw)
                provenance.append(
                    {
                        "file": target,
                        "scene": scene,
                        "source_file": name,
                        "source_sha256": hashlib.sha256(content).hexdigest(),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "simulated": scene != "normal",
                    }
                )
                pictures.append(result)
            if index in (0, 3):
                examples.append(pictures)
        protocol = {
            "persons": persons,
            "gallery_images": len(gallery),
            "query_images_per_scene": len(queries),
            "source_protocol": source_protocol,
            "scenes": SCENES,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "simulation": "Software exposure and spatial lighting fields; no face generation, no geometric warp; all query images retained in every scene",
            "note": "三类特殊光照为软件模拟输入，尚未增强；文件夹中的算法名是处理建议，不保证提高识别率。正常图与三个变体属于同源图片，不可当作独立实景采集或跨校准/测试划分。",
        }
        output.writestr(
            PREFIX + "protocol.json", json.dumps(protocol, ensure_ascii=False, indent=2)
        )
        output.writestr(
            PREFIX + "provenance.json", json.dumps(provenance, ensure_ascii=False, indent=2)
        )
        output.writestr(PREFIX + "光照对照.png", preview(examples))
        output.writestr(
            PREFIX + "使用说明.txt",
            f"LFW 身份与光照数据包：{persons} 人\n\n"
            f"1. gallery：{persons} 人 × 2 张参考图，导入身份库。同名身份会跳过，无需删除旧身份。\n"
            f"2. query：每个场景 {len(queries)} 张，每人 3 张，来源与注册图不同。\n"
            "00_正常光照：原查询图；01_逆光_CLAHE：模拟逆光；02_光照不均_Retinex：模拟侧光阴影；03_低照度_Gamma：模拟暗光。\n"
            "批量测试时选择一个场景目录，不要选择整个 query；确认姓名自动匹配后开始测试。\n"
            "光照变体均为软件模拟、尚未增强，不是实景采集。相同文件名的四种场景属于同源图片，不能当作独立样本。\n"
            "来源、文件校验和裁剪处理见 protocol.json、provenance.json；LFW 图片版权属于原权利人，仅用于本地课程研究演示。\n"
            "本包可能包含用于默认判定参数校准的身份；不得将整包结果称为完全未参与校准的独立性能验证。",

        )
    with zipfile.ZipFile(staged) as output:
        assert output.testzip() is None
    staged.replace(destination)
    return protocol


if __name__ == "__main__":
    print(
        json.dumps(
            build(ROOT / "datasets/lfw_120_demo.zip", ROOT / "datasets/lfw_120_lighting.zip"),
            ensure_ascii=False,
            indent=2,
        )
    )
