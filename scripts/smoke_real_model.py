#!/usr/bin/env python3
"""Real model end-to-end smoke test; synthetic perturbations are NOT a benchmark.
Uses an isolated temporary database. Never populates the user's identity library.
"""
import argparse
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'experiments/results/smoke-real-model.json')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='lumiface-real-smoke-') as storage:
        os.environ['LUMIFACE_DATA'] = storage
        os.environ.setdefault('MPLCONFIGDIR', str(Path(storage) / 'cache' / 'matplotlib'))
        from fastapi.testclient import TestClient
        import cv2
        import matplotlib
        import numpy as np
        from skimage import data
        from app.main import app
        from app.services.images import png
        from app.algorithms.enhancement import gamma
        astronaut = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
        hopper = cv2.imread(str(Path(matplotlib.get_data_path()) / 'sample_data' / 'grace_hopper.jpg'))
        if hopper is None:
            raise RuntimeError('Matplotlib grace_hopper sample image is missing')
        report = {'purpose': 'Real inference / API integration smoke test only',
                  'performance_claim': 'NOT a real-scene benchmark. Same-source synthetic variants are correlated; no 95%/90% target is validated.',
                  'sources': ['https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut',
                              'https://github.com/matplotlib/matplotlib/tree/main/lib/matplotlib/mpl-data/sample_data'], 'checks': {}}
        with TestClient(app) as client:
            def require(response):
                if response.status_code != 200:
                    raise RuntimeError(f'{response.status_code}: {response.text[:2000]}')
                return response.json()['data']
            report['model'] = require(client.post('/api/system/model/load'))
            person = require(client.post('/api/person/register', data={'name': 'Smoke reference A', 'capture_id': 'synthetic-source-reference'},
                            files=[('files', ('astronaut.png', png(astronaut), 'image/png'))]))
            pid = person['id']
            probe = gamma(astronaut, 1.1)
            known = require(client.post('/api/recognition/verify', data={'person_id': pid, 'options': '{"method":"original"}'}, files={'file': ('probe.png', png(probe), 'image/png')}))
            unknown = require(client.post('/api/recognition/identify', data={'options': '{"method":"original"}'}, files={'file': ('unknown.png', png(hopper), 'image/png')}))
            assert known['confirmed'] and not unknown['confirmed']
            report['checks']['known_verification'] = {k: known[k] for k in ['confirmed','similarity','threshold','elapsed_ms']}
            report['checks']['unknown_rejection'] = {k: unknown[k] for k in ['confirmed','similarity','threshold','elapsed_ms']}
            multi = np.full((650,1050,3),127,np.uint8)
            multi[:astronaut.shape[0],:astronaut.shape[1]] = astronaut
            multi[:hopper.shape[0],530:530+hopper.shape[1]] = hopper
            detected = require(client.post('/api/face/detect', data={'options': '{"method":"original"}'}, files={'file': ('multi.png', png(multi), 'image/png')}))
            assert detected['original']['count'] >= 2
            report['checks']['multi_face_count'] = detected['original']['count']
            items = []
            images = {}
            # Explicit approximate manual face boxes; never detector-generated ground truth.
            cases = [('normal', gamma(astronaut,1.05), [175,55,277,185], pid, 'known-A'),
                     ('low_light', gamma(astronaut,2.2), [175,55,277,185], pid, 'known-A')]
            backlight = astronaut.copy()
            dark = gamma(astronaut,2)
            backlight[45:195,165:290] = dark[45:195,165:290]
            cases += [('backlight',backlight,[175,55,277,185],pid,'known-A'),
                      ('normal',hopper,[175,120,355,335],None,'unknown-B')]
            for index,(scene,image,bbox,label,subject) in enumerate(cases):
                filename=f'images/{index}.png'
                images[filename]=png(image)
                items.append({'file':filename,'scene':scene,'capture_id':f'synthetic-derived-case-{index}',
                              'faces':[{'bbox':bbox,'person_id':label,'subject':subject}]})
            manifest={'name':'Synthetic-variant integration smoke (NOT benchmark)','split':'test',
                      'source':'scikit-image astronaut and Matplotlib grace_hopper; deterministic gamma / local darkening derivatives of source pictures',
                      'license':'Upstream sample image terms; astronaut NASA public domain. Retain upstream attribution.',
                      'real_capture':False,'items':items}
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json',json.dumps(manifest))
                for path,payload in images.items():archive.writestr(path,payload)
            dataset=require(client.post('/api/dataset/import',files={'file':('smoke.zip',buffer.getvalue(),'application/zip')}))
            experiment=require(client.post('/api/experiment/run',json={'dataset_id':dataset['id'],'threshold':.45}))
            result=require(client.get(f'/api/experiment/{experiment["id"]}'))
            assert result['status']=='completed',result['error']
            assert all(s['targets']['infrared']['status']=='未评估' for s in result['summary'].values())
            assert all('达标' not in s['targets']['overall']['status'] or '不能判定达标' in s['targets']['overall']['status'] for s in result['summary'].values())
            rows=require(client.get(f'/api/experiment/{experiment["id"]}/results'))
            report['experiment']=result
            report['predictions']=rows
            csv=client.get(f'/api/experiment/{experiment["id"]}/csv')
            assert csv.status_code==200
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.with_suffix('.csv').write_text(csv.text,encoding='utf-8')
            require(client.delete(f'/api/person/{pid}'))
            assert require(client.get('/api/person'))==[]
            report['checks']['delete_person_and_samples']=True
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'output':str(args.output),'checks':report['checks'],
                          'confirmation_rates':{m:s['overall']['confirmation_rate'] for m,s in report['experiment']['summary'].items()},
                          'limitation':report['performance_claim']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
