#!/usr/bin/env python3
"""Download the checksum-pinned LFW mirror and package a deterministic 120-person subset."""

import hashlib
import io
import json
import tarfile
import time
import urllib.request
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://s3-eu-west-1.amazonaws.com/pfigshare-u-files/5976015/lfwfunneled.tgz"
SOURCE_PAGE = (
    "https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_lfw_people.html"
)
SOURCE_SHA256 = "b47c8422c8cded889dc5a13418c4bc2abbda121092b3533a83306f90d900100a"
SOURCE_BYTES = 243346528


def single_person_image(raw: bytes) -> bytes:
    """Use the aligned central subject, excluding surrounding news-photo faces."""
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        if image.size != (250, 250):
            raise ValueError("LFW funneled 图片尺寸与固定裁剪协议不符")
        image = ImageOps.expand(image.crop((65, 55, 185, 210)), border=64, fill=(128, 128, 128))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


def download(archive: Path) -> None:
    if archive.is_file():
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == SOURCE_SHA256:
                return
        raise RuntimeError("已有 LFW 原始包摘要不符，未覆盖；请核查该文件")
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(".download")
    chunk_size = 8 * 1024 * 1024
    chunks = range((SOURCE_BYTES + chunk_size - 1) // chunk_size)

    def fetch(index: int) -> tuple[int, bytes]:
        first, last = index * chunk_size, min((index + 1) * chunk_size, SOURCE_BYTES) - 1
        for attempt in range(4):
            try:
                request = urllib.request.Request(SOURCE, headers={"Range": f"bytes={first}-{last}"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = response.read()
                    if (
                        response.status != 206
                        or response.headers.get("Content-Range")
                        != f"bytes {first}-{last}/{SOURCE_BYTES}"
                        or len(data) != last - first + 1
                    ):
                        raise RuntimeError("下载片段不完整")
                    return index, data
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
        raise RuntimeError("下载失败")

    with temporary.open("wb") as stream, ThreadPoolExecutor(max_workers=4) as pool:
        stream.truncate(SOURCE_BYTES)
        for index, data in pool.map(fetch, chunks):
            stream.seek(index * chunk_size)
            stream.write(data)
            print(f"LFW 下载：{index + 1}/{len(chunks)}", flush=True)
    with temporary.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != SOURCE_SHA256:
            raise RuntimeError("LFW 摘要校验失败，未生成演示包")
    temporary.replace(archive)


def prepare(archive: Path, destination: Path, people_limit: int = 120, selected_people: list[str] | None = None) -> dict:
    groups = defaultdict(list)
    with tarfile.open(archive, "r:gz") as source:
        for item in source.getmembers():
            parts = item.name.split("/")
            if item.isfile() and len(parts) == 3 and parts[-1].lower().endswith(".jpg"):
                groups[parts[-2]].append(item)
        eligible = sorted(name for name, images in groups.items() if len(images) >= 5)
        people = eligible[:people_limit] if selected_people is None else sorted(selected_people)
        if len(people) != people_limit or len(set(people)) != people_limit or not set(people) <= set(eligible):
            raise RuntimeError("原始包中符合每人至少 5 张要求的身份数量不足")
        prefix = f"lfw_{people_limit}_demo"
        provenance = []
        staging = destination.with_suffix(".tmp.zip")
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED) as output:
            for name in people:
                for index, item in enumerate(sorted(groups[name], key=lambda item: item.name)[:5]):
                    original = source.extractfile(item).read()
                    content = single_person_image(original)
                    role = "gallery" if index < 2 else "query"
                    path = f"{prefix}/{role}/LFW_{name}/{Path(item.name).stem}.png"
                    output.writestr(path, content)
                    provenance.append(
                        {
                            "file": path,
                            "source_file": item.name,
                            "source_sha256": hashlib.sha256(original).hexdigest(),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    )
            protocol = {
                "dataset": f"LFW funneled, deterministic {people_limit}-person demonstration subset",
                "persons": people_limit,
                "gallery_images": people_limit * 2,
                "query_images": people_limit * 3,
                "selection": f"First {people_limit} eligible names in lexical order; first two files for gallery, next three for query; no query-score filtering. " + ("References checked for exactly one detectable face." if selected_people is not None else "No model-based filtering."),
                "source_url": SOURCE,
                "source_page": SOURCE_PAGE,
                "source_sha256": SOURCE_SHA256,
                "image_transform": {
                    "crop_xyxy": [65, 55, 185, 210],
                    "border": 64,
                    "border_rgb": [128, 128, 128],
                    "output_size": [248, 283],
                    "note": "所有图片固定中心裁剪并加中性边框，保留裁剪区域的人脸像素；排除外围背景人脸，无 AI 改脸；不按查询识别结果选择图片。",
                },
                "limitations": [
                    "不同照片不证明独立采集会话；没有实景照明标签或独立检测框。",
                    "预训练模型可能见过 LFW，该演示结果不代表无污染的泛化性能。",
                    "图片按固定中心区域裁剪并加边框；背景和外围面部区域被裁掉，不能将裁剪适配的结果等同于原始照片性能。",
                    "LFW 来源图片版权属于原权利人，保留数据来源，仅用于本地课程研究演示。",
                ],
            }
            output.writestr(
                f"{prefix}/protocol.json", json.dumps(protocol, ensure_ascii=False, indent=2)
            )
            output.writestr(
                f"{prefix}/provenance.json", json.dumps(provenance, ensure_ascii=False, indent=2)
            )
            output.writestr(
                f"{prefix}/使用说明.txt",
                f"LFW 身份数据：{people_limit} 人、{people_limit * 5} 张照片\n\n"
                f"gallery：{people_limit} 人，每人 2 张，导入身份库。query：每人另外 3 张，供测试使用。\n"
                "固定中心裁剪并加中性边框；不按查询识别结果筛选，不使用 AI 改脸。\n来源："
                + SOURCE_PAGE
                + "\n\n"
                + "\n".join(protocol["limitations"]),
            )
        with zipfile.ZipFile(staging) as output:
            assert output.testzip() is None
        staging.replace(destination)
        return protocol


if __name__ == "__main__":
    archive = ROOT / "datasets/raw/lfw/lfw-funneled.tgz"
    download(archive)
    destination = ROOT / "datasets/lfw_120_demo.zip"
    print(json.dumps(prepare(archive, destination), ensure_ascii=False, indent=2))
    print(destination)
