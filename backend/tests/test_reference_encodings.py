"""Backbone upgrades retain original samples and cache compatible derived features."""
import copy
import pytest
from sqlalchemy import select, func
from app.algorithms.face_detector import engine
from app.core.config import DATA
from app.core.errors import AppError
from app.database.session import SessionLocal
from app.models.entities import FaceSample, FaceEncoding
from app.services.persons import gallery, delete_people
from test_api import enroll, photo


def upgrade(monkeypatch):
    monkeypatch.setattr(engine, 'fingerprint', 'upgraded-unit-model')
    monkeypatch.setattr(engine, 'compatible_fingerprints', {'unit-test-model'})
    monkeypatch.setattr(engine, 'load', lambda: None)


def test_gallery_reencodes_once_preserves_original_and_cleans_on_delete(client, model, monkeypatch):
    assert enroll(client).status_code == 200
    with SessionLocal() as db:
        sample = db.scalar(select(FaceSample))
        original_embedding = copy.deepcopy(sample.embedding)
        original_fingerprint = sample.model_fingerprint
        path = DATA / 'samples' / sample.path
        original_bytes = path.read_bytes()
    infer = model.infer
    calls = []
    def new_infer(image):
        calls.append(1)
        return [{**f, 'embedding': [0., 1., 0.]} for f in infer(image)]
    upgrade(monkeypatch)
    monkeypatch.setattr(model, 'infer', new_infer)
    with SessionLocal() as db:
        assert gallery(db)[0]['embedding'] == [0., 1., 0.]
        assert calls == [1]
        sample = db.scalar(select(FaceSample))
        assert sample.embedding == original_embedding
        assert sample.model_fingerprint == original_fingerprint
        assert path.read_bytes() == original_bytes
        assert db.scalar(select(func.count(FaceEncoding.sample_id))) == 1
    with SessionLocal() as db:
        assert gallery(db)[0]['embedding'] == [0., 1., 0.]
        assert calls == [1]
        delete_people(db, [1])
        assert db.scalar(select(func.count(FaceEncoding.sample_id))) == 0
        assert not path.exists()


def test_unsupported_fingerprint_does_not_silently_migrate(client, model, monkeypatch):
    enroll(client)
    upgrade(monkeypatch)
    monkeypatch.setattr(engine, 'compatible_fingerprints', set())
    with SessionLocal() as db, pytest.raises(AppError, match='模型指纹'):
        gallery(db)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(FaceEncoding.sample_id))) == 0


def test_changed_registration_photo_cannot_generate_new_encoding(client, model, monkeypatch):
    enroll(client)
    upgrade(monkeypatch)
    with SessionLocal() as db:
        sample = db.scalar(select(FaceSample))
        (DATA / 'samples' / sample.path).write_bytes(photo(180))
        with pytest.raises(AppError, match='校验不一致'):
            gallery(db)
        assert db.scalar(select(func.count(FaceEncoding.sample_id))) == 0
