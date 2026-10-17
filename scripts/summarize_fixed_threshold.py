#!/usr/bin/env python3
"""Secondary comparison at the pre-existing software default; no score-based tuning."""
import json
from pathlib import Path
import sys
import hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.algorithms.metrics import aggregate,score_image


def summarize(folder: Path) -> dict:
    preset=ROOT/'experiments/configs/fixed-threshold-protocol.json'
    declaration=json.loads(preset.read_text())
    threshold=declaration['threshold']
    config=json.loads((folder/'protocol-frozen.json').read_text())
    truth={item['file']:item['faces'] for item in config['test']}
    rows=[]
    for line in (folder/'predictions.jsonl').read_text().splitlines():
        original=json.loads(line)
        predictions=[]
        for face in original['predictions']:
            decision=dict(face['match'])
            candidates=decision['candidates']
            accepted=bool(candidates and decision['similarity']>=threshold)
            decision.update(confirmed=accepted,threshold=threshold,person_id=candidates[0]['person_id'] if accepted else None,
                            name=candidates[0]['name'] if accepted else '未知身份')
            predictions.append({**face,'match':decision})
        row=score_image(truth[original['file']],predictions,original['elapsed_ms'],protocol=config['protocol']['localization_protocol'])
        rows.append({**row,'method':original['method'],'scene':original['scene']})
    result={'protocol':declaration,'declaration_sha256':hashlib.sha256(preset.read_bytes()).hexdigest(),
            'summary':{method:aggregate([row for row in rows if row['method']==method]) for method in config['methods']}}
    (folder/'secondary-fixed-default.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    for dataset in ['cbsr-nir','yale-b']:
        folder=ROOT/'experiments/results'/('real-'+dataset)
        print(dataset,json.dumps({m:{k:v for k,v in stats.items() if k in ('confirmation_rate','unknown_far','correct','known','unknown','false_accept')} for m,stats in summarize(folder)['summary'].items()}))
