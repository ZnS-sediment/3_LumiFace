from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import MAX_DATASET_IMAGES, DEFAULT_THRESHOLD

Method = Literal["original", "gamma", "clahe", "retinex", "exposure", "normalize", "adaptive"]
Scene = Literal["normal", "low_light", "backlight", "infrared", "overexposed", "uneven"]


class Response(BaseModel):
    data: Any
    message: str = "ok"


class EnhanceOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    method: Method = "adaptive"
    gamma: float = Field(default=0.65, ge=0.15, le=4)
    clip_limit: float = Field(default=2.0, ge=0.1, le=8)
    sigma: float = Field(default=30, ge=3, le=100)
    target: float = Field(default=115, ge=40, le=190)
    strength: float = Field(default=0.6, ge=0, le=1)


class PersonEdit(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=500)


class PersonBatchDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_ids: list[Annotated[int, Field(strict=True, ge=1)]] = Field(
        min_length=1, max_length=1000
    )


class TruthFace(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    bbox: tuple[float, float, float, float]
    person_id: int | None = Field(default=None, ge=1)
    subject: str = Field(min_length=1, max_length=100)
    eyes: tuple[tuple[float, float], tuple[float, float]] | None = None

    @model_validator(mode="after")
    def valid_bbox(self) -> "TruthFace":
        x1, y1, x2, y2 = self.bbox
        if min(x1, y1) < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError("bbox 必须为有效 [x1,y1,x2,y2]")
        return self


class DatasetItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str = Field(min_length=1, max_length=200)
    scene: Scene
    capture_id: str = Field(min_length=1, max_length=120)
    faces: list[TruthFace] = Field(max_length=100)


class SceneEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(default="", max_length=1000)
    annotation_basis: Literal[
        "dataset_metadata", "manual_capture_log", "brightness_only", "unspecified"
    ] = "unspecified"
    modality: Literal["rgb", "nir", "lwir", "swir", "unknown"] = "unknown"
    active_illumination: bool = False
    night_confirmed: bool = False
    backlight_confirmed: bool = False
    low_light_confirmed: bool = False


class ResearchProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="exploratory", max_length=200)
    capture_independence: Literal[
        "session_disjoint", "condition_disjoint", "frame_disjoint", "unknown"
    ] = "unknown"
    scene_evidence: dict[Scene, SceneEvidence] = Field(default_factory=dict)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    split: Literal["calibration", "test"]
    source: str = Field(min_length=1, max_length=1000)
    license: str = Field(min_length=1, max_length=1000)
    real_capture: bool
    localization_protocol: Literal["iou", "eye_containment", "single_face_presence"] = "iou"
    protocol: ResearchProtocol = Field(default_factory=ResearchProtocol)
    items: list[DatasetItem] = Field(min_length=1, max_length=MAX_DATASET_IMAGES)


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    dataset_id: int
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=-1, le=1)
    methods: list[Method] = Field(
        default=["original", "gamma", "clahe", "retinex", "adaptive"], min_length=1, max_length=7
    )
    calibration_id: int | None = None


class CalibrationRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    experiment_id: int
    target_far: float = Field(default=0.01, ge=0, le=0.2)
