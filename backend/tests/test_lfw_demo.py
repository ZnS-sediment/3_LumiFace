"""Guard the published crop geometry and preservation of downloaded originals."""

import importlib.util
import io
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "lfw_demo", Path(__file__).resolve().parents[2] / "scripts/prepare_lfw_demo.py"
)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_fixed_crop_preserves_each_retained_pixel_and_adds_only_border():
    image = np.random.default_rng(11).integers(0, 256, (250, 250, 3), dtype=np.uint8)
    raw = io.BytesIO()
    Image.fromarray(image).save(raw, format="PNG")
    result = np.array(Image.open(io.BytesIO(demo.single_person_image(raw.getvalue()))))
    assert result.shape == (283, 248, 3)
    assert np.array_equal(result[64:-64, 64:-64], image[55:210, 65:185])
    assert np.all(result[:64] == 128) and np.all(result[-64:] == 128)
    assert np.all(result[:, :64] == 128) and np.all(result[:, -64:] == 128)


def test_wrong_source_dimensions_are_rejected_instead_of_silently_cropped():
    raw = io.BytesIO()
    Image.new("RGB", (200, 200)).save(raw, format="PNG")
    with pytest.raises(ValueError, match="尺寸"):
        demo.single_person_image(raw.getvalue())


def test_corrupt_existing_download_is_not_overwritten(tmp_path):
    source = tmp_path / "source.tgz"
    source.write_bytes(b"existing user download")
    with pytest.raises(RuntimeError, match="未覆盖"):
        demo.download(source)
    assert source.read_bytes() == b"existing user download"
