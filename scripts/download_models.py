#!/usr/bin/env python3
"""Fetch only the official InsightFace buffalo_l pack, with safe extraction and hashes."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    Path(os.environ.get("LUMIFACE_MODELS", str(ROOT / "runtime" / "insightface")))
    / "models"
    / "buffalo_l"
)
URLS = [
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
    "https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip",
]
REQUIRED = {"det_10g.onnx", "w600k_r50.onnx"}


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if all((TARGET / name).is_file() for name in REQUIRED):
        print(f"Models already present: {TARGET}")
        return
    print(
        "InsightFace pretrained weights: non-commercial research only. Source: official deepinsight/insightface releases.",
        flush=True,
    )
    with tempfile.TemporaryDirectory(dir=TARGET.parent) as directory:
        archive = Path(directory) / "pack.zip"
        error = None
        source = ""
        for url in URLS:
            try:
                print(f"Downloading {url}", flush=True)
                with (
                    urllib.request.urlopen(url, timeout=60) as response,
                    archive.open("wb") as output,
                ):
                    shutil.copyfileobj(response, output)
                source = url
                break
            except Exception as exc:
                error = exc
                print(f"Download failed: {exc}", flush=True)
        if not source:
            raise SystemExit(
                f"Official model download failed: {error}. No substitute model was installed."
            )
        staged = Path(directory) / "ready"
        staged.mkdir()
        with zipfile.ZipFile(archive) as package:
            for name in REQUIRED:
                entries = [x for x in package.infolist() if Path(x.filename).name == name]
                if len(entries) != 1 or entries[0].file_size > 500 * 1024 * 1024:
                    raise SystemExit(f"Missing or invalid model: {name}")
                with package.open(entries[0]) as src, (staged / name).open("wb") as dest:
                    shutil.copyfileobj(src, dest)
        hashes = {
            name: hashlib.sha256((staged / name).read_bytes()).hexdigest()
            for name in sorted(REQUIRED)
        }
        (staged / "source.json").write_text(
            json.dumps(
                {"source": source, "sha256": hashes, "license": "non-commercial research only"},
                indent=2,
            )
        )
        TARGET.mkdir(exist_ok=True)
        for path in staged.iterdir():
            shutil.move(str(path), str(TARGET / path.name))
        print(json.dumps({"directory": str(TARGET), "sha256": hashes}, indent=2))


if __name__ == "__main__":
    main()
