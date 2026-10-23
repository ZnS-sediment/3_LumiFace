import io
import json
import zipfile
import cv2
import numpy as np
import pytest
from app.core.config import DATA


def photo(value=60):
    return cv2.imencode(".png", np.full((64, 64, 3), value, np.uint8))[1].tobytes()


def enroll(client, value=60, name="测试人员", capture="enroll-1"):
    return client.post(
        "/api/person/register",
        data={"name": name, "capture_id": capture},
        files=[("files", ("ref.png", photo(value), "image/png"))],
    )


def dataset_zip(
    value=70, split="test", capture="test-1", person_id=1, subject="known-1", scene="normal"
):
    manifest = {
        "name": "测试夹具，不是真实性能数据",
        "split": split,
        "source": "unit tests",
        "license": "test fixture",
        "real_capture": False,
        "items": [
            {
                "file": "image.png",
                "scene": scene,
                "capture_id": capture,
                "faces": [{"bbox": [8, 8, 56, 56], "person_id": person_id, "subject": subject}],
            }
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("image.png", photo(value))
    return buffer.getvalue()


def test_overview_and_invalid_upload(client):
    assert client.get("/api/system/overview").json()["data"]["persons"] == 0
    response = client.post(
        "/api/enhance/analyze", files={"file": ("fake.png", b"not an image", "image/png")}
    )
    assert response.status_code == 400
    response = client.post(
        "/api/enhance/process",
        files={"file": ("x.png", photo(), "image/png")},
        data={"options": '{"gamma":0}'},
    )
    assert response.status_code == 422
    response = client.post("/api/enhance/process", files={"file": ("x.png", photo(), "image/png")})
    assert response.status_code == 200 and response.json()["data"]["enhanced"].startswith(
        "data:image/png"
    )


def test_backend_root_redirects_to_ui_without_masking_unknown_api_routes(client):
    from app.main import FRONTEND_ORIGIN

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == FRONTEND_ORIGIN + "/"
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/api/system/overview").status_code == 200


@pytest.mark.parametrize(
    "route,archive_name,prepare_script",
    [
        ("demo-dataset", "att_faces_demo.zip", "prepare_att_faces_demo.py"),
        ("simulated-dataset", "att_lighting_three_scenes.zip", "prepare_three_scene_demo.py"),
        ("lfw-dataset", "lfw_120_demo.zip", "prepare_lfw_demo.py"),
    ],
)
def test_demo_dataset_download_and_missing_archive(
    client, monkeypatch, tmp_path, route, archive_name, prepare_script
):
    from app.api import routes

    monkeypatch.setattr(routes, "ROOT", tmp_path)
    archive = tmp_path / "datasets" / archive_name
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("att_faces_demo/README.zh-CN.md", "AT&T 公开演示数据")
    response = client.get("/api/person/" + route)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert archive_name in response.headers["content-disposition"]
    assert response.content == archive.read_bytes()
    archive.unlink()
    response = client.get("/api/person/" + route)
    assert response.status_code == 404
    assert prepare_script in response.json()["message"]


def test_person_list_sorts_numeric_ids_ascending_including_search(client):
    from app.database.session import SessionLocal
    from app.models.entities import Person

    with SessionLocal() as db:
        db.add_all(
            [
                Person(id=10, name="排序人员10"),
                Person(id=2, name="排序人员2"),
                Person(id=1, name="其他人员"),
            ]
        )
        db.commit()
    assert [p["id"] for p in client.get("/api/person").json()["data"]] == [1, 2, 10]
    assert [p["id"] for p in client.get("/api/person?q=排序").json()["data"]] == [2, 10]


def test_registration_atomic_multi_photo_and_delete(client, model):
    response = client.post(
        "/api/person/register",
        data={"name": "失败注册", "capture_id": "e"},
        files=[
            ("files", ("a.png", photo(60), "image/png")),
            ("files", ("b.png", photo(0), "image/png")),
        ],
    )
    assert response.status_code == 422
    assert client.get("/api/person").json()["data"] == []
    response = enroll(client)
    assert response.status_code == 200
    pid = response.json()["data"]["id"]
    detail = client.get(f"/api/person/{pid}").json()["data"]
    assert "embedding" not in detail["samples"][0]
    image_url = detail["samples"][0]["image_url"]
    assert client.get(image_url).status_code == 200
    assert enroll(client).status_code == 409
    assert (
        client.patch(f"/api/person/{pid}", json={"name": "新姓名", "note": "更新"}).status_code
        == 200
    )
    assert client.delete(f"/api/person/{pid}").status_code == 200
    assert client.get(image_url).status_code == 404
    assert not list((DATA / "samples").glob("*.png"))


@pytest.mark.parametrize("value", [0, 255])
def test_reject_no_face_or_multiple_faces(client, model, value):
    assert enroll(client, value).status_code == 422


def test_recognition_and_detection(client, model):
    enroll(client)
    response = client.post(
        "/api/recognition/identify",
        data={"options": '{"method":"original"}'},
        files={"file": ("unknown.png", photo(180), "image/png")},
    )
    assert response.status_code == 200
    assert not response.json()["data"]["confirmed"]
    response = client.post(
        "/api/recognition/verify",
        data={"person_id": 1, "options": '{"method":"original"}'},
        files={"file": ("known.png", photo(70), "image/png")},
    )
    assert response.json()["data"]["confirmed"]
    response = client.post("/api/face/detect", files={"file": ("x.png", photo(80), "image/png")})
    assert response.status_code == 200 and response.json()["data"]["original"]["count"] == 1
    assert client.get("/api/system/overview").json()["data"]["detections"] == 1
    assert (
        client.post(
            "/api/recognition/identify",
            data={"threshold": "nan"},
            files={"file": ("x.png", photo(), "image/png")},
        ).status_code
        == 422
    )


def test_dataset_leakage_and_unknown_subject_split(client, model):
    enroll(client)

    def upload(raw):
        return client.post(
            "/api/dataset/import", files={"file": ("data.zip", raw, "application/zip")}
        )

    assert upload(dataset_zip(value=60)).status_code == 409
    assert upload(dataset_zip(capture="enroll-1")).status_code == 409
    assert (
        upload(
            dataset_zip(
                value=80, split="calibration", capture="cal-1", person_id=None, subject="u1"
            )
        ).status_code
        == 200
    )
    assert upload(dataset_zip(value=80, capture="test-2")).status_code == 409
    assert upload(dataset_zip(value=90, capture="cal-1")).status_code == 409
    assert upload(dataset_zip(value=90, person_id=None, subject="u1")).status_code == 409
    assert upload(dataset_zip(value=100)).status_code == 200


def test_archive_traversal_rejected(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../outside.txt", "bad")
    response = client.post(
        "/api/dataset/import", files={"file": ("bad.zip", buffer.getvalue(), "application/zip")}
    )
    assert response.status_code == 400


def test_batch_persistence_metrics_csv_and_preview(client, model):
    enroll(client)
    uploaded = client.post(
        "/api/dataset/import", files={"file": ("data.zip", dataset_zip(), "application/zip")}
    )
    did = uploaded.json()["data"]["id"]
    response = client.post(
        "/api/experiment/run",
        json={"dataset_id": did, "methods": ["original", "gamma"], "threshold": 0.45},
    )
    assert response.status_code == 200
    eid = response.json()["data"]["id"]
    record = client.get(f"/api/experiment/{eid}").json()["data"]
    assert record["status"] == "completed", record["error"]
    assert record["summary"]["original"]["overall"]["confirmation_rate"] == 1
    assert record["summary"]["original"]["targets"]["infrared"]["status"] == "未评估"
    assert record["summary"]["original"]["targets"]["overall"]["status"] == "未评估"
    assert client.get(f"/api/experiment/{eid}/csv").text.count("\n") == 3
    rows = client.get(f"/api/experiment/{eid}/results").json()["data"]
    assert client.get(f"/api/experiment/{eid}/preview/{rows[0]['id']}").status_code == 200
    assert client.delete(f"/api/dataset/{did}").status_code == 409
    assert client.delete(f"/api/experiment/{eid}").status_code == 200
    assert client.delete(f"/api/dataset/{did}").status_code == 200


def test_foreign_origin_and_private_paths(client):
    assert client.get("/api/person", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/runtime/lumiface.db").status_code == 404
    assert client.get("/api/person/999").status_code == 404


def test_calibration_is_frozen_and_gallery_changes_are_rejected(client, model):
    enroll(client)
    manifest = {
        "name": "calibration fixture",
        "split": "calibration",
        "source": "unit test",
        "license": "fixture",
        "real_capture": False,
        "items": [
            {
                "file": "known.png",
                "scene": "normal",
                "capture_id": "cal-a",
                "faces": [{"bbox": [8, 8, 56, 56], "person_id": 1, "subject": "known-a"}],
            },
            {
                "file": "unknown.png",
                "scene": "normal",
                "capture_id": "cal-u",
                "faces": [{"bbox": [8, 8, 56, 56], "person_id": None, "subject": "unknown-cal"}],
            },
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("known.png", photo(70))
        z.writestr("unknown.png", photo(180))
    did = client.post(
        "/api/dataset/import", files={"file": ("cal.zip", buffer.getvalue(), "application/zip")}
    ).json()["data"]["id"]
    eid = client.post(
        "/api/experiment/run", json={"dataset_id": did, "methods": ["original"]}
    ).json()["data"]["id"]
    response = client.post("/api/calibration", json={"experiment_id": eid, "target_far": 0})
    assert response.status_code == 200, response.text
    cid = response.json()["data"]["id"]
    assert response.json()["data"]["detail"]["original"]["observed_far"] == 0
    test_id = client.post(
        "/api/dataset/import",
        files={"file": ("test.zip", dataset_zip(value=80), "application/zip")},
    ).json()["data"]["id"]
    response = client.post(
        "/api/experiment/run",
        json={
            "dataset_id": test_id,
            "methods": ["original"],
            "calibration_id": cid,
            "threshold": -0.5,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["config"]["thresholds"]["original"] == 1
    assert (
        client.post(
            "/api/experiment/run",
            json={"dataset_id": test_id, "methods": ["gamma"], "calibration_id": cid},
        ).status_code
        == 400
    )
    assert enroll(client, value=200, name="另一人员", capture="enroll-2").status_code == 200
    assert (
        client.post(
            "/api/experiment/run",
            json={"dataset_id": test_id, "methods": ["original"], "calibration_id": cid},
        ).status_code
        == 409
    )


def test_failed_background_experiment_has_no_success_summary(client, model, monkeypatch):
    enroll(client)
    did = client.post(
        "/api/dataset/import", files={"file": ("test.zip", dataset_zip(), "application/zip")}
    ).json()["data"]["id"]

    def broken(_):
        raise RuntimeError("deliberate test inference failure")

    monkeypatch.setattr(model, "infer", broken)
    eid = client.post(
        "/api/experiment/run", json={"dataset_id": did, "methods": ["original"]}
    ).json()["data"]["id"]
    record = client.get(f"/api/experiment/{eid}").json()["data"]
    assert record["status"] == "failed" and record["summary"] == {}
    assert "deliberate test inference failure" in record["error"]


def test_deleted_person_id_is_never_reassigned_to_old_labels(client, model):
    enroll(client)
    did = client.post(
        "/api/dataset/import", files={"file": ("test.zip", dataset_zip(), "application/zip")}
    ).json()["data"]["id"]
    assert client.delete("/api/person/1").status_code == 200
    fresh = enroll(client, value=200, name="新人员", capture="new-session")
    assert fresh.status_code == 200 and fresh.json()["data"]["id"] != 1
    response = client.post("/api/experiment/run", json={"dataset_id": did, "methods": ["original"]})
    assert response.status_code == 409


def test_legacy_numeric_id_reuse_or_missing_registration_binding_is_rejected(client, model):
    from app.database.session import SessionLocal
    from app.models.entities import Person, Dataset
    from datetime import timedelta

    enroll(client)
    did = client.post(
        "/api/dataset/import", files={"file": ("test.zip", dataset_zip(), "application/zip")}
    ).json()["data"]["id"]
    with SessionLocal() as db:
        person = db.get(Person, 1)
        person.created_at += timedelta(seconds=1)
        db.commit()
    response = client.post("/api/experiment/run", json={"dataset_id": did, "methods": ["original"]})
    assert response.status_code == 409 and "身份引用" in response.json()["message"]
    with SessionLocal() as db:
        dataset = db.get(Dataset, did)
        manifest = dict(dataset.manifest)
        manifest.pop("person_references")
        dataset.manifest = manifest
        db.commit()
    assert (
        client.post(
            "/api/experiment/run", json={"dataset_id": did, "methods": ["original"]}
        ).status_code
        == 409
    )


def test_research_reports_are_read_only_and_raw_paths_not_accessible(client, tmp_path, monkeypatch):
    from app.services import research

    monkeypatch.setattr(research, "ROOT", tmp_path)
    assert client.get("/api/research/benchmarks").json()["data"] == []
    folder = tmp_path / "experiments/results/real-cbsr-nir"
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps({"dataset": "cbsr-nir", "status": "running"}))
    assert client.get("/api/research/benchmarks").json()["data"] == []
    (folder / "summary.json").write_text(
        json.dumps(
            {
                "dataset": "cbsr-nir",
                "status": "completed",
                "purpose": "unit-test report reader fixture",
            }
        )
    )
    assert len(client.get("/api/research/benchmarks").json()["data"]) == 1
    assert client.get("/api/research/benchmarks/not-a-dataset/csv").status_code == 404
    assert client.get("/datasets/raw/cbsr-nir/CBSR-NIR.zip").status_code == 404
    assert client.get("/api/research/benchmarks/cbsr-nir/csv").status_code == 404


def test_batch_delete_cleans_samples_and_all_related_records_only(client, model):
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models.entities import Person, FaceSample, RecognitionRecord, Dataset

    people = [
        enroll(client, value, name=f"批量人员{index}", capture=f"batch-{index}").json()["data"]
        for index, value in enumerate([60, 180, 200], 1)
    ]
    first, second, kept = [p["id"] for p in people]
    urls = [p["samples"][0]["image_url"] for p in people]
    did = client.post(
        "/api/dataset/import",
        files={"file": ("test.zip", dataset_zip(person_id=first), "application/zip")},
    ).json()["data"]["id"]
    with SessionLocal() as db:
        files = {
            sample.person_id: DATA / "samples" / sample.path
            for sample in db.scalars(select(FaceSample))
        }
        original_manifest = db.get(Dataset, did).manifest
        db.add_all(
            [
                RecognitionRecord(person_id=first, mode="identify", result={"candidates": []}),
                RecognitionRecord(
                    person_id=kept, mode="identify", result={"candidates": [{"person_id": second}]}
                ),
                RecognitionRecord(
                    person_id=None,
                    mode="verify",
                    result={"target_person_id": first, "candidates": []},
                ),
                RecognitionRecord(
                    person_id=kept, mode="identify", result={"candidates": [{"person_id": kept}]}
                ),
            ]
        )
        db.commit()
    response = client.post("/api/person/batch-delete", json={"person_ids": [second, first, first]})
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "deleted": [first, second],
        "count": 2,
        "cleanup": {"deleted_files": 2, "pending_files": 0},
    }
    assert [p["id"] for p in client.get("/api/person").json()["data"]] == [kept]
    assert [client.get(url).status_code for url in urls] == [404, 404, 200]
    assert not files[first].exists() and not files[second].exists() and files[kept].exists()
    with SessionLocal() as db:
        assert [s.person_id for s in db.scalars(select(FaceSample))] == [kept]
        records = list(db.scalars(select(RecognitionRecord)))
        assert len(records) == 1 and records[0].person_id == kept
        assert db.get(Dataset, did).manifest == original_manifest
        assert db.get(Person, first) is None and db.get(Person, second) is None


def test_batch_delete_stale_selection_is_rejected_without_partial_deletion(client, model):
    person = enroll(client).json()["data"]
    response = client.post("/api/person/batch-delete", json={"person_ids": [person["id"], 99999]})
    assert response.status_code == 409 and "刷新" in response.json()["message"]
    assert len(client.get("/api/person").json()["data"]) == 1
    assert client.get(person["samples"][0]["image_url"]).status_code == 200
    # A single-row delete still uses the same cleanup and retains its original response.
    assert client.delete(f"/api/person/{person['id']}").json()["data"] == {
        "deleted": person["id"],
        "cleanup": {"deleted_files": 1, "pending_files": 0},
    }
    assert client.delete(f"/api/person/{person['id']}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"person_ids": []},
        {"person_ids": [0]},
        {"person_ids": [-1]},
        {"person_ids": [True]},
        {"person_ids": ["1"]},
        {"person_ids": [1.5]},
        {"person_ids": [None]},
        {"person_ids": list(range(1, 1002))},
        {"person_ids": [1], "all": True},
    ],
)
def test_batch_delete_requires_explicit_bounded_positive_integer_ids(client, payload):
    assert client.post("/api/person/batch-delete", json=payload).status_code == 422
