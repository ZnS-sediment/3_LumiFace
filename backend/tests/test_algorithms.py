import numpy as np
import pytest
from app.algorithms.light_analysis import analyze
from app.algorithms.enhancement import enhance, gamma
from app.algorithms.face_recognizer import match, unit
from app.schemas.contracts import EnhanceOptions
from app.core.errors import AppError


@pytest.mark.parametrize('method',['original','gamma','clahe','retinex','exposure','normalize','adaptive'])
@pytest.mark.parametrize('value',[0,30,120,255])
def test_extreme_images_are_finite_uint8(method,value):
    image=np.full((32,40,3),value,dtype=np.uint8)
    original=image.copy()
    output, steps=enhance(image,EnhanceOptions(method=method))
    assert output.shape==image.shape and output.dtype==np.uint8
    assert np.isfinite(output).all() and steps
    assert np.array_equal(image,original)


def test_gamma_direction_and_identity():
    image=np.full((16,16,3),50,dtype=np.uint8)
    assert gamma(image,.5).mean()>image.mean()
    assert gamma(image,2).mean()<image.mean()
    assert np.array_equal(enhance(image,EnhanceOptions(method='original'))[0],image)


def test_scene_classification_and_histogram():
    image=np.full((100,100,3),180,dtype=np.uint8)
    image[25:75,25:75]=35
    stats=analyze(image)
    assert stats['scene']=='backlight'
    assert sum(stats['histogram'])==10000
    assert analyze(np.zeros_like(image))['scene']=='low_light'
    assert analyze(np.full_like(image,255))['scene']=='overexposed'


def test_normal_lighting_is_unchanged():
    image=np.full((20,20,3),130,dtype=np.uint8)
    assert np.array_equal(enhance(image,EnhanceOptions())[0],image)


def test_invalid_images_and_zero_embedding():
    with pytest.raises(AppError):analyze(np.ones((4,4,3)))
    with pytest.raises(AppError):unit([0,0,0])
    with pytest.raises(AppError):unit([float('nan'),1])
    with pytest.raises(ValueError):EnhanceOptions(gamma=float('nan'))
    with pytest.raises(ValueError):EnhanceOptions(method='fake')


def test_unknown_rejection_and_empty_gallery():
    people=[{'id':1,'name':'A','embedding':[1,0]}]
    assert match([0,1],people,.45)['person_id'] is None
    assert match([1,0],people,.45)['confirmed']
    assert match([1,0],[],.45)['similarity'] is None
