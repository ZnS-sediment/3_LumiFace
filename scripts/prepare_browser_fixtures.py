#!/usr/bin/env python3
"""Explicit synthetic fixtures for browser integration, separate from real datasets."""

import os
import zipfile
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
WORK.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(WORK / "matplotlib-cache"))
import matplotlib
from skimage import data

image = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
cv2.imwrite(str(WORK / "astronaut.png"), image)
hopper = cv2.imread(str(Path(matplotlib.get_data_path()) / "sample_data" / "grace_hopper.jpg"))
cv2.imwrite(str(WORK / "hopper.png"), hopper)
# Two real sample photos in one canvas, only for multi-face integration checks.
import numpy as np
group = np.full((650, 1050, 3), 127, np.uint8)
group[:image.shape[0], :image.shape[1]] = image
group[:hopper.shape[0], 530:530 + hopper.shape[1]] = hopper
cv2.imwrite(str(WORK / "browser-group.png"), group)
# Real-model browser batch-import fixtures, confined to the test namespace.
batch = WORK / "browser-batch-identities"
for name in ["浏览器测试参考身份", "批量导入参考B", "批量导入无脸"]:
    (batch / name).mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(batch / "浏览器测试参考身份/ref.png"), image)
cv2.imwrite(str(batch / "批量导入参考B/ref.png"), hopper)
cv2.imwrite(str(batch / "批量导入参考B/ref2.png"), cv2.convertScaleAbs(hopper, alpha=0.9))
cv2.imwrite(str(batch / "批量导入无脸/ref.png"), np.zeros((64, 64, 3), dtype=np.uint8))
invalid_batch = WORK / "browser-batch-invalid" / "照片过多"
invalid_batch.mkdir(parents=True, exist_ok=True)
for index in range(11):
    cv2.imwrite(str(invalid_batch / f"{index:02d}.png"), image)

# Keep integration fixtures on the current LFW data source, independent of retired downloads.
import shutil

multi = WORK / "browser-multi-query"
shutil.rmtree(multi, ignore_errors=True)
with zipfile.ZipFile(ROOT / "datasets/lfw_120_demo.zip") as bundle:
    reference = sorted(n for n in bundle.namelist() if "/gallery/" in n)[0]
    identity = reference.split("/")[-2]
    (WORK / "browser-multi-reference.png").write_bytes(bundle.read(reference))
    folder = multi / "多图测试参考"
    folder.mkdir(parents=True)
    queries = sorted(
        n for n in bundle.namelist() if "/query/" in n and n.split("/")[-2] == identity
    )[:2]
    for index, source in enumerate(queries):
        (folder / f"query{index + 1}.png").write_bytes(bundle.read(source))
    cv2.imwrite(str(folder / "blank.png"), np.zeros((64, 64, 3), dtype=np.uint8))

lighting_query = WORK / "browser-lighting-query"
shutil.rmtree(lighting_query, ignore_errors=True)
with zipfile.ZipFile(ROOT / "datasets/lfw_120_lighting.zip") as bundle:
    for scene in ["01_逆光_CLAHE", "02_光照不均_Retinex", "03_低照度_Gamma"]:
        target = lighting_query / scene / "多图测试参考"
        target.mkdir(parents=True)
        source = "lfw_120_lighting/query/" + scene + "/" + queries[0].split("/query/", 1)[1]
        (target / "query.png").write_bytes(bundle.read(source))
