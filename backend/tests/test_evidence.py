import pytest
from app.algorithms.evidence import assess_target
from app.algorithms.metrics import score_image, wilson, subject_bootstrap


def stats(correct=100, total=100):
    return {
        "confirmation_rate": correct / total,
        "known": total,
        "known_subjects": 10,
        "confirmation_ci95": wilson(correct, total),
        "confirmation_subject_bootstrap_ci95": [correct / total, correct / total],
    }


def nir_evidence(night=False):
    return {
        "capture_independence": "session_disjoint",
        "scene_evidence": {
            "infrared": {
                "source": "independent capture log",
                "annotation_basis": "manual_capture_log",
                "modality": "nir",
                "active_illumination": True,
                "night_confirmed": night,
            }
        },
    }


def test_real_capture_flag_alone_never_certifies_targets():
    result = assess_target(
        "infrared", stats(), real_capture=True, independent_calibration=True, protocol={}
    )
    assert result["status"] == "已有实测，目标场景证据不足"
    assert any("夜间" in reason for reason in result["reasons"])


def test_nir_without_night_and_thermal_are_not_night_nir_evidence():
    result = assess_target(
        "infrared",
        stats(),
        real_capture=True,
        independent_calibration=True,
        protocol=nir_evidence(),
    )
    assert result["reasons"]
    evidence = nir_evidence(True)
    evidence["scene_evidence"]["infrared"]["modality"] = "lwir"
    assert assess_target(
        "infrared", stats(), real_capture=True, independent_calibration=True, protocol=evidence
    )["reasons"]


def test_verified_sample_counts_intervals_and_freeze_are_all_required():
    evidence = nir_evidence(True)
    result = assess_target(
        "infrared", stats(), real_capture=True, independent_calibration=True, protocol=evidence
    )
    assert result["status"].startswith("达到目标")
    small = stats(10, 10)
    small["known_subjects"] = 2
    assert assess_target(
        "infrared", small, real_capture=True, independent_calibration=True, protocol=evidence
    )["reasons"]
    assert (
        assess_target(
            "infrared", stats(), real_capture=True, independent_calibration=False, protocol=evidence
        )["status"]
        == "探索性结果，不能判定达标"
    )
    point = stats(95, 100)
    assert (
        assess_target(
            "infrared", point, real_capture=True, independent_calibration=True, protocol=evidence
        )["status"]
        == "点估计达到目标，95%区间下限不足"
    )


def test_empty_denominator_and_cluster_uncertainty():
    assert wilson(0, 0) is None
    low, high = wilson(0, 100)
    assert low == pytest.approx(0, abs=1e-15) and 0 < high < 0.05
    assert subject_bootstrap([]) is None
    rows = [
        {"decisions": [{"known": True, "subject": "A", "correct": True}] * 20},
        {"decisions": [{"known": True, "subject": "B", "correct": False}] * 5},
    ]
    assert subject_bootstrap(rows) == subject_bootstrap(rows)
    assert subject_bootstrap(rows) == [0, 1]


def face(box):
    return {
        "bbox": box,
        "confidence": 0.9,
        "match": {
            "confirmed": True,
            "person_id": 1,
            "similarity": 0.9,
            "candidates": [{"person_id": 1}],
        },
    }


def test_independent_eyes_protocol_is_not_implicitly_iou():
    truth = [
        {"bbox": [0, 0, 100, 100], "eyes": [[40, 40], [60, 40]], "person_id": 1, "subject": "A"}
    ]
    prediction = face([35, 35, 65, 50])
    assert score_image(truth, [prediction], 1, protocol="eye_containment")["correct"] == 1
    assert score_image(truth, [prediction], 1)["correct"] == 0
    with pytest.raises(ValueError):
        score_image([{**truth[0], "eyes": None}], [prediction], 1, protocol="eye_containment")


def test_presence_rejects_multiple_predictions_and_preserves_failed_queries():
    truth = [{"bbox": [0, 0, 100, 100], "person_id": 1, "subject": "A"}]
    assert (
        score_image(truth, [face([20, 20, 60, 60])], 1, protocol="single_face_presence")["correct"]
        == 1
    )
    result = score_image(truth, [face([20, 20, 60, 60])] * 2, 1, protocol="single_face_presence")
    assert result["correct"] == 0 and result["known"] == 1 and result["fp"] == 2
    with pytest.raises(ValueError):
        score_image(truth, [], 1, protocol="fabricated")
