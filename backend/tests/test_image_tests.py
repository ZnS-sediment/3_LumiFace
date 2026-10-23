"""Batch-upload contracts and metric denominators, using the isolated model fixture."""

import json
import pytest
from app.core.config import DATA
from app.database.session import SessionLocal
from app.models.entities import Dataset, Experiment
from test_api import enroll, photo


def submit(client, values, labels=None, methods=None, filenames=None):
    filenames = filenames or [f"query/{i}.png" for i in range(len(values))]
    items = (
        labels
        if labels is not None
        else [{"filename": filename, "person_id": 1, "scene": "normal"} for filename in filenames]
    )
    return client.post(
        "/api/experiment/images",
        data={
            "labels": json.dumps(
                {"items": items, "methods": methods or ["original"], "threshold": 0.45}
            )
        },
        files=[
            ("files", (name, photo(value), "image/png")) for name, value in zip(filenames, values)
        ],
    )


def detail(client, response):
    assert response.status_code == 200, response.text
    return client.get(f"/api/experiment/{response.json()['data']['id']}").json()["data"]


def test_all_images_in_denominator_and_unknown_separate(client, model):
    enroll(client)
    values = [70, 180, 0, 255, 170, 80]
    labels = [
        {
            "filename": f"query/{i}.png",
            "person_id": 1 if i < 4 else None,
            "scene": "normal" if i % 2 else "low_light",
        }
        for i in range(6)
    ]
    result = detail(client, submit(client, values, labels))
    assert result["status"] == "completed"
    assert (result["progress"], result["total"]) == (6, 6)
    stats = result["summary"]["original"]["overall"]
    assert (stats["correct"], stats["known"], stats["unknown"]) == (1, 4, 2)
    assert stats["confirmation_rate"] == 0.25
    assert stats["unknown_far"] == 0.5
    assert stats["no_face"] == stats["multiple_faces"] == 1
    assert result["config"]["kind"] == "image_batch"
    assert result["config"]["localization_protocol"] == "single_face_presence"
    rows = client.get(f"/api/experiment/{result['id']}/results").json()["data"]
    assert [row["outcome"] for row in rows] == [
        "correct",
        "rejected",
        "no_face",
        "multiple_faces",
        "unknown_rejected",
        "false_accept",
    ]
    assert "embedding" not in str(rows)
    preview = client.get(f"/api/experiment/{result['id']}/preview/{rows[0]['id']}")
    assert preview.status_code == 200
    assert preview.json()["data"]["enhanced"].startswith("data:image/png")


def test_wrong_identity_and_latest_run_history(client, model):
    enroll(client)
    enroll(client, value=180, name="另一人", capture="enroll-B")
    first = detail(client, submit(client, [190, 70]))
    rows = client.get(f"/api/experiment/{first['id']}/results").json()["data"]
    assert [row["outcome"] for row in rows] == ["wrong_identity", "correct"]
    assert rows[0]["expected_name"] == "测试人员" and rows[0]["predicted_name"] == "另一人"
    second = detail(client, submit(client, [70], methods=["original", "gamma"]))
    assert second["summary"]["original"]["overall"]["confirmation_rate"] == 1
    history = client.get("/api/experiment").json()["data"]
    assert [run["id"] for run in history] == [second["id"], first["id"]]
    assert history[1]["summary"]["original"]["overall"]["confirmation_rate"] == 0.5
    assert second["progress"] == 2


@pytest.mark.parametrize(
    "case",
    ["registration_copy", "duplicates", "label_order", "missing_label", "unknown_id", "bad_image"],
)
def test_invalid_upload_is_atomic(client, model, case):
    enroll(client)
    if case == "registration_copy":
        response = submit(client, [60])
    elif case == "duplicates":
        response = submit(client, [70, 70])
    elif case == "label_order":
        response = submit(client, [70], [{"filename": "different.png", "person_id": 1}])
    elif case == "missing_label":
        response = submit(client, [70], [{"filename": "query/0.png"}])
    elif case == "unknown_id":
        response = submit(client, [70], [{"filename": "query/0.png", "person_id": 999}])
    else:
        response = client.post(
            "/api/experiment/images",
            data={"labels": json.dumps({"items": [{"filename": "bad.png", "person_id": 1}]})},
            files={"files": ("bad.png", b"invalid", "image/png")},
        )
    assert response.status_code in (400, 409, 422), response.text
    with SessionLocal() as db:
        assert db.query(Dataset).count() == db.query(Experiment).count() == 0
    assert not list((DATA / "datasets").iterdir())


def test_no_gallery_rolls_back_generated_dataset(client, model):
    response = submit(client, [70], [{"filename": "query/0.png", "person_id": None}])
    assert response.status_code == 409
    assert client.get("/api/dataset").json()["data"] == []
    assert not list((DATA / "datasets").iterdir())


def test_unknown_only_is_not_reported_as_known_accuracy(client, model):
    enroll(client)
    run = detail(client, submit(client, [180], [{"filename": "query/0.png", "person_id": None}]))
    stats = run["summary"]["original"]["overall"]
    assert stats["confirmation_rate"] is None
    assert (stats["unknown"], stats["false_accept"]) == (1, 0)


def test_delete_quick_run_cleans_only_its_uploaded_dataset_and_csv_safe(client, model):
    enroll(client)
    run = detail(client, submit(client, [70], filenames=["=unsafe.png"]))
    csv = client.get(f"/api/experiment/{run['id']}/csv").text
    assert "filename,expected_name,predicted_name,similarity,outcome" in csv
    assert "'=unsafe.png" in csv
    assert client.delete(f"/api/experiment/{run['id']}").status_code == 200
    assert client.get("/api/dataset").json()["data"] == []
    assert not list((DATA / "datasets").iterdir())
    assert client.get("/api/person").json()["data"][0]["sample_count"] == 1


def test_size_limit_and_file_label_count(client, model, monkeypatch):
    from app.services import image_tests

    enroll(client)
    monkeypatch.setattr(image_tests, "MAX_ARCHIVE", 1)
    assert submit(client, [70]).status_code == 413
    assert (
        submit(client, [70, 80], [{"filename": "query/0.png", "person_id": 1}]).status_code == 422
    )
    assert not list((DATA / "datasets").iterdir())
