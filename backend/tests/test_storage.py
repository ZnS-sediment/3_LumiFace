"""Deletion tests always use the disposable database configured by conftest."""

import os
import time
import uuid
from pathlib import Path

import pytest
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import DATA
from app.database.session import SessionLocal
from app.main import app
from app.models.entities import FaceSample, PendingSampleDeletion, Person
from app.services.persons import delete_people, register
from app.services.storage import (
    purge_pending_samples,
    queue_sample_deletion,
    recover_sample_cleanup,
)
from test_api import enroll, photo


@pytest.mark.parametrize("failure", ["write", "chmod"])
def test_interrupted_registration_removes_partial_files_and_features(model, monkeypatch, failure):
    write_bytes = Path.write_bytes
    chmod = Path.chmod
    writes = 0

    def broken_write(path, content):
        nonlocal writes
        if path.parent == DATA / "samples":
            writes += 1
            if failure == "write" and writes == 2:
                write_bytes(path, b"partial image")
                raise OSError("simulated incomplete image write")
        return write_bytes(path, content)

    def broken_chmod(path, mode, *args, **kwargs):
        if failure == "chmod" and path.parent == DATA / "samples":
            raise OSError("simulated image permission failure")
        return chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", broken_write)
    monkeypatch.setattr(Path, "chmod", broken_chmod)
    with SessionLocal() as db:
        images = [np.full((64, 64, 3), value, np.uint8) for value in [60, 70]]
        with pytest.raises(OSError, match="simulated"):
            register(db, "中断导入", "", images, "interrupted-registration")
        assert db.scalar(select(Person.id)) is None
        assert db.scalar(select(FaceSample.id)) is None
        assert db.scalar(select(PendingSampleDeletion.path)) is None
    assert list((DATA / "samples").glob("*.png")) == []


def test_identity_deletion_keeps_downloads_and_original_photos(
    client, model, tmp_path, monkeypatch
):
    from app.api import routes

    monkeypatch.setattr(routes, "ROOT", tmp_path)
    downloads = tmp_path / "datasets"
    downloads.mkdir()
    protected = {
        downloads / "att_faces_demo.zip": b"downloaded demo archive",
        downloads / "att_lighting_simulation.zip": b"downloaded simulation archive",
        downloads / "att_lighting_three_scenes.zip": b"three scene archive",
        downloads / "original.png": photo(),
    }
    for path, content in protected.items():
        path.write_bytes(content)
    person = enroll(client).json()["data"]
    result = client.post("/api/person/batch-delete", json={"person_ids": [person["id"]]})
    assert result.status_code == 200
    assert result.json()["data"]["cleanup"] == {"deleted_files": 1, "pending_files": 0}
    assert not list((DATA / "samples").glob("*.png"))
    with SessionLocal() as db:
        assert list(db.scalars(select(FaceSample))) == []
        assert list(db.scalars(select(PendingSampleDeletion))) == []
    for path, content in protected.items():
        assert path.read_bytes() == content
    assert (
        client.get("/api/person/demo-dataset").content
        == protected[downloads / "att_faces_demo.zip"]
    )
    assert (
        client.get("/api/person/simulated-dataset").content
        == protected[downloads / "att_lighting_three_scenes.zip"]
    )


def test_failed_file_removal_is_reported_and_retried_on_restart(client, model, monkeypatch):
    person = enroll(client).json()["data"]
    with SessionLocal() as db:
        filename = db.scalar(select(FaceSample.path))
    path = DATA / "samples" / filename
    unlink = Path.unlink

    def locked(target, *args, **kwargs):
        if target == path:
            raise PermissionError("simulated filesystem failure")
        return unlink(target, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked)
        result = client.delete(f"/api/person/{person['id']}")
        assert result.status_code == 200
        assert result.json()["data"]["cleanup"] == {"deleted_files": 0, "pending_files": 1}
        assert path.exists()
        with SessionLocal() as db:
            assert db.get(Person, person["id"]) is None
            assert db.scalar(select(FaceSample.id)) is None
            assert db.get(PendingSampleDeletion, filename) is not None
    with TestClient(app) as restarted:
        assert restarted.get("/api/person").json()["data"] == []
    assert not path.exists()
    with SessionLocal() as db:
        assert db.get(PendingSampleDeletion, filename) is None


def test_database_failure_never_removes_registered_files(client, model, monkeypatch):
    person = enroll(client).json()["data"]
    with SessionLocal() as db:
        filename = db.scalar(select(FaceSample.path))

        def failed_commit():
            raise RuntimeError("simulated database commit failure")

        monkeypatch.setattr(db, "commit", failed_commit)
        with pytest.raises(RuntimeError, match="database commit"):
            delete_people(db, [person["id"]])
        db.rollback()
    assert (DATA / "samples" / filename).exists()
    with SessionLocal() as db:
        assert db.get(Person, person["id"]) is not None
        assert db.scalar(select(FaceSample.path)) == filename
        assert db.scalar(select(PendingSampleDeletion.path)) is None


def test_recovery_removes_only_old_unreferenced_registration_copies(client, model):
    enroll(client)
    with SessionLocal() as db:
        active = DATA / "samples" / db.scalar(select(FaceSample.path))
    abandoned = DATA / "samples" / f"{uuid.uuid4().hex}.png"
    recent = DATA / "samples" / f"{uuid.uuid4().hex}.png"
    unrelated = DATA / "samples" / "my-original.png"
    for path in [abandoned, recent, unrelated]:
        path.write_bytes(photo())
    for path in [active, abandoned, unrelated]:
        os.utime(path, (time.time() - 7200,) * 2)
    with SessionLocal() as db:
        assert recover_sample_cleanup(db) == {"deleted_files": 1, "pending_files": 0}
        # Even an incorrect stale job must never remove a live registration.
        queue_sample_deletion(db, [active.name])
        db.commit()
        assert purge_pending_samples(db) == {"deleted_files": 0, "pending_files": 0}
    assert active.exists() and recent.exists() and unrelated.exists()
    assert not abandoned.exists()


def test_invalid_sample_path_rejects_entire_deletion(client, model):
    person = enroll(client).json()["data"]
    outside = DATA / "outside.png"
    outside.write_bytes(photo())
    with SessionLocal() as db:
        db.scalar(select(FaceSample)).path = "../outside.png"
        db.commit()
    result = client.delete(f"/api/person/{person['id']}")
    assert result.status_code == 409
    assert outside.exists()
    with SessionLocal() as db:
        assert db.get(Person, person["id"]) is not None
        assert db.scalar(select(PendingSampleDeletion.path)) is None


def test_cleanup_rejects_symlinked_sample_directory(client, tmp_path, monkeypatch):
    from app.services import storage

    outside = tmp_path / "outside"
    outside.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "samples").symlink_to(outside, target_is_directory=True)
    filename = f"{uuid.uuid4().hex}.png"
    original = outside / filename
    original.write_bytes(photo())
    monkeypatch.setattr(storage, "DATA", runtime)
    with SessionLocal() as db:
        queue_sample_deletion(db, [filename])
        db.commit()
        assert purge_pending_samples(db) == {"deleted_files": 0, "pending_files": 1}
    assert original.exists()
