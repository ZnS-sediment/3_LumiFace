"""Multi-face decisions must use accepted exact IDs, never candidate/name containment."""

import copy
import numpy as np
import pytest
from app.algorithms.face_recognizer import match
from app.algorithms.metrics import score_image
from app.algorithms.recognition import recognition_faces, RECOGNITION_POLICY, PREVIOUS_RECOGNITION_POLICY
from test_api import enroll, photo
from test_image_tests import detail, submit


def face(embedding, box=None):
    return {
        "bbox": box or [8., 8., 56., 56.],
        "keypoints": [[20., 25.], [43., 25.], [32., 35.], [23., 45.], [41., 45.]],
        "confidence": .99, "embedding": embedding,
    }


def test_second_face_correct_only_under_new_image_policy(client, model, monkeypatch):
    enroll(client, name="Ann")
    enroll(client, value=180, name="Anna", capture="other")
    infer = model.infer

    def multi(image):
        if image[0, 0, 0] == 200:
            return [face([0, 1, 0]), face([1, 0, 0], [1., 1., 20., 20.])]
        return infer(image)

    monkeypatch.setattr(model, "infer", multi)
    run = detail(client, submit(client, [200, 190]))
    stats = run["summary"]["original"]["overall"]
    assert (stats["correct"], stats["known"], stats["multiple_faces"]) == (1, 2, 1)
    rows = client.get(f"/api/experiment/{run['id']}/results").json()["data"]
    assert rows[0]["outcome"] == "correct"
    assert rows[0]["predicted_name"] == "Anna、Ann"
    assert [p["match"]["person_id"] for p in rows[0]["predictions"]] == [2, 1]
    assert rows[1]["outcome"] == "wrong_identity"  # "Anna" contains "Ann"; still wrong.
    legacy = score_image(
        [{"person_id": 1, "subject": "Ann", "bbox": [0, 0, 64, 64]}],
        rows[0]["predictions"], 1, "single_face_presence",
    )
    assert legacy["correct"] == 0
    response = client.post(
        "/api/recognition/identify", data={"options": '{"method":"original"}'},
        files={"file": ("group.png", photo(200), "image/png")},
    )
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["name"] == "Anna、Ann" and result["person_ids"] == [2, 1]
    assert len(result["faces"]) == len(result["face_matches"]) == 2
    assert all("embedding" not in f for f in result["faces"])
    response = client.post(
        "/api/recognition/verify",
        data={"person_id": 1, "options": '{"method":"original"}'},
        files={"file": ("group.png", photo(200), "image/png")},
    )
    verified = response.json()["data"]
    assert verified["name"] == "Ann" and verified["confirmed"]
    assert [f["match"]["confirmed"] for f in verified["faces"]] == [False, True]
    assert enroll(client, value=255, name="group", capture="group").status_code == 422
    # Identity deletion must also clear records holding that person's per-face candidates.
    assert client.delete("/api/person/1").status_code == 200
    assert client.get("/api/recognition/records").json()["data"] == []


@pytest.mark.parametrize("count", [1, 2, 3])
def test_threshold_candidates_and_unknown_false_accept(count):
    gallery = [{"id": 1, "name": "A", "embedding": [1, 0]}]
    rejected = {**face([0, 1]), "match": match([.44, np.sqrt(1-.44**2)], gallery, .45)}
    accepted = {**face([1, 0]), "match": match([1, 0], gallery, .45)}
    truth = [{"person_id": 1, "subject": "A"}]
    rows = [copy.deepcopy(rejected) for _ in range(count)]
    stats = score_image(truth, rows, 1, "image_identity_presence")
    assert stats["correct"] == 0 and stats["known"] == 1
    rows[-1] = accepted
    stats = score_image(truth, rows, 1, "image_identity_presence")
    assert stats["correct"] == stats["known"] == 1
    unknown = score_image([{"person_id": None, "subject": "U"}], rows, 1, "image_identity_presence")
    assert unknown["false_accept"] == unknown["unknown"] == 1
    assert unknown["correct"] == 0


def test_fusion_preserves_geometry_and_detects_additional_faces(model, monkeypatch):
    original = np.full((64, 64, 3), 70, np.uint8)
    enhanced = np.full_like(original, 150)
    raw = [face([1, 0, 0])]
    extra = face([0, 0, 1], [1., 1., 6., 6.])
    monkeypatch.setattr(model, "infer", lambda im: copy.deepcopy(raw if im[0, 0, 0] == 70 else [face([0, 1, 0]), extra]))
    calls = []

    def aligned(image, faces):
        calls.append(copy.deepcopy(faces))
        return [[0., 1., 0.] for _ in faces]

    monkeypatch.setattr(model, "aligned_embeddings", aligned)
    fused = recognition_faces(original, enhanced, PREVIOUS_RECOGNITION_POLICY, .3)
    assert len(fused) == 2 and len(calls) == 1
    assert calls[0][0]["keypoints"] == fused[0]["keypoints"] == raw[0]["keypoints"]
    assert fused[0]["embedding"] == pytest.approx([.7 / np.sqrt(.58), .3 / np.sqrt(.58), 0])
    assert raw[0]["embedding"] == [1, 0, 0]
    assert fused[1]["feature_source"] == "enhanced_detection"
    assert recognition_faces(original, original, PREVIOUS_RECOGNITION_POLICY) == raw
    legacy = recognition_faces(original, enhanced)
    assert legacy[0]["embedding"] == [0, 1, 0]


def test_fusion_configuration_is_frozen_per_new_run(client, model):
    enroll(client)
    run = detail(client, submit(client, [70], methods=["original", "gamma"]))
    assert run["config"]["recognition_policy"] == RECOGNITION_POLICY
    assert run["config"]["enhanced_feature_weight"] is None
    assert run["config"]["recognition_parameters"]["gamma"] == {"mode": "aligned_fusion", "enhanced_weight": .3}
    assert run["config"]["environment"]["algorithm_version"] == "lumiface-1.4"


def test_legacy_worker_config_keeps_strict_multiple_face_failure(client, model):
    from app.database.session import SessionLocal
    from app.models.entities import Experiment
    from app.services.experiments import run_experiment
    from app.services.persons import gallery

    enroll(client, value=180)
    current = detail(client, submit(client, [255]))
    assert current["summary"]["original"]["overall"]["correct"] == 1
    with SessionLocal() as db:
        original = db.get(Experiment, current["id"])
        config = copy.deepcopy(original.config)
        config.pop("recognition_policy")
        config.pop("enhanced_feature_weight")
        config["localization_protocol"] = "single_face_presence"
        legacy = Experiment(dataset_id=original.dataset_id, config=config, total=1)
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
        templates = gallery(db)
    run_experiment(legacy_id, templates)
    legacy = client.get(f"/api/experiment/{legacy_id}").json()["data"]
    assert legacy["status"] == "completed"
    assert legacy["summary"]["original"]["overall"]["correct"] == 0
    assert legacy["error_summary"]["original"]["overall"]["counts"]["multiple_faces"] == 1
    # Reading/running another policy never changes an already completed run.
    assert client.get(f"/api/experiment/{current['id']}").json()["data"]["summary"] == current["summary"]


@pytest.mark.parametrize("truth", [[], [{"person_id": 1}, {"person_id": 2}]])
def test_image_identity_protocol_requires_exactly_one_image_label(truth):
    with pytest.raises(ValueError, match="exactly one"):
        score_image(truth, [], 0, "image_identity_presence")


@pytest.mark.parametrize('raw_count', [0, 1, 2])
def test_v3_only_extracts_features_used_in_output(model, monkeypatch, raw_count):
    from app.algorithms.recognition import LEGACY_FUSION_POLICY

    original = np.full((64, 64, 3), 70, np.uint8)
    enhanced = np.full_like(original, 150)
    raw = [face([1, 0, 0], [i * 20, 0, i * 20 + 15, 15]) for i in range(raw_count)]
    extra = face([0, 1, 0], [0, 30, 15, 45])
    detections = [*raw, extra, copy.deepcopy(extra)]
    calls = []
    monkeypatch.setattr(model, 'infer', lambda im: copy.deepcopy(raw if im is original else detections))
    monkeypatch.setattr(model, 'detect_faces', lambda im: copy.deepcopy(detections))

    def extract(im, faces):
        calls.append(len(faces))
        return [f['embedding'] for f in faces]

    monkeypatch.setattr(model, 'aligned_embeddings', extract)
    legacy = recognition_faces(original, enhanced, LEGACY_FUSION_POLICY)
    calls.clear()
    result = recognition_faces(original, enhanced, PREVIOUS_RECOGNITION_POLICY, original_faces=raw)
    assert result == legacy
    assert calls == [raw_count + 1]  # No features for duplicate detections.
    assert len(result) == raw_count + 1


def test_batch_reuses_original_but_charges_it_to_each_method(client, model, monkeypatch):
    import itertools
    from app.services import experiments

    enroll(client)
    calls = []
    original_infer = model.infer

    def infer(image):
        calls.append(int(image[0, 0, 0]))
        return original_infer(image)

    monkeypatch.setattr(model, 'infer', infer)
    monkeypatch.setattr(model, 'detect_faces', lambda im: original_infer(im))
    # Model deterministic durations: one second for shared inference, one for
    # each method's remaining work. Never report a free cached baseline.
    ticks = itertools.count()
    monkeypatch.setattr(experiments.time, 'perf_counter', lambda: float(next(ticks)))
    run = detail(client, submit(client, [70, 80], methods=['gamma', 'original', 'clahe']))
    assert run['status'] == 'completed'
    assert calls == [70, 70, 80]  # One warmup plus one inference per image.
    rows = client.get(f"/api/experiment/{run['id']}/results").json()['data']
    assert len(rows) == 6
    for row in rows:
        assert row['timing']['original_inference_ms'] == 1000
        assert row['timing']['method_ms'] == 1000
        assert row['elapsed_ms'] == 2000


def test_face_local_preserves_every_face_and_original_geometry(model, monkeypatch):
    original = np.full((64, 64, 3), 70, np.uint8)
    enhanced = np.full_like(original, 150)
    raw = [face([1, 0, 0]), face([0, 1, 0], [70, 0, 100, 30])]
    saved = copy.deepcopy(raw)
    extra = face([0, 0, 1], [0, 70, 30, 100])
    monkeypatch.setattr(model, 'detect_faces', lambda im: raw + [extra, copy.deepcopy(extra)])
    monkeypatch.setattr(model, 'aligned_embeddings', lambda im, faces: [[0, 0, 1] for _ in faces])
    calls = []

    def local(im, faces, method):
        assert im is original
        calls.append((len(faces), method))
        return [[[0, 1, 0], [0, 0, 1]] for _ in faces]

    monkeypatch.setattr(model, 'local_embeddings', local)
    result = recognition_faces(original, enhanced, RECOGNITION_POLICY,
        original_faces=raw, enhancement_method='clahe')
    assert calls == [(3, 'clahe')]
    assert len(result) == 3 and raw == saved
    assert result[0]['embedding'] == pytest.approx(np.array([.7, .15, .15]) / np.linalg.norm([.7, .15, .15]))
    assert [r['bbox'] for r in result] == [f['bbox'] for f in raw + [extra]]
    assert all(r['feature_source'] == 'face_local_mirror' for r in result)
    with pytest.raises(ValueError, match='method'):
        recognition_faces(original, enhanced, RECOGNITION_POLICY)


def test_local_views_normalize_aligned_faces_and_keep_mirror_pairs(model, monkeypatch):
    from types import SimpleNamespace
    from app.algorithms.face_detector import FaceEngine
    from app.algorithms import enhancement

    image = np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)
    saved = image.copy()
    stages, batches = [], []

    def enhance(crop, options):
        assert crop.shape == (112, 112, 3)
        stages.append(options.method)
        return (crop // 2 + 15).astype(np.uint8), []

    def extract(crops):
        batches.append(crops)
        return [[1., 0., 0.] for _ in crops]

    monkeypatch.setattr(enhancement, 'enhance', enhance)
    monkeypatch.setattr(model, '_app', SimpleNamespace(models={'recognition': SimpleNamespace(get_feat=extract)}))
    result = FaceEngine.local_embeddings(model, image, [face([1, 0, 0]), face([1, 0, 0])], 'clahe')
    assert stages == ['clahe', 'clahe']
    assert len(batches) == 1 and len(batches[0]) == 4
    for index in (0, 2):
        assert np.array_equal(batches[0][index][:, ::-1], batches[0][index + 1])
    assert result == [[[1., 0., 0.]] * 2] * 2
    assert np.array_equal(image, saved)


def test_face_local_parameters_are_recorded_for_each_method(client, model):
    enroll(client)
    run = detail(client, submit(client, [70], methods=['original', 'gamma', 'clahe', 'retinex']))
    assert run['status'] == 'completed'
    parameters = run['config']['recognition_parameters']
    assert parameters['clahe'] == {'mode': 'face_local_mirror', 'original_weight': .7}
    assert parameters['retinex'] == {'mode': 'aligned_fusion', 'enhanced_weight': .5}


def test_retinex_weight_changes_only_current_policy(model, monkeypatch):
    original = np.full((64, 64, 3), 70, np.uint8)
    enhanced = np.full_like(original, 150)
    raw = [face([1, 0, 0])]
    monkeypatch.setattr(model, 'detect_faces', lambda im: raw)
    monkeypatch.setattr(model, 'aligned_embeddings', lambda im, faces: [[0, 1, 0] for _ in faces])
    for policy, expected in [(RECOGNITION_POLICY, [.5, .5, 0]), (PREVIOUS_RECOGNITION_POLICY, [.7, .3, 0])]:
        result = recognition_faces(original, enhanced, policy, original_faces=raw, enhancement_method='retinex')
        assert result[0]['embedding'] == pytest.approx(np.array(expected) / np.linalg.norm(expected))
    assert raw[0]['embedding'] == [1, 0, 0]
