#!/usr/bin/env python3
"""Freeze a default on development identities; evaluate held-out identities afterwards.

Inputs are actual glintr100 features from benchmark_recognition_backbone.py.
No runtime database, test labels or current request labels influence inference.
"""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work/accuracy-v4'
OUTPUT = ROOT / 'work/auto-threshold/report.json'


def load(name):
    return json.loads((CACHE / name).read_text())


def main():
    gallery = load('r100-independent-gallery.json') + load('r100-package-gallery.json')
    names = [g['name'].removeprefix('LFW_') for g in gallery]
    assert len(names) == len(set(names))
    matrix = np.asarray([g['embedding'] for g in gallery], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1)[:, None]
    unknown_rows = load('r100-unknown.json')['rows']
    unknown_names = sorted({r['person'] for r in unknown_rows}, key=lambda n: hashlib.sha256(n.encode()).hexdigest())
    assert not set(unknown_names) & set(names)
    hashes = {load(f'r100-{part}.json')['model_sha256'] for part in ['development', 'validation', 'package', 'unknown']}
    assert len(hashes) == 1, 'Calibration inputs must use the same recognition weights'
    calibration_unknown = set(unknown_names[:len(unknown_names)//2])

    def scores(rows, unknown=False):
        result = []
        for row in rows:
            for method, field in [('original', 'raw'), ('enhanced', 'enhanced')]:
                decisions = []
                for face in row[field]:
                    vector = np.asarray(face['embedding'], dtype=np.float32)
                    similarities = np.clip(matrix @ (vector / np.linalg.norm(vector)), -1, 1)
                    best = int(similarities.argmax())
                    decisions.append((names[best], float(similarities[best])))
                result.append({'person': row['person'], 'file': row['file'], 'scene': row['scene'], 'method': method,
                    'score': max((s for n, s in decisions if unknown or n == row['person'].removeprefix('LFW_')), default=-1),
                    'unknown': unknown, 'faces': len(decisions)})
        return result

    development = scores(load('r100-development.json')['rows'])
    unknown = scores(unknown_rows, True)
    calibration = development + [r for r in unknown if r['person'] in calibration_unknown]

    def measure(rows, threshold):
        known = [r for r in rows if not r['unknown']]
        unknown = [r for r in rows if r['unknown']]
        correct = sum(r['score'] >= threshold for r in known)
        false_accept = sum(r['score'] >= threshold for r in unknown)
        return {'known': len(known), 'correct': correct, 'unknown': len(unknown), 'false_accept': false_accept,
            'known_accuracy': correct / len(known) if known else None,
            'unknown_far': false_accept / len(unknown) if unknown else None}

    grid = np.arange(0, 1001) / 1000
    objective = []
    for t in grid:
        m = measure(calibration, t)
        objective.append((m['known_accuracy'] + 1 - m['unknown_far']) / 2)
    best = max(objective)
    indices = np.flatnonzero(np.isclose(objective, best, atol=1e-12, rtol=0))
    intervals = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    # Midpoint of widest optimal plateau avoids a boundary fit; larger midpoint breaks ties.
    interval = max(intervals, key=lambda x: (len(x), int(x[-1])))
    threshold = float(grid[int(interval[(len(interval)-1)//2])])
    # Only after freezing the threshold do we open held-out known/query results.
    validation = scores(load('r100-validation.json')['rows']) + [r for r in unknown if r['person'] not in calibration_unknown]
    package = scores(load('r100-package.json')['rows'])
    assert not {r['person'] for r in calibration} & {r['person'] for r in validation}
    report = {'threshold': threshold, 'model': 'glintr100', 'gallery_size': len(names),
        'model_sha256': load('r100-development.json')['model_sha256'],
        'selection': 'Maximum balanced known-image accuracy and unknown rejection on development only; 0.001 grid; midpoint of widest optimal plateau',
        'optimal_interval': [float(grid[interval[0]]), float(grid[interval[-1]])],
        'calibration_unknown_names': sorted(calibration_unknown),
        'validation_unknown_names': sorted(set(unknown_names) - calibration_unknown),
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob('r100-*.json')},
        'limitations': 'Simulated LFW lighting, not real-capture acceptance. Original/enhanced and lighting variants share source photos. Calibration is not universal or gallery-independent; larger galleries require revalidation.',
        'results': {part: {'before': measure(rows, .45), 'after': measure(rows, threshold),
            'groups': {f'{scene}/{method}': measure([r for r in rows if r['scene']==scene and r['method']==method], threshold)
                for scene in sorted({r['scene'] for r in rows}) for method in ['original','enhanced']}}
            for part, rows in [('calibration',calibration), ('held_out',validation), ('existing_package',package)]}}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
