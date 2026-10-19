#!/usr/bin/env python3
"""Acquire public research data; never fetch gated datasets or redistribute photos.
CBSR/OTCBVS: educational and research use with acknowledgment.
Yale mirror: only original Yale B subjects 01..10 are used by the evaluation adapter.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "cbsr-nir": {
        "url": "http://vcipl-okstate.org/pbvs/bench/Data/07/NIR_face_dataset.zip",
        "filename": "CBSR-NIR.zip",
        "size": 369223897,
        "sha256": "066e385ac7469012f9c2574738c6b8bd15dcfcc5085e7eb97148e0b884b9fe53",
        "terms_url": "http://vcipl-okstate.org/pbvs/bench/index.html",
        "description_url": "http://vcipl-okstate.org/pbvs/bench/Data/07/download.html",
        "scope": "Real active NIR; ambient light/night not specified; not proof of night operation.",
        "extras": [
            "http://vcipl-okstate.org/pbvs/bench/Data/07/gallery-groundtruth.txt",
            "http://vcipl-okstate.org/pbvs/bench/Data/07/probe-groundtruth.txt",
        ],
    },
    "yale-b": {
        "url": "https://raw.githubusercontent.com/trokas/ai_primer/master/img/CroppedYale.zip",
        "filename": "CroppedYale.zip",
        "size": 59206862,
        "sha256": "7696c098b298561cd12e52c797b66fca5f864c27a000d7bda6d1b86c1fe91d39",
        "terms_url": "http://cvc.cs.yale.edu/cvc/projects/yalefacesB/yalefacesB.html",
        "description_url": "https://trokas.github.io/ai_primer/SVD.html",
        "scope": "Original Yale B 01..10 only. Controlled illumination stress; near-consecutive captures, not independent sessions; no IR.",
        "extras": [
            "http://cvc.cs.yale.edu/cvc/projects/yalefacesB/no_strobe.html",
            "http://cvc.cs.yale.edu/cvc/projects/yalefacesB/corrupt.html",
        ],
    },
}


def download(
    url: str,
    destination: Path,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    provenance = destination.with_suffix(destination.suffix + ".source.json")
    if destination.exists() and (
        expected_size is None or destination.stat().st_size == expected_size
    ):
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise RuntimeError(f"Pinned SHA-256 mismatch: {destination}")
        if provenance.exists():
            prior = json.loads(provenance.read_text())
            if prior["sha256"] != digest:
                raise RuntimeError(f"Local checksum mismatch: {destination}")
        print(f"Already present: {destination.name} {digest}", flush=True)
        return {"url": url, "bytes": destination.stat().st_size, "sha256": digest}
    partial = destination.with_suffix(destination.suffix + ".part")
    start = time.monotonic()
    total = 0
    hasher = hashlib.sha256()
    next_report = 32 * 1024 * 1024
    request = urllib.request.Request(
        url, headers={"User-Agent": "LumiFace-Academic-Evaluation/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            resolved = response.geturl()
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > 2 * 1024**3:
                    raise RuntimeError("Unexpected data size >2 GiB")
                output.write(block)
                hasher.update(block)
                if total >= next_report:
                    print(
                        f"{destination.name}: {total / 1024**2:.0f} MiB ({time.monotonic() - start:.1f}s)",
                        flush=True,
                    )
                    next_report += 32 * 1024 * 1024
        if expected_size is not None and total != expected_size:
            raise RuntimeError(f"Expected {expected_size} bytes, received {total}")
        if expected_sha256 and hasher.hexdigest() != expected_sha256:
            raise RuntimeError("Downloaded archive differs from the pinned research version")
        partial.chmod(0o600)
        os.replace(partial, destination)
        result = {
            "url": url,
            "resolved_url": resolved,
            "bytes": total,
            "sha256": hasher.hexdigest(),
            "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        provenance.write_text(json.dumps(result, indent=2))
        provenance.chmod(0o600)
        return result
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=SOURCES)
    args = parser.parse_args()
    source = SOURCES[args.dataset]
    folder = ROOT / "datasets" / "raw" / args.dataset
    result = download(source["url"], folder / source["filename"], source["size"], source["sha256"])
    for url in [source["terms_url"], source["description_url"], *source["extras"]]:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        download(url, folder / name)
    (folder / "provenance.json").write_text(
        json.dumps({**source, **result, "redistribute_images": False}, ensure_ascii=False, indent=2)
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
