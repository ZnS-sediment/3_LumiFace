"""One-to-one score-ordered IoU matching; all rates use pooled counts."""
import math


def iou(a: list, b: list) -> float:
    w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def score_image(truth: list[dict], predictions: list[dict], elapsed_ms: float) -> dict:
    available = set(range(len(truth)))
    pairs = []
    for p in sorted(range(len(predictions)), key=lambda j: -predictions[j]['confidence']):
        ranked = [(iou(truth[g]['bbox'], predictions[p]['bbox']), g) for g in available]
        overlap, g = max(ranked, default=(0, -1))
        if overlap >= .5:
            available.remove(g)
            pairs.append((g, p))
    known = sum(g['person_id'] is not None for g in truth)
    unknown = len(truth) - known
    correct = detected_known = false_accept = detected_unknown = 0
    decisions = []
    matched = dict(pairs)
    for index, gt in enumerate(truth):
        pred = predictions[matched[index]] if index in matched else None
        is_known = gt['person_id'] is not None
        accepted = pred is not None and pred['match']['confirmed']
        success = bool(is_known and accepted and pred['match']['person_id'] == gt['person_id'])
        correct += success
        detected_known += bool(is_known and pred is not None)
        detected_unknown += bool(not is_known and pred is not None)
        false_accept += bool(not is_known and accepted)
        decisions.append({'known': is_known, 'correct': success, 'detected': pred is not None,
                          'score': pred['match']['similarity'] if pred else None,
                          'candidate_id': pred['match']['candidates'][0]['person_id'] if pred and pred['match']['candidates'] else None,
                          'truth_person_id': gt['person_id'], 'subject': gt['subject']})
    return {'tp': len(pairs), 'fp': len(predictions) - len(pairs), 'fn': len(truth) - len(pairs),
            'known': known, 'unknown': unknown, 'correct': correct, 'detected_known': detected_known,
            'detected_unknown': detected_unknown, 'false_accept': false_accept,
            'elapsed_ms': elapsed_ms, 'decisions': decisions, 'predictions': predictions}


def ratio(n: int | float, d: int | float) -> float | None:
    return n / d if d else None


def aggregate(rows: list[dict]) -> dict:
    counts = {k: sum(r[k] for r in rows) for k in ['tp', 'fp', 'fn', 'known', 'unknown', 'correct', 'detected_known', 'detected_unknown', 'false_accept']}
    return {**counts, 'images': len(rows), 'precision': ratio(counts['tp'], counts['tp'] + counts['fp']),
            'recall': ratio(counts['tp'], counts['tp'] + counts['fn']),
            'confirmation_rate': ratio(counts['correct'], counts['known']),
            'recognition_accuracy': ratio(counts['correct'], counts['detected_known']),
            'unknown_far': ratio(counts['false_accept'], counts['unknown']),
            'conditional_unknown_far': ratio(counts['false_accept'], counts['detected_unknown']),
            'mean_ms': ratio(sum(r['elapsed_ms'] for r in rows), len(rows))}


def calibrate(decisions: list[dict], target_far: float) -> dict:
    unknown = [d for d in decisions if not d['known']]
    known = [d for d in decisions if d['known']]
    if not unknown or not known:
        raise ValueError('校准集必须同时包含已知身份和未知身份')
    candidates = {-1., 1.}
    for decision in decisions:
        if decision['score'] is not None:
            candidates.add(float(decision['score']))
            if decision['score'] < 1:
                candidates.add(math.nextafter(float(decision['score']), math.inf))
    feasible = []
    for threshold in sorted(candidates):
        far = sum(d['score'] is not None and d['score'] >= threshold for d in unknown) / len(unknown)
        rate = sum(d['score'] is not None and d['score'] >= threshold and d['candidate_id'] == d['truth_person_id'] for d in known) / len(known)
        if far <= target_far:
            feasible.append((rate, threshold, far))
    if not feasible:
        raise ValueError('[-1,1] 中没有满足目标 FAR 的阈值')
    rate, threshold, far = max(feasible, key=lambda x: (x[0], x[1]))
    return {'threshold': threshold, 'observed_far': far, 'confirmation_rate': rate, 'known': len(known),
            'unknown': len(unknown), 'target_far': target_far, 'note': '仅校准集经验值，不保证测试集 FAR'}
