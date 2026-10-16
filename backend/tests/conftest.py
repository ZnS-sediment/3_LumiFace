"""Test database and predictable test doubles are isolated from the application runtime."""
import os
import tempfile
from pathlib import Path
import numpy as np
import pytest

_TEMP = tempfile.TemporaryDirectory(prefix='lumiface-tests-')
os.environ['LUMIFACE_DATA'] = _TEMP.name
from app.database.session import Base, engine, SessionLocal
from app.main import app
from app.algorithms.face_detector import engine as face_engine
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def model(monkeypatch):
    """Explicit unit-test fixture, never used by app or benchmark scripts."""
    def load():
        face_engine.fingerprint = 'unit-test-model'
    def infer(image):
        value = int(image[0, 0, 0])
        if value == 0:
            return []
        embedding = [1., 0., 0.] if value < 128 else [0., 1., 0.]
        face = {'bbox': [8., 8., 56., 56.], 'keypoints': [[20.,25.],[43.,25.],[32.,35.],[23.,45.],[41.,45.]], 'confidence': .99, 'embedding': embedding}
        return [face, face.copy()] if value == 255 else [face]
    monkeypatch.setattr(face_engine, 'load', load)
    monkeypatch.setattr(face_engine, 'infer', infer)
    load()
    return face_engine
