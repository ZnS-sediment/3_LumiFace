from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Method = Literal['original', 'gamma', 'clahe', 'retinex', 'exposure', 'normalize', 'adaptive']
Scene = Literal['normal', 'low_light', 'backlight', 'infrared', 'overexposed', 'uneven']


class Response(BaseModel):
    data: Any
    message: str = 'ok'


class EnhanceOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    method: Method = 'adaptive'
    gamma: float = Field(default=0.65, ge=0.15, le=4)
    clip_limit: float = Field(default=2.0, ge=0.1, le=8)
    sigma: float = Field(default=30, ge=3, le=100)
    target: float = Field(default=115, ge=40, le=190)
    strength: float = Field(default=0.6, ge=0, le=1)


class PersonEdit(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    note: str = Field(default='', max_length=500)


class TruthFace(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    bbox: tuple[float, float, float, float]
    person_id: int | None = Field(default=None, ge=1)
    subject: str = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def valid_bbox(self) -> 'TruthFace':
        x1, y1, x2, y2 = self.bbox
        if min(x1, y1) < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError('bbox 必须为有效 [x1,y1,x2,y2]')
        return self


class DatasetItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file: str = Field(min_length=1, max_length=200)
    scene: Scene
    capture_id: str = Field(min_length=1, max_length=120)
    faces: list[TruthFace] = Field(max_length=100)


class Manifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    split: Literal['calibration', 'test']
    source: str = Field(min_length=1, max_length=1000)
    license: str = Field(min_length=1, max_length=1000)
    real_capture: bool
    items: list[DatasetItem] = Field(min_length=1, max_length=500)


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    dataset_id: int
    threshold: float = Field(default=0.45, ge=-1, le=1)
    methods: list[Method] = Field(default=['original', 'gamma', 'clahe', 'retinex', 'adaptive'], min_length=1, max_length=7)
    calibration_id: int | None = None


class CalibrationRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    experiment_id: int
    target_far: float = Field(default=0.01, ge=0, le=0.2)
