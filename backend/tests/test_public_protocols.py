import importlib.util
from pathlib import Path
import zipfile

spec=importlib.util.spec_from_file_location('public_benchmark',Path(__file__).resolve().parents[2]/'experiments/scripts/benchmark_public.py')
benchmark=importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_nonconsecutive_cbsr_ids_are_split_by_actual_ids(tmp_path):
    ids=[i for i in range(1,203) if i not in {33,45,87,102,150}]
    assert len(ids)==197
    for kind,count in [('gallery',8),('probe',12)]:
        rows=[f'{identity:04d}-{index+(20 if kind=="probe" else 0):02d}-a.bmp,100,200,200,200' for identity in ids for index in range(count)]
        (tmp_path/f'{kind}-groundtruth.txt').write_text('\n'.join(rows))
    protocol,enrollment,calibration,test=benchmark.cbsr_protocol(tmp_path)
    benchmark.validate_split(enrollment,calibration,test)
    assert len(enrollment)==800 and len(calibration)==560 and len(test)==1484
    assert len(protocol['roles']['known_subjects'])==100
    assert 33 not in protocol['roles']['known_subjects']
    assert not protocol['scene_evidence']['infrared']['night_confirmed']
    known=set(protocol['roles']['known_subjects'])
    assert all((item['faces'][0]['person_id'] in known) if int(item['file'].split('/')[-1].split('-')[0]) in known else item['faces'][0]['person_id'] is None for item in calibration+test)


def test_yale_does_not_relabel_rear_side_as_field_backlight(tmp_path):
    archive=tmp_path/'yale.zip'
    suffixes=['A+000E+00','A+005E+10','A-005E+10','A+000E+20','A+110E+15','A+050E+00','_Ambient']
    with zipfile.ZipFile(archive,'w') as package:
        for identity in list(range(1,11))+[33]:
            for suffix in suffixes:
                name=f'CroppedYale/yaleB{identity:02d}/yaleB{identity:02d}_P00{suffix}.pgm'
                package.writestr(name,b'filename-only protocol fixture')
                package.writestr('__MACOSX/'+name,b'not an image')
    protocol,enrollment,calibration,test=benchmark.yale_protocol(archive)
    benchmark.validate_split(enrollment,calibration,test)
    assert len(enrollment)==24
    assert all('yaleB33' not in item['file'] for item in enrollment+calibration+test)
    assert any(item['scene']=='controlled_rear_side' for item in calibration+test)
    assert not any(item['scene']=='backlight' for item in calibration+test)
    assert protocol['capture_independence']=='condition_disjoint'


def test_pilot_is_fixed_before_scores_and_keeps_disjoint_unknowns(tmp_path):
    ids=[i for i in range(1,203) if i not in {33,45,87,102,150}]
    for kind,count in [('gallery',8),('probe',12)]:
        rows=[f'{identity:04d}-{index+(20 if kind=="probe" else 0):02d}-a.bmp,100,200,200,200' for identity in ids for index in range(count)]
        (tmp_path/f'{kind}-groundtruth.txt').write_text('\n'.join(rows))
    protocol,enrollment,calibration,test=benchmark.cbsr_protocol(tmp_path,'pilot')
    benchmark.validate_split(enrollment,calibration,test)
    assert [len(x) for x in (enrollment,calibration,test)]==[80,70,200]
    assert len(protocol['roles']['known_subjects'])==20
    assert sum(item['faces'][0]['person_id'] is not None for item in test)==100
    assert sum(item['faces'][0]['person_id'] is None for item in test)==100
