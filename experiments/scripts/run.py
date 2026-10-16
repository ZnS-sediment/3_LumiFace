#!/usr/bin/env python3
"""Submit and poll a real experiment, export auditable JSON and CSV."""
import argparse
import json
import time
from pathlib import Path
import httpx


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('experiments/results'))
    args=parser.parse_args()
    with httpx.Client(base_url=args.base_url,timeout=180) as client:
        response=client.post('/api/experiment/run',json=json.loads(args.config.read_text()))
        response.raise_for_status()
        identity=response.json()['data']['id']
        while True:
            response=client.get(f'/api/experiment/{identity}')
            response.raise_for_status()
            result=response.json()['data']
            print(f"{result['status']} {result['progress']}/{result['total']}",flush=True)
            if result['status'] in ('completed','failed'):break
            time.sleep(2)
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/f'experiment-{identity}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        if result['status']=='failed':raise SystemExit(result['error'])
        csv=client.get(f'/api/experiment/{identity}/csv')
        csv.raise_for_status()
        (args.output/f'experiment-{identity}.csv').write_bytes(csv.content)


if __name__=='__main__':main()
