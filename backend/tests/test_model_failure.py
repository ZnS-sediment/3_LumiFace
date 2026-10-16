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
