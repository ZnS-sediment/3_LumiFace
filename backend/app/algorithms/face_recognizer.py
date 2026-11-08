import numpy as np
from app.core.errors import AppError


def unit(vector: list | np.ndarray) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    if not np.all(np.isfinite(v)) or n < 1e-8:
        raise AppError("无效的人脸特征向量", 422)
    return v / n


def match(embedding: list | np.ndarray, gallery: list[dict], threshold: float) -> dict:
    probe = unit(embedding)
    candidates = []
    for person in gallery:
        score = float(np.clip(probe @ unit(person["embedding"]), -1, 1))
        candidates.append({"person_id": person["id"], "name": person["name"], "similarity": score})
    candidates.sort(key=lambda row: (-row["similarity"], row["person_id"]))
    best = candidates[0] if candidates else None
    confirmed = best is not None and best["similarity"] >= threshold
    return {
        "person_id": best["person_id"] if confirmed else None,
        "name": best["name"] if confirmed else "未知身份",
        "similarity": best["similarity"] if best else None,
        "threshold": threshold,
        "confirmed": confirmed,
        "candidates": candidates[:5],
        "diagnostic": "身份已确认" if confirmed else ("未达到身份确认标准" if best else "身份库为空"),
    }


def summarize_matches(matches: list[dict], threshold: float) -> dict:
    """Keep each face's threshold decision; never promote diagnostic candidates."""
    if len(matches) == 1:
        return matches[0].copy()
    accepted = {m["person_id"]: m["name"] for m in matches if m["confirmed"]}
    scores = [m["similarity"] for m in matches if m["similarity"] is not None]
    return {
        "person_id": None,
        "person_ids": list(accepted),
        "name": "、".join(accepted.values()) or "未知身份",
        "similarity": max(scores, default=None),
        "threshold": threshold,
        "confirmed": bool(accepted),
        "candidates": [],
        "diagnostic": f"逐一识别 {len(matches)} 张人脸，确认 {len(accepted)} 个身份",
    }
