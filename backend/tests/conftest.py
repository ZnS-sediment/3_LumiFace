"""Test database and predictable test doubles are isolated from the application runtime."""

import os
import tempfile
import shutil
import pytest

_TEMP = tempfile.TemporaryDirectory(prefix="lumiface-tests-")
os.environ["LUMIFACE_DATA"] = _TEMP.name
from app.database.session import Base, engine
from app.main import app
from app.core.config import DATA
from app.algorithms.face_detector import engine as face_engine
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    for name in ["samples", "datasets"]:
        folder = DATA / name
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(mode=0o700)
    yield


@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def model(monkeypatch):
    """Explicit unit-test fixture, never used by app or benchmark scripts."""

    def load():
        face_engine.fingerprint = "unit-test-model"

    def infer(image):
        value = int(image[0, 0, 0])
        if value == 0:
            return []
        embedding = [1.0, 0.0, 0.0] if value < 128 else [0.0, 1.0, 0.0]
        face = {
            "bbox": [8.0, 8.0, 56.0, 56.0],
            "keypoints": [[20.0, 25.0], [43.0, 25.0], [32.0, 35.0], [23.0, 45.0], [41.0, 45.0]],
            "confidence": 0.99,
            "embedding": embedding,
        }
        return [face, face.copy()] if value == 255 else [face]

    monkeypatch.setattr(face_engine, "load", load)
    monkeypatch.setattr(face_engine, "infer", infer)
    monkeypatch.setattr(face_engine, "detect_faces", lambda image: [{k: v for k, v in f.items() if k != "embedding"} for f in face_engine.infer(image)])
    monkeypatch.setattr(
        face_engine, "aligned_embeddings",
        lambda image, faces: [infer(image)[0]["embedding"] for _ in faces],
    )
    monkeypatch.setattr(
        face_engine, "local_embeddings",
        lambda image, faces, method: [[infer(image)[0]["embedding"]] * 2 for _ in faces],
    )
    load()
    return face_engine
