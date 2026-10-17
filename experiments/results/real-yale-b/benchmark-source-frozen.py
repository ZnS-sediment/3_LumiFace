#!/usr/bin/env python3
"""Reproducible real-image benchmarks. Fixed splits are written BEFORE inference.
CBSR: original official gallery/probe, in-domain NIR -> NIR, unknown subjects disjoint.
Yale: original subjects 01..10, controlled-illumination holdout; NOT an independent field test.
No detector-generated ground truth; supplied eye labels or single-face image presence only.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
METHODS = ['original', 'gamma', 'clahe', 'retinex', 'adaptive']
_ARCHIVES: dict[str, zipfile.ZipFile] = {}
_TEMPLATES: list[dict] = []


def read_image(archive_path: str, member: str):
    import cv2
    import numpy as np
    if archive_path not in _ARCHIVES:
        _ARCHIVES[archive_path] = zipfile.ZipFile(archive_path)
    package = _ARCHIVES[archive_path]
    image = cv2.imdecode(np.frombuffer(package.read(member), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Image decode failed: {member}')
    return image


def infer_with_border(image, border: int = 0) -> list[dict]:
    """Detector context padding only; illumination analysis always sees original pixels."""
    import cv2
    from app.algorithms.face_detector import engine
    if not border:
        return engine.infer(image)
    padded = cv2.copyMakeBorder(image, border, border, border, border, cv2.BORDER_CONSTANT, value=(100,100,100))
    faces = engine.infer(padded)
    result = []
    for face in faces:
        corrected = dict(face)
        corrected['bbox'] = [v-border for v in face['bbox']]
        corrected['keypoints'] = [[x-border,y-border] for x,y in face['keypoints']]
        result.append(corrected)
    return result


def worker_init(templates: list[dict]) -> None:
    global _TEMPLATES
    _TEMPLATES = templates
    from app.algorithms.face_detector import engine
    import numpy as np
    import cv2
    import warnings
    cv2.setNumThreads(1)
    engine.load()
    warnings.filterwarnings('ignore', category=FutureWarning, module='insightface.utils.face_align')
    engine.infer(np.full((320, 320, 3), 128, dtype=np.uint8))


def infer_job(job: tuple[dict, str, str]) -> dict:
    item, method, archive_path = job
    from app.algorithms.face_detector import engine
    from app.algorithms.face_recognizer import match
    from app.algorithms.enhancement import enhance
    from app.schemas.contracts import EnhanceOptions
    image = read_image(archive_path, item['file'])
    start = time.perf_counter()
    processed, steps = enhance(image, EnhanceOptions(method=method))
    faces = infer_with_border(processed, item.get('detector_border',0))
    predictions = [{k: v for k, v in face.items() if k != 'embedding'} |
                   {'match': match(face['embedding'], _TEMPLATES, -1)} for face in faces]
    return {'file': item['file'], 'method': method, 'scene': item['scene'], 'truth': item['faces'],
            'predictions': predictions, 'steps': steps, 'elapsed_ms': (time.perf_counter() - start) * 1000}


def score_prediction(row: dict, threshold: float, localization: str) -> dict:
    from app.algorithms.metrics import score_image
    predictions = []
    for raw in row['predictions']:
        decision = dict(raw['match'])
        candidates = decision['candidates']
        confirmed = bool(candidates and decision['similarity'] >= threshold)
        decision.update(confirmed=confirmed, threshold=threshold,
                        person_id=candidates[0]['person_id'] if confirmed else None,
                        name=candidates[0]['name'] if confirmed else '未知身份')
        predictions.append({**raw, 'match': decision})
    return {**score_image(row['truth'], predictions, row['elapsed_ms'], protocol=localization),
            'file': row['file'], 'method': row['method'], 'scene': row['scene'], 'steps': row['steps']}


def cbsr_protocol(folder: Path, profile: str = 'full') -> tuple[dict, list[dict], list[dict], list[dict]]:
    def parse(name: str) -> dict[int, list[dict]]:
        groups: dict[int, list[dict]] = {}
        for line in (folder / name).read_text().splitlines():
            if not line.strip():
                continue
            filename, *coords = line.strip().split(',')
            subject = int(filename.split('-')[0])
            x1, y1, x2, y2 = map(float, coords)
            eyes = [[x1, y1], [x2, y2]]
            distance = ((x2-x1)**2 + (y2-y1)**2)**.5
            mid = (x1+x2)/2
            y = (y1+y2)/2
            # A display-only proxy; localization scoring uses the supplied eye points.
            bbox = [max(0, mid-.9*distance), max(0, y-.65*distance), min(480, mid+.9*distance), min(640, y+1.6*distance)]
            groups.setdefault(subject, []).append({'file': 'NIR_face_dataset/'+filename, 'scene': 'infrared',
                'capture_id': 'official-probe' if 'probe' in name else 'official-gallery',
                'faces': [{'bbox': bbox, 'eyes': eyes, 'person_id': subject if subject <= 100 else None,
                           'subject': f'CBSR-{subject:04d}'}]})
        return {k: sorted(v, key=lambda x: x['file']) for k, v in groups.items()}
    gallery = parse('gallery-groundtruth.txt')
    probes = parse('probe-groundtruth.txt')
    identities = sorted(gallery)
    if profile == 'pilot':
        known_ids, calibration_unknown_ids, test_unknown_ids = identities[:20], identities[20:30], identities[30:50]
    else:
        known_ids, calibration_unknown_ids, test_unknown_ids = identities[:100], identities[100:140], identities[140:]
    for rows in [*gallery.values(), *probes.values()]:
        for row in rows:
            original_id = int(row['file'].split('/')[-1].split('-')[0])
            row['faces'][0]['person_id'] = original_id if original_id in known_ids else None
    if len(gallery) != 197 or any(len(v) != 8 for v in gallery.values()) or any(len(v) != 12 for v in probes.values()):
        raise ValueError('Unexpected official CBSR split counts')
    if profile == 'pilot':
        enrollment = [x for person in known_ids for x in gallery[person][:4]]
        calibration = [x for person in known_ids for x in probes[person][:2]]+[x for person in calibration_unknown_ids for x in probes[person][:3]]
        test = [x for person in known_ids for x in probes[person][2:7]]+[x for person in test_unknown_ids for x in probes[person][:5]]
    else:
        enrollment = [x for person in known_ids for x in gallery[person]]
        calibration = [x for person in known_ids+calibration_unknown_ids for x in probes[person][:4]]
        test = [x for person in known_ids for x in probes[person][4:]] + [x for person in test_unknown_ids for x in probes[person]]
    protocol = {'name': 'CBSR-NIR open-set, fixed official gallery/probe with held-out unknown subjects', 'profile':profile,
        'localization_protocol': 'eye_containment', 'capture_independence': 'unknown',
        'source': 'http://vcipl-okstate.org/pbvs/bench/Data/07/download.html',
        'terms': 'http://vcipl-okstate.org/pbvs/bench/index.html',
        'scene_evidence': {'infrared': {'source': 'OTCBVS dataset 07 official sensor and protocol description',
            'annotation_basis': 'dataset_metadata', 'modality': 'nir', 'active_illumination': True,
            'night_confirmed': False}},
        'scene_labels': {'infrared': '真实主动近红外（夜间环境未注明）'},
        'limitations': ['NIR->NIR only; no RGB->NIR guarantee', 'Night/ambient-light metadata and independent sessions are not provided',
                       'Supplied eye labels test eye containment, not IoU detection accuracy',
                       'No bounding boxes or night labels have been generated from model predictions'],
        'roles': {'known_subjects': known_ids, 'unknown_calibration': calibration_unknown_ids, 'unknown_test': test_unknown_ids}}
    return protocol, enrollment, calibration, test


def yale_protocol(archive: Path, profile: str = 'full') -> tuple[dict, list[dict], list[dict], list[dict]]:
    # Original Yale B subjects only; the original owner's explicit research terms apply.
    pattern = re.compile(r'^CroppedYale/yaleB(\d{2})/yaleB\d{2}_P00(?:A([+-]\d{3})E([+-]\d{2})|_Ambient)\.pgm$')
    groups: dict[int, list[dict]] = {}
    quality_lists = {}
    for name in ['no_strobe.html','corrupt.html']:
        path = archive.parent/name
        quality_lists[name] = set(re.findall(r'yaleB\d{2}_P\d{2}A[+-]\d{3}E[+-]\d{2}\.pgm',path.read_text())) if path.exists() else set()
    with zipfile.ZipFile(archive) as package:
        for name in sorted(package.namelist()):
            parsed = pattern.match(name)
            if not parsed or int(parsed[1]) > 10:
                continue
            subject = int(parsed[1])
            azimuth = int(parsed[2]) if parsed[2] else None
            elevation = int(parsed[3]) if parsed[3] else None
            quality = 'field_imbalance' if Path(name).name in quality_lists['corrupt.html'] else 'standard'
            if Path(name).name in quality_lists['no_strobe.html']:
                scene = 'acquisition_failure_no_flash'
                quality = 'documented_flash_failure'
            elif azimuth is None:
                scene = 'ambient_no_flash'
            elif abs(azimuth) >= 90:
                scene = 'controlled_rear_side'
            elif abs(azimuth) > 35 or abs(elevation) > 35:
                scene = 'controlled_oblique'
            else:
                scene = 'controlled_frontal'
            groups.setdefault(subject, []).append({'file': name, 'scene': scene,
                'capture_id': 'same-acquisition-P00', 'azimuth': azimuth, 'elevation': elevation, 'detector_border': 100, 'source_quality':quality,
                'faces': [{'bbox': [0,0,168,192], 'person_id': subject if subject <= 6 else None, 'subject': f'YaleB-{subject:02d}'}]})
    reference_suffixes = ['A+000E+00.pgm', 'A+005E+10.pgm', 'A-005E+10.pgm', 'A+000E+20.pgm']
    enrollment, calibration, test = [], [], []
    for subject, rows in sorted(groups.items()):
        reference = [r for r in rows if subject <= 6 and any(r['file'].endswith(s) for s in reference_suffixes)]
        if subject <= 6 and len(reference) != 4:
            raise ValueError(f'Missing predeclared Yale gallery samples: {subject}')
        enrollment.extend(reference)
        rest = [r for r in rows if r not in reference]
        if profile == 'pilot':
            buckets = {}
            for row in rest:buckets.setdefault(row['scene'],[]).append(row)
            if subject <= 6:
                for scene,items in sorted(buckets.items()):
                    if scene in ('ambient_no_flash','acquisition_failure_no_flash'):test.extend(items)
                    else:
                        calibration.extend(items[:2]);test.extend(items[2:5])
            elif subject <= 8:
                for items in buckets.values():calibration.extend(items[:2])
            else:
                for items in buckets.values():test.extend(items[:4])
        elif subject <= 6:
            calibration.extend(r for i,r in enumerate(rest) if i%3 == 0)
            test.extend(r for i,r in enumerate(rest) if i%3 != 0)
        elif subject <= 8:
            calibration.extend(rest)
        else:
            test.extend(rest)
    protocol = {'name': 'Original Yale B 01..10, fixed controlled-illumination holdout (limited benchmark)', 'profile':profile,
        'localization_protocol': 'single_face_presence', 'capture_independence': 'condition_disjoint',
        'detector_border': {'pixels':100, 'value':100, 'applied':'after enhancement, gallery and every query identically', 'selected_on':'reference enrollment image only, before query inference'},
        'source': 'http://cvc.cs.yale.edu/cvc/projects/yalefacesB/yalefacesB.html',
        'scene_evidence': {}, 'source_quality_lists': {name:sorted(values) for name,values in quality_lists.items()},
        'scene_labels': {'acquisition_failure_no_flash':'原库记录的闪光未触发', 'ambient_no_flash': '无闪光环境光（不等同夜间）',
            'controlled_frontal': '受控正面光', 'controlled_oblique': '受控斜向光', 'controlled_rear_side': '受控背侧光（非实景强逆光）'},
        'limitations': ['Original cropped data, no independent capture sessions',
                       'Images were acquired in approximately two seconds under changing strobes',
                       'Single-face presence is not IoU localization validation',
                       'No actual IR, field low-light, or bright-background backlight labels',
                       'Original 01..10 only; extra subjects in mirror are not used',
                       'Documented flash failures have their own scene; mild source field imbalance is flagged, not filtered using model scores'],
        'roles': {'known_subjects': list(range(1,7)), 'unknown_calibration': [7,8], 'unknown_test': [9,10]},
        'mirror': 'https://raw.githubusercontent.com/trokas/ai_primer/master/img/CroppedYale.zip'}
    return protocol, enrollment, calibration, test


def validate_split(enrollment: list[dict], calibration: list[dict], test: list[dict]) -> None:
    filenames = [{x['file'] for x in split} for split in (enrollment, calibration, test)]
    if any(filenames[i] & filenames[j] for i,j in [(0,1),(0,2),(1,2)]):
        raise ValueError('Image filename leakage')
    unknown = [{f['subject'] for x in split for f in x['faces'] if f['person_id'] is None} for split in (calibration,test)]
    if unknown[0] & unknown[1]:
        raise ValueError('Unknown subject leakage')


def audit_and_deduplicate(archive: Path, enrollment: list[dict], calibration: list[dict], test: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Fixed, pre-inference exact-pixel deduplication; never inspect prediction scores."""
    seen: dict[str, tuple[str,str]] = {}
    exclusions = []
    splits = []
    original_counts = [len(enrollment),len(calibration),len(test)]
    for role,items in [('gallery',enrollment),('calibration',calibration),('test',test)]:
        kept = []
        for item in items:
            image = read_image(str(archive),item['file'])
            digest = hashlib.sha256(str(image.shape).encode()+image.tobytes()).hexdigest()
            if digest in seen:
                prior_role,prior_file = seen[digest]
                exclusions.append({'file':item['file'],'role':role,'same_pixels_as':prior_file,'prior_role':prior_role,'reason':'exact canonical pixel duplicate, excluded before inference'})
            else:
                seen[digest] = (role,item['file'])
                kept.append(item)
        splits.append(kept)
    return *splits, {'rule':'gallery > calibration > test; retain first canonical-pixel image; filenames/labels and source ordering fixed before inference',
                     'original_counts':dict(zip(['gallery','calibration','test'],original_counts)),
                     'unique_counts':dict(zip(['gallery','calibration','test'],map(len,splits))), 'exclusions':exclusions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset', choices=['cbsr-nir','yale-b'])
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--profile', choices=['pilot','full'], default='pilot')
    parser.add_argument('--detector-size', type=int, choices=[320,640], default=320)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit('workers must be 1..8')
    private = ROOT / 'work' / 'research' / args.dataset
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ['LUMIFACE_DATA'] = str(private / 'runtime')
    os.environ['LUMIFACE_DETECTION_SIZE'] = str(args.detector_size)
    os.environ['MPLCONFIGDIR'] = str(private / 'matplotlib')
    for variable in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
        os.environ[variable] = '1'
    from app.algorithms.face_detector import engine
    from app.algorithms.face_recognizer import unit
    from app.algorithms.metrics import aggregate, calibrate
    from app.algorithms.evidence import assess_target
    from app.schemas.contracts import EnhanceOptions
    from app.services.experiments import environment
    import numpy as np
    import cv2
    import warnings
    cv2.setNumThreads(1)
    warnings.filterwarnings('ignore', category=FutureWarning, module='insightface.utils.face_align')
    folder = ROOT / 'datasets' / 'raw' / args.dataset
    archive = folder / ('CBSR-NIR.zip' if args.dataset == 'cbsr-nir' else 'CroppedYale.zip')
    protocol, enrollment, calibration, test = cbsr_protocol(folder,args.profile) if args.dataset == 'cbsr-nir' else yale_protocol(archive,args.profile)
    validate_split(enrollment,calibration,test)
    enrollment,calibration,test,split_audit = audit_and_deduplicate(archive,enrollment,calibration,test)
    config = {'dataset': args.dataset, 'profile':args.profile, 'detector_size':args.detector_size, 'real_capture': True, 'protocol': protocol,
              'methods': METHODS, 'parameters': {m: EnhanceOptions(method=m).model_dump() for m in METHODS},
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'target_calibration_far': .01,
              'workers': args.workers, 'opencv_threads_per_worker':1, 'split_audit': split_audit, 'time_scope': 'enhancement+detection+embedding+search; concurrent CPU workers; not a dedicated speed benchmark',
              'enrollment': enrollment, 'calibration': calibration, 'test': test,
              'frozen_before_inference_utc': datetime.now(timezone.utc).isoformat(),
              'code_hashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                  ['backend/app/algorithms/enhancement.py','backend/app/algorithms/metrics.py', 'backend/app/algorithms/face_detector.py', 'experiments/scripts/benchmark_public.py']}}
    output = args.output or ROOT / 'experiments' / 'results' / f'real-{args.dataset}'
    output.mkdir(parents=True,exist_ok=True)
    config_path = output / 'protocol-frozen.json'
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2))
    config_digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
    (output / 'benchmark-source-frozen.py').write_bytes(Path(__file__).read_bytes())
    print(f'Protocol frozen {config_digest}: gallery={len(enrollment)}, calibration={len(calibration)}, test={len(test)}',flush=True)
    engine.load()
    embeddings: dict[int,list] = {}
    enrollment_failures = []
    for index,item in enumerate(enrollment):
        image = read_image(str(archive),item['file'])
        faces = infer_with_border(image, item.get('detector_border',0))
        if len(faces) == 1:
            embeddings.setdefault(item['faces'][0]['person_id'],[]).append(unit(faces[0]['embedding']))
        else:
            enrollment_failures.append({'file': item['file'], 'detected_faces': len(faces)})
        if (index+1)%100 == 0:print(f'Gallery {index+1}/{len(enrollment)}',flush=True)
    templates = [{'id': identity, 'name': f'{args.dataset}-{identity:04d}', 'embedding': unit(np.mean(vectors,axis=0)).tolist()}
                 for identity,vectors in sorted(embeddings.items())]
    if not templates:
        raise SystemExit('No usable gallery references; benchmark cannot run')
    # Failed enrollments remain in the known query denominators; never silently remove their subjects.
    report = {'dataset': args.dataset, 'title': ('CBSR 真实近红外评估' if args.dataset=='cbsr-nir' else 'Yale B 真实受控光照评估')+(' · 固定子集' if args.profile=='pilot' else ' · 全协议'), 'profile':args.profile,
        'protocol': protocol, 'protocol_sha256': config_digest, 'environment': environment(),
        'real_capture': True, 'gallery_subjects': len(templates), 'gallery_images': len(enrollment),
        'gallery_accepted_images': sum(len(v) for v in embeddings.values()), 'enrollment_failures': enrollment_failures,
        'calibration_images': len(calibration), 'test_images': len(test), 'status': 'running',
        'time_scope': config['time_scope'], 'workers': args.workers, 'split_audit':split_audit}
    manifest = {item['file']: item for item in calibration+test}
    localization = protocol['localization_protocol']
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=context, initializer=worker_init, initargs=(templates,)) as pool:
        raw_calibration: dict[str,list[dict]] = {m:[] for m in METHODS}
        jobs = [(item,method,str(archive)) for item in calibration for method in METHODS]
        for index,row in enumerate(pool.map(infer_job,jobs,chunksize=4)):
            raw_calibration[row['method']].append(row)
            if (index+1)%100 == 0:print(f'Calibration {index+1}/{len(jobs)}',flush=True)
        thresholds = {}
        calibration_details = {}
        for method,raw_rows in raw_calibration.items():
            decisions = [decision for row in raw_rows for decision in score_prediction(row,-1,localization)['decisions']]
            choice = calibrate(decisions,.01)
            thresholds[method] = choice['threshold']
            calibration_details[method] = choice
        frozen = {'thresholds': thresholds, 'details': calibration_details,
                  'frozen_before_test_utc': datetime.now(timezone.utc).isoformat(), 'protocol_sha256':config_digest}
        (output/'thresholds-frozen.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2))
        print('Thresholds frozen: '+json.dumps(thresholds),flush=True)
        report['thresholds'] = thresholds
        report['calibration'] = calibration_details
        all_rows = []
        jobs = [(item,method,str(archive)) for item in test for method in METHODS]
        with (output/'predictions.jsonl').open('w') as result_file:
            for index,row in enumerate(pool.map(infer_job,jobs,chunksize=4)):
                scored = score_prediction(row,thresholds[row['method']],localization)
                scored['capture_id'] = manifest[row['file']]['capture_id']
                result_file.write(json.dumps(scored,ensure_ascii=False)+'\n')
                all_rows.append(scored)
                if (index+1)%100 == 0:print(f'Test {index+1}/{len(jobs)}',flush=True)
    summary = {}
    for method in METHODS:
        rows = [r for r in all_rows if r['method']==method]
        scene_stats = {scene: aggregate([r for r in rows if r['scene']==scene]) for scene in sorted({r['scene'] for r in rows})}
        overall = aggregate(rows)
        targets = {}
        for scene in ['infrared','backlight','overall']:
            stats = overall if scene=='overall' else scene_stats.get(scene,aggregate([]))
            coverage = all(scene_stats.get(s,{}).get('known',0)>0 for s in ['normal','low_light','backlight']) if scene=='overall' else stats['known']>0
            targets[scene] = assess_target(scene,stats,real_capture=True,independent_calibration=True,protocol=protocol,coverage=coverage)
        summary[method] = {'overall':overall,'scenes':scene_stats,'targets':targets}
    baseline = summary['original']['overall']['confirmation_rate']
    for value in summary.values():
        value['delta_vs_original'] = value['overall']['confirmation_rate']-baseline if baseline is not None and value['overall']['confirmation_rate'] is not None else None
    report.update(summary=summary,status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat())
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    import csv
    with (output/'results.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        fields=['tp','fp','fn','known','unknown','correct','false_accept','elapsed_ms']
        writer.writerow(['method','scene','file',*fields])
        for row in all_rows:writer.writerow([row['method'],row['scene'],row['file'],*[row[key] for key in fields]])
    print(json.dumps({'output':str(output),'summary':{m:{k:v for k,v in s['overall'].items() if k in ('known','unknown','correct','confirmation_rate','unknown_far')} for m,s in summary.items()}},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
