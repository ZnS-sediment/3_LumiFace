import numpy as np
import pytest
from app.algorithms.light_analysis import analyze
from app.algorithms.enhancement import enhance, gamma
from app.algorithms.face_recognizer import match, unit
from app.schemas.contracts import EnhanceOptions
from app.core.errors import AppError


@pytest.mark.parametrize(
    "method", ["original", "gamma", "clahe", "retinex", "exposure", "normalize", "adaptive"]
)
@pytest.mark.parametrize("value", [0, 30, 120, 255])
def test_extreme_images_are_finite_uint8(method, value):
    image = np.full((32, 40, 3), value, dtype=np.uint8)
    original = image.copy()
    output, steps = enhance(image, EnhanceOptions(method=method))
    assert output.shape == image.shape and output.dtype == np.uint8
    assert np.isfinite(output).all() and steps
    assert np.array_equal(image, original)


def test_gamma_direction_and_identity():
    image = np.full((16, 16, 3), 50, dtype=np.uint8)
    assert gamma(image, 0.5).mean() > image.mean()
    assert gamma(image, 2).mean() < image.mean()
    assert np.array_equal(enhance(image, EnhanceOptions(method="original"))[0], image)


def test_scene_classification_and_histogram():
    image = np.full((100, 100, 3), 180, dtype=np.uint8)
    image[25:75, 25:75] = 35
    stats = analyze(image)
    assert stats["scene"] == "backlight"
    assert sum(stats["histogram"]) == 10000
    assert analyze(np.zeros_like(image))["scene"] == "low_light"
    assert analyze(np.full_like(image, 255))["scene"] == "overexposed"


def test_normal_lighting_is_unchanged():
    image = np.full((20, 20, 3), 130, dtype=np.uint8)
    assert np.array_equal(enhance(image, EnhanceOptions())[0], image)


def test_invalid_images_and_zero_embedding():
    with pytest.raises(AppError):
        analyze(np.ones((4, 4, 3)))
    with pytest.raises(AppError):
        unit([0, 0, 0])
    with pytest.raises(AppError):
        unit([float("nan"), 1])
    with pytest.raises(ValueError):
        EnhanceOptions(gamma=float("nan"))
    with pytest.raises(ValueError):
        EnhanceOptions(method="fake")


def test_unknown_rejection_and_empty_gallery():
    people = [{"id": 1, "name": "A", "embedding": [1, 0]}]
    assert match([0, 1], people, 0.45)["person_id"] is None
    assert match([1, 0], people, 0.45)["confirmed"]
    assert match([1, 0], [], 0.45)["similarity"] is None


def test_automatic_gamma_responds_to_brightness_and_preserves_input():
    from app.algorithms.enhancement import resolve_options

    dark = np.full((64, 96, 3), 25, np.uint8)
    bright = np.full_like(dark, 180)
    options = EnhanceOptions(method="gamma", auto_parameters=True)
    dark_options = resolve_options(dark, options)
    bright_options = resolve_options(bright, options)
    assert dark_options.gamma < 1 < bright_options.gamma
    enhanced, steps = enhance(dark, options)
    assert 100 < enhanced.mean() < 125
    assert (dark == 25).all() and options.auto_parameters
    assert "自动参数" in steps[0]
    assert resolve_options(dark, options) == dark_options


def test_automatic_clahe_limits_noise_and_retinex_uses_size_and_unevenness():
    from app.algorithms.enhancement import resolve_options

    rng = np.random.default_rng(104)
    uniform = np.full((128, 128, 3), 100, np.uint8)
    noisy = np.clip(
        uniform.astype(float) + rng.normal(0, 18, uniform.shape[:2])[:, :, None], 0, 255
    ).astype(np.uint8)
    clahe_options = EnhanceOptions(method="clahe", auto_parameters=True)
    assert (
        resolve_options(noisy, clahe_options).clip_limit
        < resolve_options(uniform, clahe_options).clip_limit
    )
    uneven = uniform.copy()
    uneven[:, :64] = 20
    uneven[:, 64:] = 180
    retinex_options = EnhanceOptions(method="retinex", auto_parameters=True)
    flat = resolve_options(uniform, retinex_options)
    shadow = resolve_options(uneven, retinex_options)
    large = resolve_options(np.repeat(np.repeat(uneven, 2, axis=0), 2, axis=1), retinex_options)
    assert flat.strength < shadow.strength and flat.sigma < shadow.sigma < large.sigma
    assert 3 <= large.sigma <= 100 and 0 <= shadow.strength <= 1


@pytest.mark.parametrize("method", ["gamma", "clahe", "retinex"])
@pytest.mark.parametrize("value", [0, 25, 120, 255])
def test_automatic_extremes_are_finite_and_fixed_mode_is_compatible(method, value):
    from app.algorithms.enhancement import resolve_options

    image = np.full((8, 8, 3), value, np.uint8)
    options = EnhanceOptions(method=method, auto_parameters=True)
    output, _ = enhance(image, options)
    assert output.dtype == np.uint8 and output.shape == image.shape
    assert np.array_equal(output, enhance(image, resolve_options(image, options))[0])
    fixed = EnhanceOptions(method=method)
    assert resolve_options(image, fixed) == fixed
