#!/usr/bin/env python3
"""Build 400 identities with valid references, retaining every query regardless of score."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from collections import defaultdict
import numpy as np
from PIL import Image
from prepare_lfw_demo import ROOT, SOURCE_SHA256, prepare, single_person_image
from prepare_lfw_lighting import build


def main():
    archive = ROOT / 'datasets/raw/lfw/lfw-funneled.tgz'
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != SOURCE_SHA256:
            raise ValueError('LFW source checksum mismatch')
    work = ROOT / 'work/lfw-400'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lumiface-pack-') as temporary:
        os.environ['LUMIFACE_DATA'] = temporary
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.algorithms.face_detector import engine
        from app.algorithms.face_recognizer import unit
        engine.load()
        cache_path = work / 'references.json'
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {'model_fingerprint': engine.fingerprint, 'people': {}, 'excluded': {}}
        assert cache['model_fingerprint'] == engine.fingerprint
        groups = defaultdict(list)
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                if member.isfile() and member.name.endswith('.jpg'):
                    groups[member.name.split('/')[-2]].append(member)
            for name in sorted(n for n, members in groups.items() if len(members) >= 5):
                if name not in cache['people'] and name not in cache['excluded']:
                    embeddings, counts = [], []
                    for member in sorted(groups[name], key=lambda m: m.name)[:2]:
                        content = single_person_image(source.extractfile(member).read())
                        rgb = np.asarray(Image.open(io.BytesIO(content)).convert('RGB'))
                        faces = engine.infer(rgb[:, :, ::-1].copy())
                        counts.append(len(faces))
                        if len(faces) == 1:
                            embeddings.append(faces[0]['embedding'])
                    if counts == [1, 1]:
                        cache['people'][name] = {'name': 'LFW_' + name, 'embedding': unit(np.mean(embeddings, axis=0)).tolist()}
                    else:
                        cache['excluded'][name] = {'reason': 'Reference must contain exactly one detectable face', 'counts': counts}
                    cache_path.write_text(json.dumps(cache))
                    print('References checked:', len(cache['people']), 'excluded:', len(cache['excluded']), flush=True)
                if len(cache['people']) >= 400:
                    break
        if len(cache['people']) < 400:
            raise RuntimeError('Insufficient valid references; no download replaced')
        people = sorted(cache['people'])[:400]
        base = ROOT / 'datasets/lfw_400_demo.zip'
        prepare(archive, base, 400, people)
        protocol = build(base, ROOT / 'datasets/lfw_400_lighting.zip')
        report = {'protocol': protocol, 'model_fingerprint': engine.fingerprint,
                  'reference_images_checked': len(people) * 2, 'excluded_references': cache['excluded']}
        (work / 'package-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
