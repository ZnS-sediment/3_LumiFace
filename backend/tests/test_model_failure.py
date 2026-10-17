from pathlib import Path
import pytest
from app.algorithms import face_detector
from app.core.errors import AppError


def test_missing_weights_never_fall_back_to_fake_model(monkeypatch,tmp_path):
    monkeypatch.setattr(face_detector,'MODEL_ROOT',tmp_path)
    engine=face_detector.FaceEngine()
    with pytest.raises(AppError) as error:engine.load()
    assert error.value.status==503
    assert not engine.status()['ready']


def test_detector_size_is_explicit_and_invalid_values_rejected(monkeypatch):
    monkeypatch.setenv('LUMIFACE_DETECTION_SIZE','320')
    engine=face_detector.FaceEngine()
    assert engine.status()['detection_size']==320
    monkeypatch.setenv('LUMIFACE_DETECTION_SIZE','123')
    with pytest.raises(ValueError):face_detector.FaceEngine()
