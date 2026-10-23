"""Turn explicitly labelled image uploads into the existing reproducible experiment flow."""

import io
import hashlib
import json
import shutil
import uuid
import zipfile
from datetime import datetime
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.core.config import DATA, MAX_ARCHIVE, MAX_DATASET_IMAGES
from app.core.errors import AppError
from app.schemas.contracts import ImageTestRequest, ExperimentRequest
from app.services.datasets import import_dataset
from app.services.experiments import create_experiment
from app.services.images import read_upload


def create_image_test(db: Session, files: list[UploadFile], request: ImageTestRequest):
    if not 1 <= len(files) <= MAX_DATASET_IMAGES or len(files) != len(request.items):
        raise AppError("请选择 1–500 张图片，每张图片必须有对应的真实身份标签", 422)
    manifest = {
        "name": "多图测试 " + datetime.now().strftime("%m-%d %H:%M:%S"),
        "split": "test",
        "source": "网页多图测试，身份和场景由用户确认，采集独立性未核验",
        "license": "用户提供，仅在本机测试",
        "real_capture": False,
        "localization_protocol": "single_face_presence",
        "items": [],
    }
    buffer = io.BytesIO()
    total_bytes = 0
    capture = "image-test-" + uuid.uuid4().hex
    with zipfile.ZipFile(buffer, "w") as archive:
        for index, (file, label) in enumerate(zip(files, request.items)):
            if file.filename != label.filename:
                raise AppError("图片与身份标签顺序不一致，请重新选择图片", 422)
            raw, image = read_upload(file)
            total_bytes += len(raw)
            if total_bytes > MAX_ARCHIVE:
                raise AppError("本次图片合计不得超过 100 MB，请分次测试", 413)
            filename = f"images/{index}.png"
            archive.writestr(filename, raw)
            manifest["items"].append(
                {
                    "file": filename,
                    "capture_id": capture,
                    "scene": label.scene,
                    "faces": [
                        {
                            # Placeholder extent for presence scoring, never an IoU ground-truth box.
                            "bbox": [0, 0, image.shape[1], image.shape[0]],
                            "person_id": label.person_id,
                            "subject": str(label.person_id)
                            if label.person_id
                            else "unknown-"
                            + hashlib.sha256(
                                label.filename.rpartition("/")[0].encode()
                            ).hexdigest()[:24],
                        }
                    ],
                }
            )
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    dataset = import_dataset(db, buffer.getvalue())
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
                methods=request.methods,
                threshold=request.threshold,
            ),
        )
    except Exception:
        db.rollback()
        db.delete(dataset)
        db.commit()
        shutil.rmtree(DATA / "datasets" / dataset.directory, ignore_errors=True)
        raise
