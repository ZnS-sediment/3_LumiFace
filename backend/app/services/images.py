import base64
import hashlib
import io
import warnings
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import UploadFile
from app.core.config import MAX_UPLOAD, MAX_PIXELS
from app.core.errors import AppError


def decode(raw: bytes) -> np.ndarray:
    if not raw or len(raw) > MAX_UPLOAD:
        raise AppError("图片为空或超过 12 MB 限制", 413 if raw else 400)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as im:
                if im.format not in ("JPEG", "PNG"):
                    raise AppError("仅支持真实 JPEG / PNG 图片", 415)
                if im.width * im.height > MAX_PIXELS or min(im.size) < 8:
                    raise AppError("图片尺寸须至少 8×8 且不超过 1600 万像素", 413)
                im.load()
                rgb = np.array(ImageOps.exif_transpose(im).convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except AppError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise AppError("无法解码图片，请上传完整的 JPG 或 PNG") from exc


def read_upload(file: UploadFile) -> tuple[bytes, np.ndarray]:
    raw = file.file.read(MAX_UPLOAD + 1)
    return raw, decode(raw)


def png(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise AppError("图片编码失败", 500)
    return data.tobytes()


def data_url(image: np.ndarray) -> str:
    return "data:image/png;base64," + base64.b64encode(png(image)).decode("ascii")


def digest(image: np.ndarray) -> str:
    """Canonical pixels detect duplicate images even when metadata/container differs."""
    return hashlib.sha256(str(image.shape).encode() + image.tobytes()).hexdigest()
