"""The new uneven-light scene changes illumination, not geometry or identity labels."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "three_scene_demo", Path(__file__).resolve().parents[2] / "scripts/prepare_three_scene_demo.py"
)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.mark.parametrize("seed", [0, 1, 17, 394])
def test_uneven_illumination_is_repeatable_and_directional(seed):
    source = np.full((80, 64, 3), 160, np.uint8)
    original = source.copy()
    result = demo.uneven_light(source, seed)
    assert np.array_equal(source, original)
    assert result.shape == source.shape and result.dtype == np.uint8
    assert np.array_equal(result, demo.uneven_light(source, seed))
    left, right = result[:, :16].mean(), result[:, -16:].mean()
    assert max(left, right) / min(left, right) > 2.5
    assert result.max() <= 255 and result.min() >= 0
    assert np.array_equal(result[:, :, 0], result[:, :, 1])


def test_three_scene_folders_match_available_methods():
    assert set(demo.SCENES) == {"backlight", "uneven", "low_light"}
    assert [value[0] for value in demo.SCENES.values()] == [
        "01_逆光_CLAHE",
        "02_光照不均_Retinex",
        "03_低照度_Gamma",
    ]
    assert demo.seed_for("ATT_s01", "06.png") == demo.seed_for("ATT_s01", "06.png")
    assert demo.seed_for("ATT_s01", "06.png") != demo.seed_for("ATT_s02", "06.png")
