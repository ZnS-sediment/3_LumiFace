"""Check that the three published simulation inputs have distinct illumination fields."""

import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "lfw_lighting", Path(__file__).resolve().parents[2] / "scripts/prepare_lfw_lighting.py"
)
lighting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lighting)


def test_normal_preserves_pixels_and_low_light_darkens_without_moving_geometry():
    source = np.tile(np.arange(248, dtype=np.uint8)[None, :, None], (283, 1, 3))
    saved = source.copy()
    assert np.array_equal(lighting.simulate(source, "normal", 1), source)
    result = lighting.simulate(source, "low_light", 1)
    assert result.shape == source.shape and result.dtype == np.uint8
    assert 0.15 < result.mean() / source.mean() < 0.35
    assert np.all(np.diff(result[100, :, 0].astype(int)) >= 0)
    assert np.array_equal(source, saved)


def test_backlight_has_bright_background_and_dark_central_face_region():
    source = np.full((283, 248, 3), 128, dtype=np.uint8)
    result = lighting.simulate(source, "backlight", 2)
    face = result[105:175, 100:150].mean()
    background = result[:32].mean()
    assert face < 80 and background > 200 and background / face > 3


def test_uneven_light_is_directional_repeatable_and_keeps_color_channel_order():
    source = np.full((283, 248, 3), [80, 120, 160], dtype=np.uint8)
    result = lighting.simulate(source, "uneven", 1)
    assert np.array_equal(result, lighting.simulate(source, "uneven", 1))
    assert result[:, -32:].mean() / result[:, :32].mean() > 3
    opposite = lighting.simulate(source, "uneven", 2)
    assert np.allclose(result, opposite[:, ::-1], atol=1)
    assert np.all(result[:, :, 0] <= result[:, :, 1]) and np.all(result[:, :, 1] <= result[:, :, 2])


def test_invalid_scene_and_overwriting_source_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        lighting.simulate(np.zeros((283, 248, 3), dtype=np.uint8), "infrared", 1)
    with pytest.raises(ValueError, match="overwrite"):
        lighting.build(tmp_path / "same.zip", tmp_path / "same.zip")
