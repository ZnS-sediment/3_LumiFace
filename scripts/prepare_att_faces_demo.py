#!/usr/bin/env python3
"""Download the official AT&T/ORL archive and prepare labeled PNG folders.
Original face pixels are retained; identical 64px neutral context supports SCRFD.
This is a local functional demo, not an independent field-performance benchmark.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.cl.cam.ac.uk/research/dtg/attarchive/facedatabase.html"
DOWNLOAD = "https://www.cl.cam.ac.uk/Research/DTG/attarchive/pub/data/att_faces.zip"
SHA256 = "509d763bd2276aa054d260d7f1000e8be212738134f2f83d8ff13bc2adf1c8ec"


def prepare(raw: Path, destination: Path):
    raw.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive = raw / "att_faces.zip"
    if not archive.exists():
        with urllib.request.urlopen(DOWNLOAD, timeout=60) as response:
            data = response.read(10 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError("Official archive digest changed; stop and inspect source")
        archive.write_bytes(data)
        archive.chmod(0o600)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Archive digest mismatch")
    if not (raw / "source-page.html").exists():
        with urllib.request.urlopen(SOURCE, timeout=30) as response:
            (raw / "source-page.html").write_bytes(response.read())
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    index = []
    with zipfile.ZipFile(archive) as package:
        originals = [name for name in package.namelist() if name.endswith(".pgm")]
        assert len(originals) == 400
        for subject in range(1, 41):
            identity = f"ATT_s{subject:02d}"
            for number in range(1, 11):
                member = f"s{subject}/{number}.pgm"
                image = Image.open(io.BytesIO(package.read(member))).convert("L")
                assert image.size == (92, 112)
                # Fixed before query inference; no generated faces, relabeling or score-based exclusions.
                prepared = ImageOps.expand(image, border=64, fill=128)
                split = "gallery" if number <= 3 else "query"
                path = destination / split / identity / f"{number:02d}.png"
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                prepared.save(path)
                path.chmod(0o600)
                index.append(
                    {
                        "identity": identity,
                        "source_subject": f"s{subject}",
                        "source_file": member,
                        "split": split,
                        "file": path.relative_to(destination).as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
    with (destination / "identities.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["identity", "source_subject", "reference_photos", "query_photos"])
        for subject in range(1, 41):
            writer.writerow([f"ATT_s{subject:02d}", f"s{subject}", 3, 7])
    provenance = {
        "dataset": "AT&T / ORL Database of Faces",
        "source": SOURCE,
        "download": DOWNLOAD,
        "archive_sha256": SHA256,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "identities": 40,
        "original_images": 400,
        "gallery_images": 120,
        "query_images": 280,
        "identity_labels": "anonymous subject IDs, not real names",
        "attribution": "AT&T Laboratories Cambridge",
        "preprocessing": {
            "format": "PNG L8",
            "source_size": [92, 112],
            "border_pixels": 64,
            "border_gray": 128,
            "prepared_size": [220, 240],
            "face_pixels": "unchanged",
        },
        "split_rule": "original filenames 1..3 gallery; 4..10 query, fixed without query-model tuning",
        "capture_independence": "unknown; disjoint filenames do not prove independent acquisition sessions",
        "purpose": "local teaching / import / recognition functional demo; not 95/90/95 field evidence",
        "files": index,
    }
    (destination / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2)
    )
    (destination / "README.zh-CN.md").write_text(
        """# AT&T / ORL 人脸身份演示集

来源："""
        + SOURCE
        + """
致谢：AT&T Laboratories Cambridge。原始归档与来源页保留在 datasets/raw/att-faces。

40 个匿名身份，每人 10 张，共 400 张原始照片。ATT_s01–ATT_s40 对应源标签 s1–s40；不是真实姓名。

- gallery：40 人 × 每人 3 张，共 120 张；网页“身份库管理 → 批量导入身份”选择这个 gallery 文件夹。
- query：40 人 × 每人 7 张，共 280 张；注册后用对应身份的查询照片演示身份确认。不要把 query 文件夹也作为注册参考导入。
- identities.csv：身份编号与照片数量；provenance.json：原始路径、处理方法及逐文件摘要。

网页步骤：选择 gallery → 预览 40 人/120 张 → 数据批次填 att-demo-gallery → 开始导入 → 下载逐人结果。
如同名身份已存在则跳过；有无人脸/多人脸等失败会显示真实原因，不保证每张图一定通过。

原始 PGM 为 92×112 紧裁剪灰度图，直接输入当前检测器可能漏检。这里无损转 PNG，并在每张四周统一添加 64 像素灰度 128 的背景，得到 220×240；人脸区域没有生成、增强或重绘。预处理在任何查询推理前固定，只用于输入适配，不代表更多真实采集样本。

这是不同文件的功能演示划分，原始独立会话未核实，不能据此证明现场准确率。图库全部导入后，40 人都属于已知人员；未知拒识请使用其他未注册人员照片，例如项目 work/hopper.png。

资料页要求使用时注明 AT&T Laboratories Cambridge。本文件保留出处与致谢，不为人员编造姓名，不把此数据集称作本项目自行采集的数据。
"""
    )
    print(
        json.dumps(
            {
                k: provenance[k]
                for k in [
                    "dataset",
                    "identities",
                    "gallery_images",
                    "query_images",
                    "archive_sha256",
                ]
            },
            ensure_ascii=False,
        )
    )
    print("Dataset directory:", destination.resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/att_faces_demo")
    args = parser.parse_args()
    prepare(ROOT / "datasets/raw/att-faces", args.output)
