"""Label-independent, aligned original/enhanced feature fusion for recognition."""

import numpy as np
from app.algorithms.face_detector import engine
from app.algorithms.face_recognizer import unit
from app.algorithms.metrics import iou

LEGACY_FUSION_POLICY = "aligned-fusion-v2"
PREVIOUS_RECOGNITION_POLICY = "aligned-fusion-v3"
RECOGNITION_POLICY = "face-local-v4"
LOCAL_POLICIES = {
    "clahe": {"original_weight": 0.7},
}
ENHANCED_WEIGHT = 0.3
METHOD_ENHANCED_WEIGHTS = {"retinex": 0.5}


def recognition_faces(
    original: np.ndarray,
    enhanced: np.ndarray,
    policy: str = "processed-v1",
    enhanced_weight: float = ENHANCED_WEIGHT,
    *,
    original_faces: list[dict] | None = None,
    enhancement_method: str | None = None,
) -> list[dict]:
    if policy == "processed-v1":
        return engine.infer(enhanced)
    if policy not in (RECOGNITION_POLICY, PREVIOUS_RECOGNITION_POLICY, LEGACY_FUSION_POLICY) or not 0 <= enhanced_weight <= 1:
        raise ValueError("Unknown recognition policy or invalid fusion weight")
    if policy == RECOGNITION_POLICY and enhancement_method not in {"gamma", "clahe", "retinex", "exposure", "normalize", "adaptive"}:
        raise ValueError("Face-local policy requires its enhancement method")
    raw_faces = engine.infer(original) if original_faces is None else original_faces
    if policy != RECOGNITION_POLICY and np.array_equal(original, enhanced):
        return raw_faces
    # A face must be detected in at least one actual image. No gallery scores or
    # test labels enter detection, alignment, fusion, or the choice of weight.
    if policy == LEGACY_FUSION_POLICY:
        enhanced_faces = engine.infer(enhanced)
        embeddings = engine.aligned_embeddings(enhanced, raw_faces)
        return fuse_faces(raw_faces, enhanced_faces, embeddings, enhanced_weight)
    # Still scan the entire enhanced image for additional faces. Only extract
    # embeddings at the landmarks actually used in the final result.
    additional = []
    for face in engine.detect_faces(enhanced):
        if not any(iou(face["bbox"], existing["bbox"]) >= 0.3
                   for existing in raw_faces + additional):
            additional.append(face)
    if policy == RECOGNITION_POLICY and enhancement_method in LOCAL_POLICIES:
        config = LOCAL_POLICIES[enhancement_method]
        extra_vectors = engine.aligned_embeddings(original, additional)
        located = raw_faces + [
            {**face, "embedding": vector} for face, vector in zip(additional, extra_vectors)
        ]
        views = engine.local_embeddings(original, located, enhancement_method)
        view_count = 2
        if len(views) != len(located) or any(len(pair) != view_count for pair in views):
            raise ValueError("Invalid local feature count")
        raw_weight = config["original_weight"]
        result = []
        for face, pair in zip(located, views):
            raw = unit(face["embedding"])
            fused = raw_weight * raw + (1 - raw_weight) / 2 * (unit(pair[0]) + unit(pair[1]))
            result.append({**face, "embedding": unit(fused).tolist(), "feature_source": "face_local_mirror"})
        return result
    vectors = engine.aligned_embeddings(enhanced, raw_faces + additional)
    enhanced_faces = [
        {**face, "embedding": vector}
        for face, vector in zip(additional, vectors[len(raw_faces):])
    ]
    weight = METHOD_ENHANCED_WEIGHTS.get(enhancement_method, enhanced_weight) if policy == RECOGNITION_POLICY else enhanced_weight
    return fuse_faces(raw_faces, enhanced_faces, vectors[:len(raw_faces)], weight)


def fuse_faces(
    raw_faces: list[dict],
    enhanced_faces: list[dict],
    embeddings: list[list[float]],
    enhanced_weight: float = ENHANCED_WEIGHT,
) -> list[dict]:
    if len(raw_faces) != len(embeddings) or not 0 <= enhanced_weight <= 1:
        raise ValueError("Invalid aligned embeddings or fusion weight")
    result = [
        {
            **face,
            "embedding": unit(
                (1 - enhanced_weight) * unit(face["embedding"])
                + enhanced_weight * unit(vector)
            ).tolist(),
            "feature_source": "original_enhanced_fusion",
        }
        for face, vector in zip(raw_faces, embeddings)
    ]
    # Keep additional faces recovered from shadows, without duplicating the same
    # face when enhancement slightly moves its detector box.
    for face in enhanced_faces:
        if not any(iou(face["bbox"], existing["bbox"]) >= 0.3 for existing in result):
            result.append({**face, "feature_source": "enhanced_detection"})
    return result
