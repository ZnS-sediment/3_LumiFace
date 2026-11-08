#!/usr/bin/env python3
"""Fetch required official InsightFace weights; keep research provenance and hashes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ.get('LUMIFACE_MODELS', str(ROOT / 'runtime/insightface'))) / 'models'
PACKS = {
    'buffalo_l': {'det_10g.onnx', 'w600k_r50.onnx'},
    'antelopev2': {'glintr100.onnx'},
}
R100_SHA256 = '4ab1d6435d639628a6f3e5008dd4f929edf4c4124b1a7169e1048f9fef534cdf'


def download(url: str, destination: Path) -> None:
    """Bounded ranged requests avoid stalled long CDN transfers; validate every range."""
    with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30) as response:
        final_url = response.url
        size = int(response.headers.get('Content-Length', '0'))
        ranges = response.headers.get('Accept-Ranges') == 'bytes'
    if not ranges or size <= 0:
        with urllib.request.urlopen(url, timeout=60) as source, destination.open('wb') as dest:
            shutil.copyfileobj(source, dest)
        return
    step = 1024 * 1024
    with tempfile.TemporaryDirectory(dir=destination.parent) as parts:
        def fetch(start):
            end = min(size - 1, start + step - 1)
            for attempt in range(3):
                try:
                    request = urllib.request.Request(final_url, headers={'Range': f'bytes={start}-{end}'})
                    with urllib.request.urlopen(request, timeout=30) as response:
                        if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                            raise ValueError('Model server returned an invalid byte range')
                        data = response.read(end - start + 2)
                        if len(data) != end - start + 1:
                            raise ValueError('Incomplete model download')
                    (Path(parts) / str(start)).write_bytes(data)
                    return
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(1)
        starts = list(range(0, size, step))
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(fetch, start) for start in starts]
            for index, future in enumerate(as_completed(futures), 1):
                future.result()
                if index % 64 == 0:
                    print(f'Downloaded {index}/{len(starts)} chunks', flush=True)
        with destination.open('wb') as output:
            for start in starts:
                output.write((Path(parts) / str(start)).read_bytes())


def main() -> None:
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    for pack, required in PACKS.items():
        target = MODEL_ROOT / pack
        if all((target / name).is_file() for name in required):
            if pack != 'antelopev2' or hashlib.sha256((target / 'glintr100.onnx').read_bytes()).hexdigest() == R100_SHA256:
                print(f'Models already present: {target}')
                continue
        print(f'Downloading official {pack} weights (non-commercial research only).', flush=True)
        with tempfile.TemporaryDirectory(dir=MODEL_ROOT) as directory:
            archive = Path(directory) / 'pack.zip'
            source = ''
            for tag in ['model-zoo', 'v0.7']:
                url = f'https://github.com/deepinsight/insightface/releases/download/{tag}/{pack}.zip'
                try:
                    download(url, archive)
                    source = url
                    break
                except Exception as exc:
                    print(f'Download failed: {type(exc).__name__}: {exc}', flush=True)
            if not source:
                raise SystemExit('Official model download failed. No substitute model was installed.')
            staged = Path(directory) / 'ready'
            staged.mkdir()
            with zipfile.ZipFile(archive) as package:
                for name in required:
                    entries = [x for x in package.infolist() if Path(x.filename).name == name]
                    if len(entries) != 1 or entries[0].file_size > 500 * 1024 * 1024:
                        raise SystemExit(f'Missing or invalid model: {name}')
                    with package.open(entries[0]) as src, (staged / name).open('wb') as dest:
                        shutil.copyfileobj(src, dest)
            hashes = {name: hashlib.sha256((staged / name).read_bytes()).hexdigest() for name in sorted(required)}
            if pack == 'antelopev2' and hashes['glintr100.onnx'] != R100_SHA256:
                raise SystemExit('Candidate recognition model checksum does not match the validated version')
            (staged / 'source.json').write_text(json.dumps({'source': source, 'sha256': hashes, 'license': 'non-commercial research only'}, indent=2))
            target.mkdir(exist_ok=True)
            for path in staged.iterdir():
                shutil.move(str(path), str(target / path.name))
            print(json.dumps({'directory': str(target), 'sha256': hashes}, indent=2))


if __name__ == '__main__':
    main()
