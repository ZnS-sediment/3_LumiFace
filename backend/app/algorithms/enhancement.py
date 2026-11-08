"""All transforms use uint8 BGR input/output and validated shared options."""

import cv2
import numpy as np
from app.schemas.contracts import EnhanceOptions
from app.algorithms.light_analysis import analyze, validate


def gamma(image: np.ndarray, value: float = 0.65) -> np.ndarray:
    validate(image)
    if not 0.15 <= value <= 4:
        raise ValueError("gamma must be in [0.15,4]")
    table = np.clip((np.arange(256, dtype=np.float32) / 255) ** value * 255, 0, 255).astype(
        np.uint8
    )
    return cv2.LUT(image, table)


def clahe(image: np.ndarray, clip_limit: float = 2) -> np.ndarray:
    validate(image)
    if not 0.1 <= clip_limit <= 8:
        raise ValueError("clip_limit must be in [0.1,8]")
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def luminance_transform(image: np.ndarray, luminance: np.ndarray) -> np.ndarray:
    ycc = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    ycc[:, :, 0] = np.clip(luminance, 0, 255).astype(np.uint8)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)


def retinex(image: np.ndarray, sigma: float = 30, strength: float = 0.6) -> np.ndarray:
    validate(image)
    if not 3 <= sigma <= 100 or not 0 <= strength <= 1:
        raise ValueError("invalid retinex parameters")
    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32) + 1
    # Estimate illumination at a bounded resolution, preventing expensive large Gaussian kernels.
    scale = min(1.0, 512 / max(y.shape))
    small = cv2.resize(y, None, fx=scale, fy=scale) if scale < 1 else y
    light = cv2.GaussianBlur(small, (0, 0), max(1, sigma * scale))
    light = cv2.resize(light, (y.shape[1], y.shape[0]))
    result = np.log(y) - np.log(np.maximum(light, 1))
    lo, hi = np.percentile(result, [1, 99])
    if hi - lo < 1e-5:
        return image.copy()
    mapped = np.clip((result - lo) / (hi - lo), 0, 1) * 255
    return luminance_transform(image, (1 - strength) * (y - 1) + strength * mapped)


def exposure(image: np.ndarray, target: float = 115, strength: float = 0.6) -> np.ndarray:
    validate(image)
    if not 40 <= target <= 190 or not 0 <= strength <= 1:
        raise ValueError("invalid exposure parameters")
    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
    gain = np.clip(target / max(float(y.mean()), 1), 0.5, 3)
    return luminance_transform(image, y * (1 + strength * (gain - 1)))


def normalize(image: np.ndarray, strength: float = 0.6) -> np.ndarray:
    validate(image)
    if not 0 <= strength <= 1:
        raise ValueError("invalid strength")
    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
    lo, hi = np.percentile(y, [2, 98])
    if hi - lo < 1:
        return image.copy()
    mapped = np.clip((y - lo) / (hi - lo), 0, 1) * 220 + 15
    return luminance_transform(image, (1 - strength) * y + strength * mapped)


def resolve_options(image: np.ndarray, options: EnhanceOptions) -> EnhanceOptions:
    """Deterministic image-only tuning; never inspect identity labels or match scores.

    Analyze at most 512 px per side. Historical fixed-parameter calls remain unchanged.
    Bounds limit noise amplification and preserve reproducible per-image parameters.
    """
    validate(image)
    if not options.auto_parameters or options.method not in {"gamma", "clahe", "retinex"}:
        return options.model_copy(update={"auto_parameters": False})
    h, w = image.shape[:2]
    scale = min(1, 512 / max(h, w))
    small = cv2.resize(image, (max(8, round(w * scale)), max(8, round(h * scale))))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    histogram = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    histogram /= gray.size
    levels = np.arange(256, dtype=np.float64) / 255
    values: dict[str, float | bool] = {"auto_parameters": False}
    if options.method == "gamma":
        # Solve for the expected output brightness using the whole histogram,
        # rather than taking a logarithm of the mean of a nonuniform image.
        low, high = 0.35, 1.8
        if histogram[0] + histogram[255] > 0.995:
            value = 1.0  # Gamma cannot restore clipped black or white pixels.
        else:
            for _ in range(18):
                value = (low + high) / 2
                if float(np.dot(histogram, levels**value) * 255) > 115:
                    low = value
                else:
                    high = value
            value = (low + high) / 2
        values["gamma"] = round(value, 3)
    else:
        blocks = [
            float(block.mean())
            for row in np.array_split(gray, 4)
            for block in np.array_split(row, 4, axis=1)
        ]
        uneven = float(np.clip(np.std(blocks) / max(float(gray.mean()), 20), 0, 1))
        residual = gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32)
        noise = float(np.clip(np.median(np.abs(residual)) / 18, 0, 1))
        if options.method == "clahe":
            lo, hi = np.percentile(gray, [10, 90])
            low_contrast = float(np.clip(1 - (hi - lo) / 180, 0, 1))
            clip = 1.15 + (2 * low_contrast + 0.9 * uneven) * (1 - 0.7 * noise)
            values["clip_limit"] = round(float(np.clip(clip, 1.1, 3.8)), 2)
        else:
            values["sigma"] = round(float(np.clip(min(h, w) * (0.08 + 0.12 * uneven), 3, 100)), 2)
            shadows = float((gray < 45).mean())
            values["strength"] = round(
                float(
                    np.clip((0.15 + 0.5 * uneven + 0.15 * shadows) * (1 - 0.6 * noise), 0.1, 0.75)
                ),
                3,
            )
    return options.model_copy(update=values)


def enhance(image: np.ndarray, options: EnhanceOptions) -> tuple[np.ndarray, list[str]]:
    validate(image)
    automatic = options.auto_parameters
    options = resolve_options(image, options)
    prefix = "自动参数 " if automatic else ""
    method = options.method
    if method == "original":
        return image.copy(), ["关闭增强"]
    if method == "gamma":
        return gamma(image, options.gamma), [f"{prefix}Gamma={options.gamma}"]
    if method == "clahe":
        return clahe(image, options.clip_limit), [f"{prefix}CLAHE clip={options.clip_limit}"]
    if method == "retinex":
        return retinex(image, options.sigma, options.strength), [
            f"{prefix}SSR sigma={options.sigma}, strength={options.strength}"
        ]
    if method == "exposure":
        return exposure(image, options.target, options.strength), [f"曝光 target={options.target}"]
    if method == "normalize":
        return normalize(image, options.strength), ["亮度分位数归一化"]
    stats = analyze(image)
    scene = stats["scene"]
    if scene == "low_light":
        g = float(
            np.clip(np.log(115 / 255) / np.log(max(stats["mean_brightness"], 1) / 255), 0.35, 0.9)
        )
        return clahe(gamma(image, g), 1.6), [f"低照度 Gamma={g:.3f}", "CLAHE clip=1.6"]
    if scene == "backlight":
        return exposure(clahe(image, 2), 110, 0.35), ["逆光局部对比度增强", "保守曝光补偿"]
    if scene == "uneven":
        return retinex(image, 30, 0.45), ["光照不均匀 SSR strength=0.45"]
    if scene == "overexposed":
        return gamma(image, 1.15), ["过曝保守 Gamma=1.15；无法恢复饱和细节"]
    return image.copy(), ["正常光照，不增强"]
