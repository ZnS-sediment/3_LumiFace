#!/usr/bin/env python3
"""Explicit synthetic fixtures for browser integration, separate from real datasets."""

import json
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
probe = cv2.convertScaleAbs(image, alpha=0.85)
person_id = int(os.environ.get("LUMIFACE_TEST_PERSON_ID", "1"))
if person_id < 1:
    raise ValueError("LUMIFACE_TEST_PERSON_ID must be a positive registered identity ID")
manifest = {
    "name": "浏览器流程验证数据",
    "split": "test",
    "source": "scikit-image astronaut derivative, integration only",
    "license": "NASA public domain sample",
    "real_capture": False,
    "items": [
        {
            "file": "test.png",
            "scene": "normal",
            "capture_id": "browser-synthetic-derivative",
            "faces": [
                {"bbox": [175, 55, 277, 185], "person_id": person_id, "subject": "reference-A"}
            ],
        }
    ],
}
with zipfile.ZipFile(WORK / "browser-dataset.zip", "w") as archive:
    archive.writestr("manifest.json", json.dumps(manifest))
    archive.writestr("test.png", cv2.imencode(".png", probe)[1].tobytes())

# Real-model browser batch-import fixtures, confined to the test namespace.
batch = WORK / "browser-batch-identities"
for name in ["浏览器测试参考身份", "批量导入参考B", "批量导入无脸"]:
    (batch / name).mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(batch / "浏览器测试参考身份/ref.png"), image)
cv2.imwrite(str(batch / "批量导入参考B/ref.png"), hopper)
cv2.imwrite(str(batch / "批量导入参考B/ref2.png"), cv2.convertScaleAbs(hopper, alpha=0.9))
import numpy as np

cv2.imwrite(str(batch / "批量导入无脸/ref.png"), np.zeros((64, 64, 3), dtype=np.uint8))
invalid_batch = WORK / "browser-batch-invalid" / "照片过多"
invalid_batch.mkdir(parents=True, exist_ok=True)
for index in range(11):
    cv2.imwrite(str(invalid_batch / f"{index:02d}.png"), image)
