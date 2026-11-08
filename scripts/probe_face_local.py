#!/usr/bin/env python3
"""Develop face-local normalization using old identities' previously unused photos 6–8."""
import argparse,hashlib,io,json,os,sys,tarfile,tempfile,zipfile
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
WORK=ROOT/'work/face-local-v4'
METHODS={'backlight':'clahe','uneven':'retinex','low_light':'gamma'}


def main():
 p=argparse.ArgumentParser();p.add_argument('--part',choices=['development','validation'],required=True);a=p.parse_args()
 import cv2,numpy as np
 from prepare_lfw_demo import single_person_image
 from prepare_lfw_lighting import simulate
 with tempfile.TemporaryDirectory(prefix='lumiface-local-probe-') as temporary:
  os.environ['LUMIFACE_DATA']=temporary;os.environ['MPLCONFIGDIR']=temporary
  from app.algorithms.face_detector import engine
  from app.algorithms.face_recognizer import unit
  from app.algorithms.enhancement import enhance
  from app.schemas.contracts import EnhanceOptions
  from insightface.utils.face_align import norm_crop
  engine.load()
  references=json.loads((ROOT/'work/lfw-400/references.json').read_text())
  assert references['model_fingerprint']==engine.fingerprint
  gallery_names=set(references['people'])
  with zipfile.ZipFile(ROOT/'datasets/lfw_120_lighting.zip') as z:
   old={n.split('/')[-2].removeprefix('LFW_') for n in z.namelist() if '/gallery/' in n}
  groups=defaultdict(list)
  with tarfile.open(ROOT/'datasets/raw/lfw/lfw-funneled.tgz') as source:
   for m in source.getmembers():
    if m.isfile() and m.name.endswith('.jpg'):groups[m.name.split('/')[-2]].append(m)
   known=sorted((n for n in old if len(groups[n])>=8),key=lambda n:hashlib.sha256(n.encode()).hexdigest())[:48]
   unknown=sorted(set(groups)-gallery_names,key=lambda n:hashlib.sha256(n.encode()).hexdigest())[:60]
   names=known[:24]+unknown[:30] if a.part=='development' else known[24:]+unknown[30:]
   protocol={'development_known':known[:24],'validation_known':known[24:],'development_unknown':unknown[:30],'validation_unknown':unknown[30:],'query_indices':[6,7,8],'threshold':.435,'gallery_fingerprint':engine.fingerprint,'source_rule':'Photos 6–8 of old-package identities only. No 280-new-package identities or query photos used for development.'}
   proto=WORK/'development-protocol.json'
   if proto.exists():assert json.loads(proto.read_text())==protocol
   else:proto.write_text(json.dumps(protocol,indent=2))
   raws={}
   for n in names:
    for m in sorted(groups[n],key=lambda m:m.name)[5:8] if n in known else sorted(groups[n],key=lambda m:m.name)[:1]:
     raws[m.name]=single_person_image(source.extractfile(m).read())
  output=WORK/(a.part+'.jsonl');done=set()
  if output.exists():done={(r['source'],r['scene']) for r in map(json.loads,output.read_text().splitlines())}
  with output.open('a') as stream:
   for filename,content in sorted(raws.items()):
    for scene,method in METHODS.items():
     if (filename,scene) in done:continue
     seed=int(hashlib.sha256(filename.encode()).hexdigest()[:8],16)
     rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(content,np.uint8),1),cv2.COLOR_BGR2RGB)
     image=cv2.cvtColor(simulate(rgb,scene,seed),cv2.COLOR_RGB2BGR)
     global_image,_=enhance(image,EnhanceOptions(method=method,auto_parameters=True))
     faces=engine.detect_faces(image)
     extra=[]
     from app.algorithms.metrics import iou
     for face in engine.detect_faces(global_image):
      if not any(iou(face['bbox'],f['bbox'])>=.3 for f in faces+extra):extra.append(face)
     rows=[]
     for face in faces+extra:
      crop=norm_crop(image,np.array(face['keypoints'],np.float32))
      global_crop=norm_crop(global_image,np.array(face['keypoints'],np.float32))
      local,_=enhance(crop,EnhanceOptions(method=method,auto_parameters=True))
      balanced,_=enhance(local,EnhanceOptions(method='gamma',auto_parameters=True))
      views={'raw':crop,'global':global_crop,'local':local,'balanced':balanced,'flip_raw':crop[:,::-1].copy(),'flip_local':local[:,::-1].copy(),'flip_balanced':balanced[:,::-1].copy()}
      vectors=engine._app.models['recognition'].get_feat(list(views.values()))
      rows.append({**face,'views':{n:unit(v).tolist() for n,v in zip(views,vectors)},'raw_detected':face in faces})
     record={'source':filename,'person':'LFW_'+filename.split('/')[-2] if filename.split('/')[-2] in known else None,'unknown_subject':filename.split('/')[-2] if filename.split('/')[-2] not in known else None,'scene':scene,'method':method,'faces':rows}
     stream.write(json.dumps(record)+'\n');stream.flush();done.add((filename,scene))
     if len(done)%15==0:print(a.part,len(done),'/306',flush=True)
  print('Done',a.part,len(done),flush=True)

if __name__=='__main__':main()
