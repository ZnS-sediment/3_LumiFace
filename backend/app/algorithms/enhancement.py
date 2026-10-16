"""All transforms use uint8 BGR input/output and validated shared options."""
import cv2
import numpy as np
from app.schemas.contracts import EnhanceOptions
from app.algorithms.light_analysis import analyze, validate


def gamma(image: np.ndarray, value: float = 0.65) -> np.ndarray:
    validate(image)
    if not 0.15 <= value <= 4:
        raise ValueError('gamma must be in [0.15,4]')
    table = np.clip((np.arange(256, dtype=np.float32) / 255) ** value * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(image, table)


def clahe(image: np.ndarray, clip_limit: float = 2) -> np.ndarray:
    validate(image)
    if not 0.1 <= clip_limit <= 8:
        raise ValueError('clip_limit must be in [0.1,8]')
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
        raise ValueError('invalid retinex parameters')
    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32) + 1
    # Estimate illumination at a bounded resolution, preventing expensive large Gaussian kernels.
    scale = min(1., 512 / max(y.shape))
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
        raise ValueError('invalid exposure parameters')
    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
    gain = np.clip(target / max(float(y.mean()), 1), 0.5, 3)
    return luminance_transform(image, y * (1 + strength * (gain - 1)))


def normalize(image: np.ndarray, strength: float = 0.6) -> np.ndarray:
    validate(image)
    if not 0 <= strength <= 1:
        raise ValueError('invalid strength')
    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
    lo, hi = np.percentile(y, [2, 98])
    if hi - lo < 1:
        return image.copy()
    mapped = np.clip((y - lo) / (hi - lo), 0, 1) * 220 + 15
    return luminance_transform(image, (1 - strength) * y + strength * mapped)


def enhance(image: np.ndarray, options: EnhanceOptions) -> tuple[np.ndarray, list[str]]:
    validate(image)
    method = options.method
    if method == 'original':
        return image.copy(), ['关闭增强']
    if method == 'gamma':
        return gamma(image, options.gamma), [f'Gamma={options.gamma}']
    if method == 'clahe':
        return clahe(image, options.clip_limit), [f'CLAHE clip={options.clip_limit}']
    if method == 'retinex':
        return retinex(image, options.sigma, options.strength), [f'SSR sigma={options.sigma}, strength={options.strength}']
    if method == 'exposure':
        return exposure(image, options.target, options.strength), [f'曝光 target={options.target}']
    if method == 'normalize':
        return normalize(image, options.strength), ['亮度分位数归一化']
    stats = analyze(image)
    scene = stats['scene']
    if scene == 'low_light':
        g = float(np.clip(np.log(115 / 255) / np.log(max(stats['mean_brightness'], 1) / 255), 0.35, 0.9))
        return clahe(gamma(image, g), 1.6), [f'低照度 Gamma={g:.3f}', 'CLAHE clip=1.6']
    if scene == 'backlight':
        return exposure(clahe(image, 2), 110, 0.35), ['逆光局部对比度增强', '保守曝光补偿']
    if scene == 'uneven':
        return retinex(image, 30, 0.45), ['光照不均匀 SSR strength=0.45']
    if scene == 'overexposed':
        return gamma(image, 1.15), ['过曝保守 Gamma=1.15；无法恢复饱和细节']
    return image.copy(), ['正常光照，不增强']
