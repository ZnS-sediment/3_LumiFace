"""Batch-upload contracts and metric denominators, using the isolated model fixture."""

import json
import pytest
from app.core.config import DATA
from app.database.session import SessionLocal
from app.models.entities import Dataset, Experiment, ExperimentResult
from test_api import enroll, photo


def submit(client, values, labels=None, methods=None, filenames=None, name=None):
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
                {
                    "items": items,
                    "methods": methods or ["original"],
                    "threshold": 0.45,
                    **({"name": name} if name is not None else {}),
                }
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
    errors = result["error_summary"]["original"]
    assert errors["overall"]["images"] == 6
    assert errors["overall"]["total_errors"] == 4
    assert errors["overall"]["counts"] == {
        "no_face": 1, "multiple_faces": 0, "rejected": 2, "wrong_identity": 0, "false_accept": 1,
    }
    assert errors["scenes"]["low_light"]["total_errors"] == 1
    assert errors["scenes"]["normal"]["total_errors"] == 3
    assert errors["scenes"]["uneven"]["images"] == 0
    assert result["config"]["kind"] == "image_batch"
    assert result["config"]["localization_protocol"] == "image_identity_presence"
    rows = client.get(f"/api/experiment/{result['id']}/results").json()["data"]
    assert [row["outcome"] for row in rows] == [
        "correct",
        "rejected",
        "no_face",
        "rejected",
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
    assert first["error_summary"]["original"]["overall"]["counts"]["wrong_identity"] == 1
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


def test_delete_quick_run_cleans_only_its_uploaded_dataset(client, model):
    enroll(client)
    run = detail(client, submit(client, [70]))
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


def test_batch_upload_decodes_each_image_once_without_zip_roundtrip(client, model, monkeypatch):
    import io
    from fastapi import UploadFile
    from app.services import images, datasets
    from app.services.image_tests import create_image_test
    from app.schemas.contracts import ImageTestRequest

    enroll(client)
    decoded = []
    original = images.decode

    def decode_once(raw):
        decoded.append(raw)
        return original(raw)

    monkeypatch.setattr(images, "decode", decode_once)
    monkeypatch.setattr(
        datasets.zipfile, "ZipFile", lambda *a, **kw: pytest.fail("batch must not build a ZIP")
    )
    uploads = [
        UploadFile(io.BytesIO(photo(value)), filename=f"query/{i}.png")
        for i, value in enumerate([70, 80])
    ]
    request = ImageTestRequest(
        items=[{"filename": file.filename, "person_id": 1} for file in uploads]
    )
    with SessionLocal() as db:
        record, _ = create_image_test(db, uploads, request)
        assert record.total == 2
        dataset = db.get(Dataset, record.dataset_id)
        assert [item["display_file"] for item in dataset.manifest["items"]] == [
            file.filename for file in uploads
        ]
        assert len(list((DATA / "datasets" / dataset.directory).glob("*.png"))) == 2
    assert len(decoded) == 2


def test_per_image_automatic_parameters_are_frozen_and_preview_replays_them(client, model):
    import base64
    import numpy as np
    from app.services.images import decode
    from app.algorithms.enhancement import enhance
    from app.schemas.contracts import EnhanceOptions

    enroll(client)
    run = detail(client, submit(client, [25, 90], methods=["gamma", "retinex"]))
    assert run["config"]["parameter_policy"] == "image-statistics-v1"
    rows = client.get(f"/api/experiment/{run['id']}/results").json()["data"]
    gamma_rows = [row for row in rows if row["method"] == "gamma"]
    assert gamma_rows[0]["parameters"]["gamma"] != gamma_rows[1]["parameters"]["gamma"]
    assert all(not row["parameters"]["auto_parameters"] for row in rows)
    preview = client.get(f"/api/experiment/{run['id']}/preview/{rows[0]['id']}").json()["data"]
    before = decode(base64.b64decode(preview["original"].split(",")[1]))
    after = decode(base64.b64decode(preview["enhanced"].split(",")[1]))
    from app.algorithms.face_detector import annotate

    expected, _ = enhance(before, EnhanceOptions(**rows[0]["parameters"]))
    expected = annotate(expected, rows[0]["predictions"])
    assert np.array_equal(after, expected)


def test_rename_persists_without_changing_dataset_protocol_or_predictions(client, model):
    enroll(client)
    before = detail(client, submit(client, [70]))
    path = f"/api/experiment/{before['id']}"
    predictions = client.get(path + "/results").json()["data"]
    response = client.patch(path, json={"name": "  逆光对比第一轮  "})
    assert response.status_code == 200
    renamed = response.json()["data"]
    assert renamed["name"] == "逆光对比第一轮"
    assert client.get(path).json()["data"]["name"] == renamed["name"]
    assert client.get("/api/experiment").json()["data"][0]["name"] == renamed["name"]
    assert renamed["summary"] == before["summary"]
    assert {k: v for k, v in renamed["config"].items() if k != "display_name"} == before["config"]
    assert client.get(path + "/results").json()["data"] == predictions
    dataset = client.get(f"/api/dataset/{before['dataset_id']}").json()["data"]
    assert dataset["name"] == before["config"]["dataset"]["name"]


@pytest.mark.parametrize("name", ["", "   ", "名" * 101])
def test_invalid_rename_preserves_existing_name(client, model, name):
    enroll(client)
    record = detail(client, submit(client, [70]))
    path = f"/api/experiment/{record['id']}"
    assert client.patch(path, json={"name": name}).status_code == 422
    assert client.get(path).json()["data"]["name"] == record["name"]


@pytest.mark.parametrize("status", ["queued", "running"])
def test_rename_waits_for_running_test_and_missing_test_is_404(client, model, status):
    enroll(client)
    record = detail(client, submit(client, [70]))
    with SessionLocal() as db:
        experiment = db.get(Experiment, record["id"])
        experiment.status = status
        db.commit()
    path = f"/api/experiment/{record['id']}"
    assert client.patch(path, json={"name": "稍后命名"}).status_code == 409
    assert client.get(path).json()["data"]["name"] == record["name"]
    assert client.patch("/api/experiment/999999", json={"name": "不存在"}).status_code == 404


def test_error_summary_uses_all_saved_rows_beyond_page_and_preserves_frozen_summary(client, model):
    enroll(client)
    before = detail(client, submit(client, [70]))
    with SessionLocal() as db:
        for index in range(1, 61):
            db.add(ExperimentResult(
                experiment_id=before["id"], method="original", scene="uneven", item_index=index,
                detail={"outcome": "rejected" if index <= 9 else "correct"},
            ))
        db.commit()
    result = client.get(f"/api/experiment/{before['id']}").json()["data"]
    assert len(client.get(f"/api/experiment/{before['id']}/results").json()["data"]) == 50
    stats = result["error_summary"]["original"]
    assert stats["overall"]["images"] == 61
    assert stats["overall"]["total_errors"] == stats["scenes"]["uneven"]["counts"]["rejected"] == 9
    assert stats["scenes"]["uneven"]["images"] == 60
    assert result["summary"] == before["summary"]
    assert result["config"] == before["config"]


@pytest.mark.parametrize("name", [None, "", "   ", "  逆光第一轮  "])
def test_optional_name_uses_custom_value_or_existing_default(client, model, name):
    enroll(client)
    record = detail(client, submit(client, [70], name=name))
    if name and name.strip():
        assert record["name"] == "逆光第一轮"
        assert record["config"]["display_name"] == "逆光第一轮"
    else:
        assert record["name"].startswith("多图测试 ")
        assert record["name"] == record["config"]["dataset"]["name"]
        assert "display_name" not in record["config"]
    assert client.get("/api/experiment").json()["data"][0]["name"] == record["name"]


def test_too_long_name_fails_before_creating_test_or_upload_directory(client, model):
    enroll(client)
    response = submit(client, [70], name="名" * 101)
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.query(Dataset).count() == db.query(Experiment).count() == 0
    assert not list((DATA / "datasets").iterdir())


def test_complete_400_person_scene_upload_uses_frozen_server_default(client, model):
    """Exercise the real multipart parser above its former 1000-file ceiling."""
    import io
    from PIL import Image
    from app.core.config import DEFAULT_THRESHOLD, DEFAULT_THRESHOLD_POLICY

    enrolled = enroll(client).json()['data']
    files, items = [], []
    for index in range(1200):
        image = Image.new('RGB', (64, 64), (70, 70, 70))
        image.putpixel((1, 0), (index % 256, index // 256, 23))
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        name = f'query/person/{index}.png'
        files.append(('files', (name, stream.getvalue(), 'image/png')))
        items.append({'filename': name, 'person_id': enrolled['id'], 'scene': 'normal'})
    response = client.post('/api/experiment/images', files=files,
        data={'labels': json.dumps({'items': items, 'methods': ['original']})})
    result = detail(client, response)
    assert result['status'] == 'completed'
    assert result['progress'] == result['total'] == 1200
    assert result['summary']['original']['overall']['correct'] == 1200
    assert result['config']['thresholds'] == {'original': DEFAULT_THRESHOLD}
    assert result['config']['threshold_policy'] == DEFAULT_THRESHOLD_POLICY


def test_multipart_file_limit_remains_bounded(client, model):
    from app.core.config import MAX_DATASET_IMAGES
    response = client.post('/api/experiment/images', data={'labels': '{}'},
        files=[('files', (f'{i}.png', b'x', 'image/png')) for i in range(MAX_DATASET_IMAGES + 1)])
    assert response.status_code == 400
    with SessionLocal() as db:
        assert db.query(Dataset).count() == 0
        assert db.query(Experiment).count() == 0

@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_experiment_blocks_new_runs_before_reading_images(client, model, monkeypatch, status):
    from app.services import image_tests

    enroll(client)
    previous = detail(client, submit(client, [70]))
    with SessionLocal() as db:
        db.get(Experiment, previous["id"]).status = status
        db.commit()
    with monkeypatch.context() as patch:
        patch.setattr(image_tests, "read_upload", lambda *_: pytest.fail("must reject before decoding"))
        response = submit(client, [80])
        assert response.status_code == 409
        assert "等待当前测试结束" in response.json()["message"]
        response = client.post("/api/experiment/run", json={
            "dataset_id": previous["dataset_id"], "methods": ["original"],
        })
        assert response.status_code == 409
    assert client.get(f"/api/experiment/{previous['id']}").status_code == 200
    assert client.get(f"/api/experiment/{previous['id']}/results").status_code == 200
    with SessionLocal() as db:
        assert db.query(Experiment).count() == db.query(Dataset).count() == 1
        db.get(Experiment, previous["id"]).status = "completed"
        db.commit()
    assert detail(client, submit(client, [80]))["status"] == "completed"


def test_image_creation_keeps_reads_available_and_rejects_concurrent_creation(client, model, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.services import image_tests

    enroll(client)
    entered, release = Event(), Event()
    read_upload = image_tests.read_upload

    def paused_read(file):
        entered.set()
        assert release.wait(10), "test must release the first upload"
        return read_upload(file)

    monkeypatch.setattr(image_tests, "read_upload", paused_read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(submit, client, [70])
        try:
            assert entered.wait(5)
            assert client.get("/api/experiment").status_code == 200
            assert client.get("/api/person").status_code == 200
            response = submit(client, [80])
            assert response.status_code == 409
            assert "正在创建" in response.json()["message"]
        finally:
            release.set()
        assert detail(client, pending.result(timeout=10))["status"] == "completed"
    with SessionLocal() as db:
        assert db.query(Experiment).count() == db.query(Dataset).count() == 1
