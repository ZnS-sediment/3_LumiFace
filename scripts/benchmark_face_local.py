#!/usr/bin/env python3
"""Evaluate every new-identity query against the combined 400-person gallery.

Uses production detection, enhancement, fusion and matching; labels only score
completed predictions. Resumable per-image records bind package/config hashes.
Parallel worker timing is NOT reported as production latency.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'datasets/lfw_280_new_lighting.zip'
WORK = ROOT / 'work/face-local-v4/reproduction-new'
METHODS = {'00_正常光照':'original','01_逆光_CLAHE':'clahe','02_光照不均_Retinex':'retinex','03_低照度_Gamma':'gamma'}


def initialize(templates, fingerprint, archive):
    global gallery, bundle, engine, match, recognition_faces, enhance, EnhanceOptions, DEFAULT_THRESHOLD, RECOGNITION_POLICY, cv2, np
    sys.path.insert(0,str(ROOT/'backend'))
    import cv2
    import numpy as np
    from app.algorithms.face_detector import engine
    from app.algorithms.face_recognizer import match
    from app.algorithms.recognition import recognition_faces, RECOGNITION_POLICY
    from app.algorithms.enhancement import enhance
    from app.schemas.contracts import EnhanceOptions
    from app.core.config import DEFAULT_THRESHOLD
    engine.load()
    assert engine.fingerprint == fingerprint
    gallery = templates
    bundle = zipfile.ZipFile(archive)


def process(file):
    image = cv2.imdecode(np.frombuffer(bundle.read(file), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Cannot decode ' + file)
    method = METHODS[file.split('/')[2]]
    raw = engine.infer(image)
    groups = {'original': raw}
    if method != 'original':
        enhanced, _ = enhance(image, EnhanceOptions(method=method, auto_parameters=True))
        groups[method] = recognition_faces(image, enhanced, RECOGNITION_POLICY, original_faces=raw, enhancement_method=method)
    decisions = {}
    for name, faces in groups.items():
        matches = [match(face['embedding'], gallery, DEFAULT_THRESHOLD) for face in faces]
        decisions[name] = {'face_count': len(faces), 'matches': matches,
            'accepted_names': sorted({m['name'] for m in matches if m['confirmed']})}
    # Labels are used only after all decisions, never fed to enhancement/matching.
    truth = file.split('/')[-2]
    for decision in decisions.values():
        decision['correct'] = truth in decision['accepted_names']
        decision['outcome'] = 'correct' if decision['correct'] else 'no_face' if not decision['face_count'] else 'wrong_identity' if decision['accepted_names'] else 'rejected'
    return {'file': file, 'scene': file.split('/')[2], 'expected_name': truth, 'decisions': decisions}


def main():
    global ARCHIVE, WORK
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=2,choices=[1,2,3])
    parser.add_argument('--original-package', action='store_true', help='Regress all 120 original identities against the same 400-person gallery')
    parser.add_argument('--retinex-only', action='store_true', help='Evaluate only Retinex on the selected download archive')
    args=parser.parse_args()
    if args.original_package:
        ARCHIVE = ROOT / 'datasets/lfw_120_lighting.zip'
        WORK = ROOT / 'work/face-local-v4/reproduction-old'
    if args.retinex_only:
        ARCHIVE = ROOT / ('datasets/lfw_120_lighting.zip' if args.original_package else 'datasets/lfw_280_new_lighting.zip')
        WORK = ROOT / ('work/face-local-v4/retinex-original-final' if args.original_package else 'work/face-local-v4/retinex-global-final')
    WORK.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'backend'))
    from app.core.config import DEFAULT_THRESHOLD, DEFAULT_THRESHOLD_POLICY, ALGORITHM_VERSION
    from app.algorithms.recognition import RECOGNITION_POLICY, ENHANCED_WEIGHT, LOCAL_POLICIES, METHOD_ENHANCED_WEIGHTS
    refs_path=ROOT/'work/lfw-400/references.json'
    refs=json.loads(refs_path.read_text())
    templates=[{'id':index+1,**person} for index,person in enumerate(refs['people'].values())]
    with zipfile.ZipFile(ARCHIVE) as z, zipfile.ZipFile(ROOT/'datasets/lfw_120_lighting.zip') as old:
        files=sorted(n for n in z.namelist() if '/query/' in n and n.endswith('.png') and (not args.retinex_only or '/02_光照不均_Retinex/' in n))
        new_names={n.split('/')[-2] for n in files}
        old_names={n.split('/')[-2] for n in old.namelist() if '/gallery/' in n and n.endswith('.png')}
    assert len(old_names)==120
    if args.retinex_only:
        assert len(files)==(360 if args.original_package else 840)
        assert len(new_names)==(120 if args.original_package else 280)
        assert new_names <= {p['name'] for p in templates}
    elif args.original_package:
        assert len(files)==1440 and new_names==old_names
        assert new_names <= {p['name'] for p in templates}
    else:
        assert len(files)==3360 and len(new_names)==280
        assert not new_names & old_names
        assert {p['name'] for p in templates} == new_names | old_names
    protocol={'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        'gallery_cache_sha256':hashlib.sha256(refs_path.read_bytes()).hexdigest(),
        'gallery_size':len(templates),'queries':len(files),'identities':len(new_names),
        'model_fingerprint':refs['model_fingerprint'],'threshold':DEFAULT_THRESHOLD,
        'threshold_policy':DEFAULT_THRESHOLD_POLICY,'algorithm_version':ALGORITHM_VERSION,
        'recognition_policy':RECOGNITION_POLICY,'enhanced_weight':ENHANCED_WEIGHT, 'local_policies':LOCAL_POLICIES, 'method_enhanced_weights':METHOD_ENHANCED_WEIGHTS,
        'scoring':'exact identity in confirmed per-face top1 decisions; every image counted',
        'methods':METHODS,'previous_identity_overlap':len(new_names & old_names),
        'targets':{'low_light':.95,'backlight':.90,'normal_low_light_backlight_combined':.95},
        'limitations':'Software simulated lighting, not infrared/real-capture validation. No unknown subjects in this pack. Gallery contains all 120 old and 280 new identities; no query filtering.'}
    protocol_path=WORK/'protocol.json'
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text()) == protocol, 'Protocol changed; use a fresh evidence directory'
    else:
        protocol_path.write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    records_path=WORK/'predictions.jsonl'
    done={}
    if records_path.exists():
        for line in records_path.read_text().splitlines():
            row=json.loads(line);assert row['file'] in files and row['file'] not in done;done[row['file']]=row
    pending=[f for f in files if f not in done]
    print('Resume:',len(done),'/',len(files),flush=True)
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='lumiface-new-dataset-') as temporary:
        os.environ['LUMIFACE_DATA']=temporary
        with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn'),initializer=initialize,initargs=(templates,refs['model_fingerprint'],str(ARCHIVE))) as pool, records_path.open('a') as output:
            for row in pool.map(process,pending,chunksize=1):
                output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush();done[row['file']]=row
                if len(done)%60==0 or len(done)==len(files):
                    print(f"Completed {len(done)}/{len(files)}; elapsed {time.monotonic()-start:.1f}s",flush=True)
    summaries=defaultdict(lambda:{'images':0,'correct':0,'no_face':0,'rejected':0,'wrong_identity':0})
    for row in done.values():
        for method,decision in row['decisions'].items():
            stats=summaries[row['scene']+'/'+method];stats['images']+=1;stats[decision['outcome']]+=1
    for stats in summaries.values():stats['accuracy']=stats['correct']/stats['images']
    selected=[row['decisions'][METHODS[row['scene']]] for row in done.values() if row['scene'] in ['00_正常光照','01_逆光_CLAHE','03_低照度_Gamma']]
    combined={'images':len(selected),'correct':sum(row['correct'] for row in selected)}
    combined['accuracy']=combined['correct']/combined['images'] if combined['images'] else None
    targets={}
    for target, key, minimum in [('low_light', '03_低照度_Gamma/gamma', .95), ('backlight', '01_逆光_CLAHE/clahe', .90)]:
        if key in summaries: targets[target] = summaries[key]['accuracy'] >= minimum
    if combined['images']:
        targets['normal_low_light_backlight_combined'] = combined['accuracy'] >= .95
    result={'protocol':protocol,'summary':dict(summaries),'combined':combined,'simulation_targets_passed':targets,
        'prediction_sha256':hashlib.sha256(records_path.read_bytes()).hexdigest(),
        'errors':[r for r in done.values() if any(not d['correct'] for d in r['decisions'].values())]}
    (WORK/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'summary':dict(summaries),'combined':combined,'targets':targets},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
