#!/usr/bin/env python3
"""Compare recognition backbones at threshold .45 using fixed SCRFD detections.

Uses existing quality-v2 real-model detections, never the labels for inference.
Reference/query images and photometric transforms are unchanged. Old reference
vectors are not reused for the new encoder. Runtime database is never imported.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parts', nargs='+', choices=['development', 'validation', 'package', 'unknown'],
                        default=['development', 'validation', 'package', 'unknown'])
    parser.add_argument('--model', type=Path, default=ROOT / 'runtime/insightface/models/antelopev2/glintr100.onnx')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/accuracy-v4')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='lumiface-backbone-') as storage:
        os.environ['LUMIFACE_DATA'] = storage
        os.environ['MPLCONFIGDIR'] = storage
        os.environ['NO_ALBUMENTATIONS_UPDATE'] = '1'
        os.environ['LUMIFACE_RECOGNIZER'] = 'w600k_r50'
        import cv2
        import numpy as np
        import onnxruntime as ort
        from insightface.model_zoo.arcface_onnx import ArcFaceONNX
        from insightface.utils.face_align import norm_crop
        from app.algorithms.face_detector import engine
        from app.algorithms.face_recognizer import unit, match
        from app.algorithms.recognition import fuse_faces
        from app.algorithms.enhancement import enhance
        from app.algorithms.metrics import iou
        from app.schemas.contracts import EnhanceOptions
        from prepare_lfw_lighting import simulate

        work, oldroot = args.output_dir, ROOT / 'work/quality-v2'
        work.mkdir(parents=True, exist_ok=True)
        model_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
        from download_models import R100_SHA256
        if model_hash != R100_SHA256:
            raise ValueError('This comparison requires the validated official glintr100 weights')
        opts = ort.SessionOptions()
        opts.intra_op_num_threads, opts.inter_op_num_threads, opts.log_severity_level = 2, 1, 3
        model = ArcFaceONNX(str(args.model), session=ort.InferenceSession(str(args.model), sess_options=opts, providers=['CPUExecutionProvider']))
        cv2.setNumThreads(2)

        def features(image, faces):
            return [unit(v).tolist() for v in model.get_feat([
                norm_crop(image, np.asarray(f['keypoints'], np.float32)) for f in faces
            ])] if faces else []

        def decode(content):
            return cv2.imdecode(np.frombuffer(content, np.uint8), 1)

        ind = json.loads((oldroot / 'independent-cache.json').read_text())
        pkg = json.loads((oldroot / 'package-cache.json').read_text())
        unknown = json.loads((oldroot / 'unknown-cache.json').read_text())
        raw = {}
        people = {r['person'] for r in ind['rows'] + unknown['rows']}
        with tarfile.open(ROOT / 'datasets/raw/lfw/lfw-funneled.tgz', 'r|gz') as tar:
            for member in tar:
                name = member.name.split('/')[-2] if '/' in member.name else ''
                if member.isfile() and name in people and member.name.endswith(tuple(f'_{i:04}.jpg' for i in range(1, 6))):
                    raw[member.name] = tar.extractfile(member).read()
        print('Loaded source bytes', len(raw), flush=True)
        with zipfile.ZipFile(ROOT / 'datasets/lfw_120_lighting.zip') as bundle:
            def gallery(kind):
                target = work / ('r100-' + kind + '-gallery.json')
                if target.exists():
                    return json.loads(target.read_text())
                refs = defaultdict(list)
                if kind == 'independent':
                    files = [(g['name'], f"lfw_funneled/{g['name']}/{g['name']}_{i:04}.jpg") for g in ind['gallery'] for i in (1, 2)]
                else:
                    files = [(f.split('/')[-2], f) for f in sorted(bundle.namelist()) if '/gallery/' in f and f.endswith('.png')]
                for name, file in files:
                    image = decode(raw[file] if kind == 'independent' else bundle.read(file))
                    faces = engine.detect_faces(image)
                    if len(faces) != 1:
                        raise ValueError('Invalid reference: ' + file)
                    refs[name].append(features(image, faces)[0])
                result = [{'name': n, 'embedding': unit(np.mean(v, axis=0)).tolist()} for n, v in sorted(refs.items())]
                target.write_text(json.dumps(result))
                print('Gallery', kind, len(result), flush=True)
                return result

            methods = {'backlight': 'clahe', 'uneven': 'retinex', 'low_light': 'gamma'}
            scenes = {'01_逆光_CLAHE': 'backlight', '02_光照不均_Retinex': 'uneven', '03_低照度_Gamma': 'low_light'}
            for part in args.parts:
                target = work / ('r100-' + part + '.json')
                if target.exists():
                    previous = json.loads(target.read_text())
                    if previous['model_sha256'] != model_hash:
                        raise ValueError('Existing result uses a different model; choose a new output directory')
                    print('Already complete', part, flush=True)
                    continue
                source = pkg if part == 'package' else unknown if part == 'unknown' else ind
                rows = [r for r in source['rows'] if part not in ('development', 'validation') or r['split'] == part]
                templates = gallery('package' if part in ('package', 'unknown') else 'independent')
                names = [x['name'] for x in templates]
                matrix = np.stack([x['embedding'] for x in templates])
                results, counts, seen = [], defaultdict(Counter), Counter()
                if part == 'package':
                    files = [f for f in sorted(bundle.namelist()) if '/query/' in f and f.endswith('.png') and '/00_' not in f]
                    assert len(files) == len(rows)
                for index, row in enumerate(rows):
                    person, scene = row['person'], scenes.get(row['scene'], row['scene'])
                    if part == 'package':
                        file = files[index]
                        assert file.split('/')[-2] == person and file.split('/')[-3] == row['scene']
                        image = decode(bundle.read(file))
                    else:
                        number = 1 if part == 'unknown' else 3 + seen[person, scene]
                        seen[person, scene] += 1
                        file = f'lfw_funneled/{person}/{person}_{number:04}.jpg'
                        rgb = cv2.cvtColor(decode(raw[file]), cv2.COLOR_BGR2RGB)
                        seed = int(hashlib.sha256(file.encode()).hexdigest()[:8], 16)
                        image = cv2.cvtColor(simulate(rgb, scene, seed), cv2.COLOR_RGB2BGR)
                    enhanced, _ = enhance(image, EnhanceOptions(method=methods[scene], auto_parameters=True))
                    raw_faces = [{**f, 'embedding': v} for f, v in zip(row['raw'], features(image, row['raw']))]
                    extra = []
                    for face in row['enhanced']:
                        if not any(iou(face['bbox'], x['bbox']) >= .3 for x in raw_faces + extra):
                            extra.append(face)
                    vectors = features(enhanced, raw_faces + extra)
                    enhanced_faces = [{**f, 'embedding': v} for f, v in zip(extra, vectors[len(raw_faces):])]
                    fused = fuse_faces(raw_faces, enhanced_faces, vectors[:len(raw_faces)])
                    decisions = {}
                    for method, faces in [('original', raw_faces), ('enhanced', fused)]:
                        accepted, best_truth = [], -1
                        for face in faces:
                            scores = matrix @ unit(face['embedding'])
                            top = int(scores.argmax())
                            if scores[top] >= .45:
                                accepted.append(names[top])
                            if part != 'unknown':
                                best_truth = max(best_truth, float(scores[names.index(person)]))
                        correct = person in accepted if part != 'unknown' else not accepted
                        counts[scene, method].update(images=1, correct=int(correct), false_accept=int(part == 'unknown' and bool(accepted)))
                        decisions[method] = {'correct': correct, 'accepted': accepted, 'truth_score': best_truth}
                    results.append({'person': person, 'scene': scene, 'file': file, 'raw': raw_faces, 'enhanced': fused, 'decisions': decisions})
                    if (index + 1) % 60 == 0:
                        print(part, index + 1, len(rows), flush=True)
                report = {'model_sha256': model_hash, 'threshold': .45,
                          'summary': {f'{s}/{m}': dict(c) for (s, m), c in counts.items()}, 'rows': results}
                target.write_text(json.dumps(report))
                print('RESULT', part, json.dumps(report['summary']), flush=True)

        comparison = {
            'threshold': .45, 'enhanced_weight': .3, 'scoring_policy': 'image_identity_presence',
            'old_backbone': 'w600k_r50', 'new_backbone': 'glintr100',
            'new_model_sha256': model_hash, 'parts': {},
            'limitation': 'Public LFW with software lighting; fixed prior detections. This is not a field-performance claim. Model pretraining may include LFW identities. Thresholds and samples unchanged.',
        }
        for part in ['development', 'validation', 'package', 'unknown']:
            path = work / ('r100-' + part + '.json')
            if not path.exists():
                continue
            new_rows = json.loads(path.read_text())['rows']
            source = pkg if part == 'package' else unknown if part == 'unknown' else ind
            old_rows = [r for r in source['rows'] if part not in ('development', 'validation') or r['split'] == part]
            old_gallery = source.get('gallery', pkg['gallery'])
            new_gallery = json.loads((work / ('r100-' + ('package' if part in ('package', 'unknown') else 'independent') + '-gallery.json')).read_text())
            galleries = {
                'old': [{**g, 'id': i + 1} for i, g in enumerate(old_gallery)],
                'new': [{**g, 'id': i + 1} for i, g in enumerate(new_gallery)],
            }
            assert len(old_rows) == len(new_rows)
            summary, details = defaultdict(Counter), []
            for before, after in zip(old_rows, new_rows):
                assert before['person'] == after['person']
                if part == 'unknown':
                    assert all(before['person'] not in {g['name'] for g in gallery} for gallery in galleries.values())
                old_fused = fuse_faces(before['raw'], before['enhanced'], [f['embedding'] for f in before['aligned']])
                record = {k: after[k] for k in ['person', 'scene', 'file']}
                for method in ['original', 'enhanced']:
                    record[method] = {}
                    for variant, faces in [('old', before['raw'] if method == 'original' else old_fused),
                                           ('new', after['raw'] if method == 'original' else after['enhanced'])]:
                        decisions = [match(f['embedding'], galleries[variant], .45) for f in faces]
                        accepted = [m['name'] for m in decisions if m['confirmed']]
                        correct = before['person'] in accepted if part != 'unknown' else not accepted
                        stats = summary[after['scene'], method, variant]
                        stats.update(images=1, known=int(part != 'unknown'), unknown=int(part == 'unknown'),
                                     correct=int(part != 'unknown' and correct),
                                     false_accept=int(part == 'unknown' and not correct))
                        record[method][variant] = {'correct': correct, 'accepted': accepted, 'face_count': len(faces)}
                details.append(record)
            comparison['parts'][part] = {
                'summary': {'/'.join(key): dict(value) for key, value in summary.items()},
                'improvements': {m: sum(not r[m]['old']['correct'] and r[m]['new']['correct'] for r in details) for m in ['original', 'enhanced']},
                'regressions': {m: sum(r[m]['old']['correct'] and not r[m]['new']['correct'] for r in details) for m in ['original', 'enhanced']},
                'rows': details,
            }
        comparison['source_sha256'] = {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT / 'datasets/lfw_120_lighting.zip', ROOT / 'datasets/raw/lfw/lfw-funneled.tgz',
                         oldroot / 'package-cache.json', oldroot / 'independent-cache.json', oldroot / 'unknown-cache.json']
        }
        (work / 'comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2))
        print('Paired comparison saved:', work / 'comparison.json', flush=True)


if __name__ == '__main__':
    main()
