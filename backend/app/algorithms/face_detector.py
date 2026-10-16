import hashlib
import threading
import time
from pathlib import Path
import cv2
import numpy as np
from app.core.config import MODEL_ROOT, MODEL_NAME
from app.core.errors import AppError
from app.algorithms.face_recognizer import unit
from app.services.images import data_url


class FaceEngine:
    def __init__(self) -> None:
        self._app = None
        self._lock = threading.RLock()
        self.error: str | None = None
        self.fingerprint: str | None = None
        self.providers: list[str] = []

    def status(self) -> dict:
        return {'ready': self._app is not None, 'model': MODEL_NAME, 'providers': self.providers,
                'fingerprint': self.fingerprint, 'error': self.error,
                'weights_present': (MODEL_ROOT / 'models' / MODEL_NAME / 'det_10g.onnx').exists(),
                'infrared_supported': '未验证；RGB 模型不保证可见光/红外跨模态准确率'}

    def load(self) -> None:
        with self._lock:
            if self._app is not None:
                return
            folder = MODEL_ROOT / 'models' / MODEL_NAME
            required = [folder / 'det_10g.onnx', folder / 'w600k_r50.onnx']
            if not all(f.is_file() for f in required):
                self.error = '模型权重缺失，请运行 scripts/download_models.py，再点击加载模型'
                raise AppError(self.error, 503)
            try:
                import onnxruntime as ort
                from insightface.app import FaceAnalysis
                available = ort.get_available_providers()
                selected = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if 'CUDAExecutionProvider' in available else ['CPUExecutionProvider']
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                opts.inter_op_num_threads = 1
                app = FaceAnalysis(name=MODEL_NAME, root=str(MODEL_ROOT), allowed_modules=['detection', 'recognition'], providers=selected, sess_options=opts)
                app.prepare(ctx_id=0 if selected[0] == 'CUDAExecutionProvider' else -1, det_size=(640, 640), det_thresh=0.5)
                if 'recognition' not in app.models:
                    raise RuntimeError('缺少识别模型')
                self.providers = app.det_model.session.get_providers()
                h = hashlib.sha256()
                for path in required:
                    with path.open('rb') as source:
                        for block in iter(lambda: source.read(1024 * 1024), b''):
                            h.update(block)
                self.fingerprint = h.hexdigest()
                self._app = app
                self.error = None
            except Exception as exc:
                self.error = f'真实模型加载失败：{type(exc).__name__}: {exc}'
                raise AppError(self.error, 503) from exc

    def infer(self, image: np.ndarray) -> list[dict]:
        self.load()
        with self._lock:
            try:
                faces = self._app.get(image)
                return [{'bbox': f.bbox.astype(float).tolist(), 'keypoints': f.kps.astype(float).tolist(),
                         'confidence': float(f.det_score), 'embedding': unit(f.embedding).tolist()} for f in faces]
            except Exception as exc:
                raise AppError('人脸模型推理失败，请检查模型与运行环境', 503) from exc


engine = FaceEngine()


def annotate(image: np.ndarray, faces: list[dict]) -> np.ndarray:
    result = image.copy()
    for face in faces:
        x1, y1, x2, y2 = [int(x) for x in face['bbox']]
        cv2.rectangle(result, (x1, y1), (x2, y2), (80, 220, 40), 2)
        cv2.putText(result, f"{face['confidence']:.3f}", (max(0, x1), max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .6, (80, 220, 40), 2)
        for x, y in face['keypoints']:
            cv2.circle(result, (int(x), int(y)), 3, (255, 160, 20), -1)
    return result


def public_faces(image: np.ndarray, faces: list[dict], crops: bool = True) -> list[dict]:
    from insightface.utils.face_align import norm_crop
    result = []
    for face in faces:
        row = {k: v for k, v in face.items() if k != 'embedding'}
        if crops:
            row['aligned_crop'] = data_url(norm_crop(image, np.asarray(face['keypoints'], dtype=np.float32)))
        result.append(row)
    return result


def detect(image: np.ndarray) -> dict:
    start = time.perf_counter()
    faces = engine.infer(image)
    elapsed = (time.perf_counter() - start) * 1000
    return {'faces': public_faces(image, faces), 'count': len(faces), 'elapsed_ms': elapsed,
            'image': data_url(annotate(image, faces))}
