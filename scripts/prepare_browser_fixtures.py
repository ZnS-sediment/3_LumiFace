#!/usr/bin/env python3
"""Explicit synthetic fixtures for browser integration, separate from real datasets."""
import json
import zipfile
from pathlib import Path
import cv2
import matplotlib
from skimage import data
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work'
WORK.mkdir(exist_ok=True)
image=cv2.cvtColor(data.astronaut(),cv2.COLOR_RGB2BGR)
cv2.imwrite(str(WORK/'astronaut.png'),image)
hopper=cv2.imread(str(Path(matplotlib.get_data_path())/'sample_data'/'grace_hopper.jpg'))
cv2.imwrite(str(WORK/'hopper.png'),hopper)
probe=cv2.convertScaleAbs(image,alpha=.85)
manifest={'name':'浏览器流程验证数据','split':'test','source':'scikit-image astronaut derivative, integration only','license':'NASA public domain sample','real_capture':False,'items':[{'file':'test.png','scene':'normal','capture_id':'browser-synthetic-derivative','faces':[{'bbox':[175,55,277,185],'person_id':1,'subject':'reference-A'}]}]}
with zipfile.ZipFile(WORK/'browser-dataset.zip','w') as archive:
    archive.writestr('manifest.json',json.dumps(manifest))
    archive.writestr('test.png',cv2.imencode('.png',probe)[1].tobytes())
