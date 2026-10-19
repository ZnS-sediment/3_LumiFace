"""One-to-one score-ordered IoU matching; all rates use pooled counts."""

import math
from collections import defaultdict
import numpy as np


def iou(a: list, b: list) -> float:
    w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def score_image(
    truth: list[dict], predictions: list[dict], elapsed_ms: float, protocol: str = "iou"
) -> dict:
    if protocol not in ("iou", "eye_containment", "single_face_presence"):
        raise ValueError("Unknown localization protocol")
    if protocol == "eye_containment" and any(not g.get("eyes") for g in truth):
        raise ValueError("Eye-containment evaluation requires independent eye annotations")
    if protocol == "single_face_presence" and len(truth) != 1:
        raise ValueError("Single-face presence requires exactly one annotated subject")
    available = set(range(len(truth)))
    pairs = []
    for p in sorted(range(len(predictions)), key=lambda j: -predictions[j]["confidence"]):

        def overlap(g: int) -> float:
            if protocol == "single_face_presence":
                return 1.0 if len(predictions) == 1 else 0.0
            if protocol == "eye_containment":
                x1, y1, x2, y2 = predictions[p]["bbox"]
                return float(all(x1 <= x <= x2 and y1 <= y <= y2 for x, y in truth[g]["eyes"]))
            return iou(truth[g]["bbox"], predictions[p]["bbox"])

        ranked = [(overlap(g), g) for g in available]
        overlap, g = max(ranked, default=(0, -1))
        if overlap >= 0.5:
            available.remove(g)
            pairs.append((g, p))
    known = sum(g["person_id"] is not None for g in truth)
    unknown = len(truth) - known
    correct = detected_known = false_accept = detected_unknown = 0
    decisions = []
    matched = dict(pairs)
    for index, gt in enumerate(truth):
        pred = predictions[matched[index]] if index in matched else None
        is_known = gt["person_id"] is not None
        accepted = pred is not None and pred["match"]["confirmed"]
        success = bool(is_known and accepted and pred["match"]["person_id"] == gt["person_id"])
        correct += success
        detected_known += bool(is_known and pred is not None)
        detected_unknown += bool(not is_known and pred is not None)
        false_accept += bool(not is_known and accepted)
        decisions.append(
            {
                "known": is_known,
                "correct": success,
                "detected": pred is not None,
                "score": pred["match"]["similarity"] if pred else None,
                "candidate_id": pred["match"]["candidates"][0]["person_id"]
                if pred and pred["match"]["candidates"]
                else None,
                "truth_person_id": gt["person_id"],
                "subject": gt["subject"],
            }
        )
    return {
        "tp": len(pairs),
        "fp": len(predictions) - len(pairs),
        "fn": len(truth) - len(pairs),
        "known": known,
        "unknown": unknown,
        "correct": correct,
        "detected_known": detected_known,
        "detected_unknown": detected_unknown,
        "false_accept": false_accept,
        "elapsed_ms": elapsed_ms,
        "localization_protocol": protocol,
        "decisions": decisions,
        "predictions": predictions,
    }


def ratio(n: int | float, d: int | float) -> float | None:
    return n / d if d else None


def wilson(successes: int, total: int) -> list[float] | None:
    """95% Wilson interval; correlated frames still require a cluster-aware interval."""
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def subject_bootstrap(rows: list[dict], repetitions: int = 2000) -> list[float] | None:
    """Resample measured subject clusters; never generate synthetic prediction scores."""
    clusters: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        for decision in row.get("decisions", []):
            if decision["known"]:
                clusters[decision["subject"]][0] += int(decision["correct"])
                clusters[decision["subject"]][1] += 1
    if len(clusters) < 2:
        return None
    values = np.array(list(clusters.values()), dtype=np.int64)
    indices = np.random.default_rng(20261017).integers(
        0, len(values), size=(repetitions, len(values))
    )
    sampled = values[indices].sum(axis=1)
    rates = sampled[:, 0] / sampled[:, 1]
    return np.quantile(rates, [0.025, 0.975]).astype(float).tolist()


def aggregate(rows: list[dict]) -> dict:
    counts = {
        k: sum(r[k] for r in rows)
        for k in [
            "tp",
            "fp",
            "fn",
            "known",
            "unknown",
            "correct",
            "detected_known",
            "detected_unknown",
            "false_accept",
        ]
    }
    known_subjects = {d["subject"] for r in rows for d in r.get("decisions", []) if d["known"]}
    unknown_subjects = {
        d["subject"] for r in rows for d in r.get("decisions", []) if not d["known"]
    }
    return {
        **counts,
        "images": len(rows),
        "known_subjects": len(known_subjects),
        "unknown_subjects": len(unknown_subjects),
        "confirmation_ci95": wilson(counts["correct"], counts["known"]),
        "unknown_far_ci95": wilson(counts["false_accept"], counts["unknown"]),
        "confirmation_subject_bootstrap_ci95": subject_bootstrap(rows),
        "precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
        "recall": ratio(counts["tp"], counts["tp"] + counts["fn"]),
        "confirmation_rate": ratio(counts["correct"], counts["known"]),
        "recognition_accuracy": ratio(counts["correct"], counts["detected_known"]),
        "unknown_far": ratio(counts["false_accept"], counts["unknown"]),
        "conditional_unknown_far": ratio(counts["false_accept"], counts["detected_unknown"]),
        "mean_ms": ratio(sum(r["elapsed_ms"] for r in rows), len(rows)),
    }


def calibrate(decisions: list[dict], target_far: float) -> dict:
    unknown = [d for d in decisions if not d["known"]]
    known = [d for d in decisions if d["known"]]
    if not unknown or not known:
        raise ValueError("校准集必须同时包含已知身份和未知身份")
    candidates = {-1.0, 1.0}
    for decision in decisions:
        if decision["score"] is not None:
            candidates.add(float(decision["score"]))
            if decision["score"] < 1:
                candidates.add(math.nextafter(float(decision["score"]), math.inf))
    feasible = []
    for threshold in sorted(candidates):
        far = sum(d["score"] is not None and d["score"] >= threshold for d in unknown) / len(
            unknown
        )
        rate = sum(
            d["score"] is not None
            and d["score"] >= threshold
            and d["candidate_id"] == d["truth_person_id"]
            for d in known
        ) / len(known)
        if far <= target_far:
            feasible.append((rate, threshold, far))
    if not feasible:
        raise ValueError("[-1,1] 中没有满足目标 FAR 的阈值")
    rate, threshold, far = max(feasible, key=lambda x: (x[0], x[1]))
    return {
        "threshold": threshold,
        "observed_far": far,
        "confirmation_rate": rate,
        "known": len(known),
        "unknown": len(unknown),
        "target_far": target_far,
        "note": "仅校准集经验值，不保证测试集 FAR",
    }
