"""Turn explicitly labelled image uploads into the existing reproducible experiment flow."""

import hashlib
import shutil
import uuid
from datetime import datetime
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.core.config import DATA, MAX_ARCHIVE, MAX_DATASET_IMAGES
from app.core.errors import AppError
from app.schemas.contracts import ImageTestRequest, ExperimentRequest, DatasetMetadata, DatasetItem
from app.services.datasets import store_dataset
from app.services.experiments import create_experiment, experiment_creation
from app.services.images import read_upload


def create_image_test(db: Session, files: list[UploadFile], request: ImageTestRequest):
    with experiment_creation(db):
        return _create_image_test(db, files, request)


def _create_image_test(db: Session, files: list[UploadFile], request: ImageTestRequest):
    if not 1 <= len(files) <= MAX_DATASET_IMAGES or len(files) != len(request.items):
        raise AppError(f"请选择 1–{MAX_DATASET_IMAGES} 张图片，每张图片必须有对应的真实身份标签", 422)
    metadata = DatasetMetadata(
        name="多图测试 " + datetime.now().strftime("%m-%d %H:%M:%S"),
        split="test",
        source="网页多图测试，身份和场景由用户确认，采集独立性未核验",
        license="用户提供，仅在本机测试",
        real_capture=False,
        localization_protocol="image_identity_presence",
    )
    capture = "image-test-" + uuid.uuid4().hex

    def images():
        total_bytes = 0
        for index, (file, label) in enumerate(zip(files, request.items)):
            if file.filename != label.filename:
                raise AppError("图片与身份标签顺序不一致，请重新选择图片", 422)
            raw, image = read_upload(file)
            total_bytes += len(raw)
            if total_bytes > MAX_ARCHIVE:
                raise AppError("本次图片合计不得超过 100 MB，请分次测试", 413)
            item = DatasetItem(
                file=f"images/{index}.png",
                capture_id=capture,
                scene=label.scene,
                faces=[
                    {
                        # Extent for presence scoring, never an IoU ground-truth annotation.
                        "bbox": [0, 0, image.shape[1], image.shape[0]],
                        "person_id": label.person_id,
                        "subject": str(label.person_id)
                        if label.person_id
                        else "unknown-"
                        + hashlib.sha256(label.filename.rpartition("/")[0].encode()).hexdigest()[
                            :24
                        ],
                    }
                ],
            )
            yield item, image

    dataset = store_dataset(db, metadata, images())
    try:
        dataset.manifest = {
            **dataset.manifest,
            "kind": "image_batch",
            "items": [
                {**item, "display_file": label.filename}
                for item, label in zip(dataset.manifest["items"], request.items)
            ],
        }
        return create_experiment(
            db,
            ExperimentRequest(
                dataset_id=dataset.id,
                name=request.name,
                methods=request.methods,
                **({"threshold": request.threshold} if "threshold" in request.model_fields_set else {}),
                auto_parameters=request.auto_parameters,
            ),
        )
    except Exception:
        db.rollback()
        db.delete(dataset)
        db.commit()
        shutil.rmtree(DATA / "datasets" / dataset.directory, ignore_errors=True)
        raise
