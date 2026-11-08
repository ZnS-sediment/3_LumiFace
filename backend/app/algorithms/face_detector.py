import hashlib
import os
import threading
import time
from types import SimpleNamespace
import cv2
import numpy as np
from app.core.config import MODEL_ROOT, MODEL_NAME, RECOGNITION_BACKBONE
from app.core.errors import AppError
from app.algorithms.face_recognizer import unit
from app.services.images import data_url


class FaceEngine:
    def __init__(self) -> None:
        self.detection_size = int(os.environ.get("LUMIFACE_DETECTION_SIZE", "640"))
        if self.detection_size not in (320, 640):
            raise ValueError("LUMIFACE_DETECTION_SIZE must be 320 or 640")
        self._app = None
        self._lock = threading.RLock()
        self.error: str | None = None
        self.fingerprint: str | None = None
        self.providers: list[str] = []
        self.compatible_fingerprints: set[str] = set()

    def status(self) -> dict:
        return {
            "ready": self._app is not None,
            "model": MODEL_NAME,
            "recognition_backbone": RECOGNITION_BACKBONE,
            "providers": self.providers,
            "fingerprint": self.fingerprint,
            "error": self.error,
            "detection_size": self.detection_size,
            "inference_threads": (
                {
                    task: {
                        "intra": model.session.get_session_options().intra_op_num_threads,
                        "inter": model.session.get_session_options().inter_op_num_threads,
                    }
                    for task, model in self._app.models.items()
                }
                if self._app else {}
            ),
            "weights_present": all(path.is_file() for path in [
                MODEL_ROOT / "models" / MODEL_NAME / "det_10g.onnx",
                MODEL_ROOT / "models" / ("antelopev2" if RECOGNITION_BACKBONE == "glintr100" else MODEL_NAME)
                / f"{RECOGNITION_BACKBONE}.onnx",
            ]),
            "infrared_supported": "未验证；RGB 模型不保证可见光/红外跨模态准确率",
        }

    def load(self) -> None:
        with self._lock:
            if self._app is not None:
                return
            folder = MODEL_ROOT / "models" / MODEL_NAME
            recognizers = {
                "w600k_r50": folder / "w600k_r50.onnx",
                "glintr100": MODEL_ROOT / "models" / "antelopev2" / "glintr100.onnx",
            }
            required = [folder / "det_10g.onnx", recognizers[RECOGNITION_BACKBONE]]
            if not all(f.is_file() for f in required):
                self.error = "模型权重缺失，请运行 scripts/download_models.py；完成后重启服务或重新执行人脸操作"
                raise AppError(self.error, 503)
            try:
                import onnxruntime as ort
                from insightface.model_zoo.arcface_onnx import ArcFaceONNX
                from insightface.model_zoo.retinaface import RetinaFace

                available = ort.get_available_providers()
                selected = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if "CUDAExecutionProvider" in available
                    else ["CPUExecutionProvider"]
                )
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                opts.inter_op_num_threads = 1
                opts.log_severity_level = 3
                cv2.setNumThreads(2)
                # InsightFace 0.7.3's get_model drops sess_options. Construct the
                # two sessions explicitly so CPU limits really apply, and avoid
                # loading the three unused landmark/attribute models.
                models = {
                    task: constructor(
                        model_file=str(path),
                        session=ort.InferenceSession(
                            str(path), sess_options=opts, providers=selected
                        ),
                    )
                    for task, constructor, path in [
                        ("detection", RetinaFace, required[0]),
                        ("recognition", ArcFaceONNX, required[1]),
                    ]
                }
                app = SimpleNamespace(models=models, det_model=models["detection"])
                app.det_model.prepare(
                    ctx_id=0, input_size=(self.detection_size, self.detection_size), det_thresh=0.5
                )
                self.providers = app.det_model.session.get_providers()

                def fingerprint(paths):
                    h = hashlib.sha256()
                    for path in paths:
                        with path.open("rb") as source:
                            for block in iter(lambda: source.read(1024 * 1024), b""):
                                h.update(block)
                    return h.hexdigest()

                self.fingerprint = fingerprint(required)
                self.compatible_fingerprints = {
                    fingerprint([required[0], path])
                    for path in recognizers.values() if path.is_file()
                }
                self._app = app
                self.error = None
            except Exception as exc:
                self.error = f"真实模型加载失败：{type(exc).__name__}: {exc}"
                raise AppError(self.error, 503) from exc

    def detect_faces(self, image: np.ndarray) -> list[dict]:
        """Locate every face without extracting features that may be discarded."""
        self.load()
        with self._lock:
            try:
                boxes, landmarks = self._app.det_model.detect(image, max_num=0, metric="default")
                faces = [
                    {
                        "bbox": box[:4].astype(float).tolist(),
                        "keypoints": points.astype(float).tolist(),
                        "confidence": float(box[4]),
                    }
                    for box, points in zip(boxes, landmarks if landmarks is not None else [])
                ]
                return faces
            except Exception as exc:
                raise AppError("人脸模型推理失败，请检查模型与运行环境", 503) from exc

    def infer(self, image: np.ndarray) -> list[dict]:
        faces = self.detect_faces(image)
        return [
            {**face, "embedding": vector}
            for face, vector in zip(faces, self.aligned_embeddings(image, faces))
        ]

    def aligned_embeddings(self, image: np.ndarray, faces: list[dict]) -> list[list[float]]:
        """Reuse the same landmarks for a second photometric view of each face."""
        if not faces:
            return []
        from insightface.utils.face_align import norm_crop

        self.load()
        with self._lock:
            try:
                vectors = []
                for offset in range(0, len(faces), 16):
                    crops = [
                        norm_crop(image, np.asarray(face["keypoints"], dtype=np.float32))
                        for face in faces[offset : offset + 16]
                    ]
                    vectors.extend(
                        unit(vector).tolist()
                        for vector in self._app.models["recognition"].get_feat(crops)
                    )
                return vectors
            except Exception as exc:
                raise AppError("对齐人脸特征提取失败，请检查模型与运行环境", 503) from exc

    def local_embeddings(self, image: np.ndarray, faces: list[dict], method: str) -> list[list[list[float]]]:
        """Apply image-only illumination correction after alignment, with mirrored views."""
        if not faces:
            return []
        from insightface.utils.face_align import norm_crop
        from app.algorithms.enhancement import enhance
        from app.schemas.contracts import EnhanceOptions

        self.load()
        with self._lock:
            try:
                result = []
                # Two feature views per face, bounded CPU intermediate tensors.
                batch_size = 8
                for offset in range(0, len(faces), batch_size):
                    crops = []
                    for face in faces[offset:offset + batch_size]:
                        crop = norm_crop(image, np.asarray(face["keypoints"], dtype=np.float32))
                        local, _ = enhance(crop, EnhanceOptions(method=method, auto_parameters=True))
                        crops.extend([local, cv2.flip(local, 1)])
                    vectors = [unit(v).tolist() for v in self._app.models["recognition"].get_feat(crops)]
                    result.extend([vectors[i:i + 2] for i in range(0, len(vectors), 2)])
                return result
            except Exception as exc:
                raise AppError("人脸局部增强特征提取失败，请检查模型与运行环境", 503) from exc


engine = FaceEngine()


def annotate(image: np.ndarray, faces: list[dict]) -> np.ndarray:
    result = image.copy()
    for index, face in enumerate(faces, 1):
        x1, y1, x2, y2 = [int(x) for x in face["bbox"]]
        cv2.rectangle(result, (x1, y1), (x2, y2), (80, 220, 40), 2)
        cv2.putText(
            result,
            f"#{index} {face['confidence']:.3f}",
            (max(0, x1), max(15, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (80, 220, 40),
            2,
        )
        for x, y in face["keypoints"]:
            cv2.circle(result, (int(x), int(y)), 3, (255, 160, 20), -1)
    return result


def public_faces(image: np.ndarray, faces: list[dict], crops: bool = True) -> list[dict]:
    from insightface.utils.face_align import norm_crop

    result = []
    for face in faces:
        row = {k: v for k, v in face.items() if k != "embedding"}
        if crops:
            row["aligned_crop"] = data_url(
                norm_crop(image, np.asarray(face["keypoints"], dtype=np.float32))
            )
        result.append(row)
    return result


def detect(image: np.ndarray) -> dict:
    start = time.perf_counter()
    faces = engine.infer(image)
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "faces": public_faces(image, faces),
        "count": len(faces),
        "elapsed_ms": elapsed,
        "image": data_url(annotate(image, faces)),
    }
