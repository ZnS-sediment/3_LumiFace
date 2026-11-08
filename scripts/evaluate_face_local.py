#!/usr/bin/env python3
"""Compare frozen face-local candidate mixtures on development or held-out data."""
import argparse,json
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
STRATEGIES={
 'v3':{'raw':.7,'global':.3},
 'local30':{'raw':.7,'local':.3},
 'local50':{'raw':.5,'local':.5},
 'local70':{'raw':.3,'local':.7},
 'balanced30':{'raw':.7,'balanced':.3},
 'balanced50':{'raw':.5,'balanced':.5},
 'mirror':{'raw':.5,'flip_raw':.5},
 'local_mirror30':{'raw':.7,'local':.15,'flip_local':.15},
 'local_mirror50':{'raw':.5,'local':.25,'flip_local':.25},
 'balanced_mirror50':{'raw':.5,'balanced':.25,'flip_balanced':.25},
 'balanced_mirror70':{'raw':.3,'balanced':.35,'flip_balanced':.35},
}

# Second development pass adds original-image symmetry; no package scores are
# available to this evaluator. Keep the first frozen selection as audit evidence.
for kind in ('local', 'balanced'):
 for raw_weight in (.3, .5, .7):
  STRATEGIES[f'{kind}_four_{int(raw_weight * 100)}'] = {
   'raw': raw_weight / 2, 'flip_raw': raw_weight / 2,
   kind: (1 - raw_weight) / 2, 'flip_' + kind: (1 - raw_weight) / 2,
  }

for weight in (.3, .5, .7, 1.):
 STRATEGIES[f'global_{int(weight * 100)}'] = {'raw': 1 - weight, 'global': weight}

def main():
 p=argparse.ArgumentParser();p.add_argument('--part',required=True,choices=['development','validation']);a=p.parse_args()
 path=ROOT/'work/face-local-v4'/f'{a.part}.jsonl'
 rows=[json.loads(line) for line in path.read_text().splitlines()]
 refs=json.loads((ROOT/'work/lfw-400/references.json').read_text())['people']
 names=[r['name'] for r in refs.values()];matrix=np.array([r['embedding'] for r in refs.values()],np.float32)
 matrix/=np.linalg.norm(matrix,axis=1)[:,None]
 stats=defaultdict(lambda:{'known':0,'correct':0,'unknown':0,'false_accept':0,'scores':[],'margins':[]})
 for r in rows:
  for strategy,weights in STRATEGIES.items():
   decisions=[];truth=-1;margin=-1
   for face in r['faces']:
    vector=np.sum([w*np.array(face['views'][name],np.float32) for name,w in weights.items()],axis=0)
    if strategy=='v3' and not face['raw_detected']:vector=np.array(face['views']['global'],np.float32)
    vector/=np.linalg.norm(vector);scores=np.clip(matrix@vector,-1,1);top=int(scores.argmax())
    if r['person'] is not None:
     idx=names.index(r['person']);truth=max(truth,float(scores[idx]));margin=max(margin,float(scores[idx]-np.max(np.delete(scores,idx))))
    if scores[top]>=.435:decisions.append(names[top])
   s=stats[r['method']+'/'+strategy]
   if r['person'] is None:s['unknown']+=1;s['false_accept']+=bool(decisions)
   else:s['known']+=1;s['correct']+=r['person'] in decisions;s['scores'].append(truth);s['margins'].append(margin)
 report={}
 for k,s in stats.items():
  scores=s.pop('scores');margins=s.pop('margins')
  s.update(mean_score=float(np.mean(scores)),p05_score=float(np.percentile(scores,5)),min_score=min(scores),p05_margin=float(np.percentile(margins,5)))
  report[k]=s
 (ROOT/'work/face-local-v4'/f'{a.part}-comparison.json').write_text(json.dumps(report,indent=2))
 for method in ['clahe','retinex','gamma']:
  for name in STRATEGIES:
   s=report[method+'/'+name];print(method,name,f"{s['correct']}/{s['known']}",f"FAR {s['false_accept']}/{s['unknown']}",f"p05 {s['p05_score']:.4f} mean {s['mean_score']:.4f} min {s['min_score']:.4f}")
if __name__=='__main__':main()
