import pytest
from app.algorithms.metrics import score_image,aggregate,calibrate


def prediction(box,person,score=.9):
    return {'bbox':box,'confidence':.9,'match':{'person_id':person,'confirmed':person is not None,'similarity':score,'candidates':[{'person_id':person}]}}


def test_detection_one_to_one_and_end_to_end_failure():
    truth=[{'bbox':[0,0,20,20],'person_id':1,'subject':'a'}, {'bbox':[40,40,60,60],'person_id':2,'subject':'b'}]
    predictions=[prediction([0,0,20,20],1),prediction([0,0,20,20],1)]
    row=score_image(truth,predictions,10)
    assert (row['tp'],row['fp'],row['fn'])==(1,1,1)
    assert aggregate([row])['confirmation_rate']==.5
    assert aggregate([row])['recognition_accuracy']==1


def test_false_accept_and_missing_detection_stays_in_denominator():
    truth=[{'bbox':[0,0,20,20],'person_id':None,'subject':'unknown'}]
    accepted=score_image(truth,[prediction([0,0,20,20],1)],10)
    missed=score_image(truth,[],10)
    assert aggregate([accepted,missed])['unknown_far']==.5
    assert aggregate([accepted,missed])['conditional_unknown_far']==1
    assert aggregate([accepted])['confirmation_rate'] is None


def test_pooled_counts_not_average_of_groups():
    good=score_image([{'bbox':[0,0,20,20],'person_id':1,'subject':'a'}],[prediction([0,0,20,20],1)],5)
    missed=score_image([{'bbox':[0,0,20,20],'person_id':1,'subject':'a'}],[],7)
    assert aggregate([good]+[missed]*9)['confirmation_rate']==.1
    assert aggregate([])['recall'] is None


def test_calibration_strict_threshold_and_ties():
    data=[{'known':True,'score':.8,'candidate_id':1,'truth_person_id':1}, {'known':True,'score':.6,'candidate_id':1,'truth_person_id':1}, {'known':False,'score':.6,'candidate_id':1,'truth_person_id':None}]
    result=calibrate(data,0)
    assert result['threshold']>.6
    assert result['confirmation_rate']==.5 and result['observed_far']==0
    with pytest.raises(ValueError):calibrate(data[:2],.01)
