import importlib.util
import json
from pathlib import Path
import cv2
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('field_audit',Path(__file__).resolve().parents[2]/'scripts/audit_field_data.py')
field=importlib.util.module_from_spec(spec)
spec.loader.exec_module(field)


def config(tmp_path):
    protocol={'capture_independence':'session_disjoint','scene_evidence':{scene:{'source':'fixture capture log',
        'annotation_basis':'manual_capture_log','modality':'nir' if scene=='infrared' else 'rgb',
        'active_illumination':True,'night_confirmed':True,'backlight_confirmed':True,'low_light_confirmed':True}
        for scene in ['normal','low_light','backlight','infrared']}}
    roles=['gallery','calibration','calibration','test','test']
    identities=[1,1,None,1,None]
    subjects=['known','known','unknown-cal','known','unknown-test']
    images=[]
    for index,role in enumerate(roles):
        name=f'{index}.png'
        cv2.imwrite(str(tmp_path/name),np.full((64,64,3),50+index,np.uint8))
        images.append({'file':name,'role':role,'scene':'normal','capture_id':role+'-session',
                       'faces':[{'bbox':[8,8,56,56],'person_id':identities[index],'subject':subjects[index]}]})
    payload={'name':'unit test only','source':'test fixture','license':'fixture','protocol':protocol,'images':images}
    path=tmp_path/'collection.json'
    path.write_text(json.dumps(payload))
    return path,payload


def test_audit_exports_real_protocol_format_but_flags_insufficient_samples(tmp_path):
    path,_=config(tmp_path)
    result=field.audit(path,tmp_path/'output',export=True)
    assert result['errors']==[]
    assert not result['ready_for_target_assessment'] and result['coverage_gaps']
    assert next(g for g in result['coverage_gaps'] if g['split']=='calibration' and g['scene']=='normal')['known_subjects']==1
    assert (tmp_path/'output/calibration-1.zip').exists()
    assert (tmp_path/'output/test-1.zip').exists()


def test_capture_leakage_duplicate_pixels_and_thermal_mislabel_block_export(tmp_path):
    path,payload=config(tmp_path)
    payload['images'][3]['capture_id']='gallery-session'
    payload['images'][3]['file']='0.png'
    payload['protocol']['scene_evidence']['infrared']['modality']='lwir'
    path.write_text(json.dumps(payload))
    result=field.audit(path,tmp_path/'output')
    assert any('会话跨划分' in message for message in result['errors'])
    assert any('像素重复' in message for message in result['errors'])
    assert any('近红外' in message for message in result['errors'])
    with pytest.raises(ValueError):field.audit(path,tmp_path/'output',export=True)


def test_no_data_never_becomes_a_completed_validation(tmp_path):
    path=tmp_path/'empty.json'
    path.write_text(json.dumps({'images':[]}))
    result=field.audit(path,tmp_path/'output')
    assert not result['ready_for_target_assessment']
    assert not any(result['roles'].values()) and result['errors']


def test_field_audit_requires_normal_evidence_and_consistent_identity_labels(tmp_path):
    path,payload=config(tmp_path)
    del payload['protocol']['scene_evidence']['normal']
    payload['images'][3]['faces'][0]['subject']='same-person-renamed'
    path.write_text(json.dumps(payload))
    result=field.audit(path,tmp_path/'output')
    assert any('normal' in message for message in result['errors'])
    assert any('多个 subject' in message for message in result['errors'])
    assert not result['ready_for_target_assessment']


def test_export_shards_by_actual_bytes_preserving_all_queries():
    rows=[{'file':str(i)} for i in range(3)]
    blobs={str(i):b'12345' for i in range(3)}
    chunks=list(field.query_shards(rows,blobs,max_bytes=9))
    assert chunks==[[rows[0]],[rows[1]],[rows[2]]]
    assert all(sum(len(blobs[r['file']]) for r in chunk)<=9 for chunk in chunks)
