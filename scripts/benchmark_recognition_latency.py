#!/usr/bin/env python3
"""Paired v2/v3 latency, plus replay of cached real-model features.

Run with OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1. Does not access the DB.
Timing includes enhancement, detection, extraction and matching, excludes IO and
warmup. Each enhanced method is charged the full original inference cost.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-scene', type=int, default=20)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/recognition-latency-v3.json')
    args = parser.parse_args()
    if not 1 <= args.per_scene <= 360:
        parser.error('per-scene must be 1–360')
    with tempfile.TemporaryDirectory(prefix='lumiface-latency-') as temp:
        os.environ['LUMIFACE_DATA'] = temp
        os.environ["LUMIFACE_RECOGNIZER"] = "w600k_r50"
        os.environ['MPLCONFIGDIR'] = temp
        import cv2
        import numpy as np
        from app.algorithms.face_detector import engine
        from app.algorithms.recognition import recognition_faces, PREVIOUS_RECOGNITION_POLICY as RECOGNITION_POLICY, LEGACY_FUSION_POLICY
        from app.algorithms.face_recognizer import match
        from app.algorithms.enhancement import enhance
        from app.schemas.contracts import EnhanceOptions

        cache_root = ROOT / 'work/quality-v2'
        package = json.loads((cache_root / 'package-cache.json').read_text())
        templates = package['gallery']
        methods = {'01_逆光_CLAHE': 'clahe', '02_光照不均_Retinex': 'retinex', '03_低照度_Gamma': 'gamma'}
        report = {'threshold': .45, 'policy': RECOGNITION_POLICY, 'cache_replay': {}, 'timing': {}, 'rows': []}
        report['timing_scope'] = 'Warm, paired runs; IO excluded. Enhanced standalone ms includes original inference even when shared. Batch ms measures original + enhanced together.'
        report['limitations'] = 'Cached real-model replay is equivalence regression, not new field accuracy validation. Live timing is a deterministic evenly-spaced subset, not a full-package latency measurement.'

        # Replay all previously extracted vectors: no new inference and no labels
        # available to either recognition path. No sample filtering by outcome.
        for file in ['independent-cache.json', 'package-cache.json', 'unknown-cache.json']:
            data = json.loads((cache_root / file).read_text())
            gallery = [{**p, 'id': p.get('id', i + 1)} for i, p in enumerate(data.get('gallery', templates))]
            names = {p['name']: p['id'] for p in gallery}
            counts = defaultdict(lambda: {'images': 0, 'correct': 0, 'false_accept': 0, 'changed': 0})
            for row in data['rows']:
                original, enhanced = np.zeros((1, 1, 3), np.uint8), np.ones((1, 1, 3), np.uint8)
                def embeddings(im, faces):
                    result = []
                    for face in faces:
                        source = row['aligned'] if any(face is f for f in row['raw']) else row['enhanced']
                        result.append(next(f['embedding'] for f in source if f['keypoints'] == face['keypoints']))
                    return result
                with patch.object(engine, 'infer', side_effect=lambda im: row['raw'] if im is original else row['enhanced']), patch.object(engine, 'detect_faces', return_value=row['enhanced']), patch.object(engine, 'aligned_embeddings', side_effect=embeddings):
                    old = recognition_faces(original, enhanced, LEGACY_FUSION_POLICY)
                    new = recognition_faces(original, enhanced, RECOGNITION_POLICY)
                assert old == new, (file, row['person'], row['scene'])
                accepted = {m['person_id'] for f in new if (m := match(f['embedding'], gallery, .45))['confirmed']}
                key = row.get('split', 'all') + '/' + row['scene']
                stats = counts[key]
                stats['images'] += 1
                stats['correct'] += int(file != 'unknown-cache.json' and names[row['person']] in accepted)
                stats['false_accept'] += int(file == 'unknown-cache.json' and bool(accepted))
            report['cache_replay'][file] = {'sha256': hashlib.sha256((cache_root / file).read_bytes()).hexdigest(), 'summary': dict(counts)}
            print('Cache replay complete:', file, len(data['rows']), flush=True)

        engine.load()
        def process(image, method, policy, shared=None):
            processed, _ = enhance(image, EnhanceOptions(method=method, auto_parameters=True))
            faces = recognition_faces(image, processed, policy, original_faces=shared)
            return [match(f['embedding'], templates, .45) for f in faces]

        def accepted(matches):
            return [m['person_id'] for m in matches if m['confirmed']]

        def batch(image, method, optimized):
            start = time.perf_counter()
            faces = engine.infer(image)
            raw_ms = (time.perf_counter() - start) * 1000
            raw_matches = [match(f['embedding'], templates, .45) for f in faces]
            original_ms = (time.perf_counter() - start) * 1000
            start_method = time.perf_counter()
            matches = process(image, method, RECOGNITION_POLICY if optimized else LEGACY_FUSION_POLICY, faces if optimized else None)
            method_ms = (time.perf_counter() - start_method) * 1000
            return {'original_ms': original_ms, 'enhanced_ms': method_ms + (raw_ms if optimized else 0),
                    'batch_ms': (time.perf_counter() - start) * 1000,
                    'accepted': accepted(matches), 'raw_accepted': accepted(raw_matches),
                    'face_count': len(matches)}

        with zipfile.ZipFile(ROOT / 'datasets/lfw_120_lighting.zip') as bundle:
            for scene, method in methods.items():
                files = sorted(n for n in bundle.namelist() if '/' + scene + '/' in n and n.endswith('.png'))
                selected = [files[i] for i in np.linspace(0, len(files) - 1, args.per_scene, dtype=int)]
                image = cv2.imdecode(np.frombuffer(bundle.read(selected[0]), np.uint8), 1)
                batch(image, method, False)
                batch(image, method, True)
                rows = []
                for index, name in enumerate(selected):
                    image = cv2.imdecode(np.frombuffer(bundle.read(name), np.uint8), 1)
                    pair = {}
                    for optimized in ([False, True] if index % 2 == 0 else [True, False]):
                        pair['new' if optimized else 'old'] = batch(image, method, optimized)
                    assert pair['old']['accepted'] == pair['new']['accepted'], name
                    assert pair['old']['face_count'] == pair['new']['face_count'], name
                    row = {'file': name, 'method': method, **pair}
                    rows.append(row)
                    report['rows'].append(row)
                report['timing'][method] = {
                    variant: {field: float(np.mean([r[variant][field] for r in rows])) for field in ['original_ms', 'enhanced_ms', 'batch_ms']}
                    for variant in ['old', 'new']
                }
                print(method, json.dumps(report['timing'][method]), flush=True)
        report['model'] = engine.status()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('Saved:', args.output, flush=True)


if __name__ == '__main__':
    main()
