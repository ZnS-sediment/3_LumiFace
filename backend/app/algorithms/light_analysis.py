import cv2
import numpy as np
from app.core.errors import AppError


def validate(image: np.ndarray) -> None:
    if (
        not isinstance(image, np.ndarray)
        or image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or min(image.shape[:2]) < 8
    ):
        raise AppError("算法输入须为至少 8×8 的 uint8 BGR 图像")


def analyze(image: np.ndarray) -> dict:
    validate(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    mean = float(gray.mean())
    under, over = float((gray < 30).mean()), float((gray > 240).mean())
    blocks = [
        float(b.mean())
        for row in np.array_split(gray, 4, axis=0)
        for b in np.array_split(row, 4, axis=1)
    ]
    uneven = float(np.std(blocks) / max(mean, 1))
    center = gray[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
    mask = np.ones(gray.shape, dtype=bool)
    mask[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = False
    backlight_gap = float(gray[mask].mean() - center.mean())
    if backlight_gap > 45 and float(center.mean()) < 110:
        scene = "backlight"
    elif mean < 75 or under > 0.55:
        scene = "low_light"
    elif over > 0.18:
        scene = "overexposed"
    elif uneven > 0.4:
        scene = "uneven"
    else:
        scene = "normal"
    return {
        "mean_brightness": mean,
        "histogram": np.bincount(gray.ravel(), minlength=256).tolist(),
        "underexposed_ratio": under,
        "overexposed_ratio": over,
        "contrast": float(gray.std()),
        "illumination_unevenness": uneven,
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "backlight_gap": backlight_gap,
        "scene": scene,
        "width": w,
        "height": h,
        "scene_note": "启发式亮度分类，不能据此判定红外成像模态",
    }
