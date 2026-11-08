import io
import shutil
import uuid
import zipfile
from pathlib import PurePosixPath
from collections.abc import Iterable
import numpy as np
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import DATA, MAX_ARCHIVE, MAX_UPLOAD, MAX_DATASET_IMAGES
from app.core.errors import AppError
from app.models.entities import Dataset, FaceSample, Person
from app.schemas.contracts import Manifest, DatasetMetadata, DatasetItem
from app.services.images import decode, digest, png


def import_dataset(db: Session, raw: bytes) -> Dataset:
    if len(raw) > MAX_ARCHIVE:
        raise AppError("ZIP 压缩包不得超过 100 MB", 413)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            entries = {member.filename: member for member in members}
            if len(members) > 1001 or len(entries) != len(members):
                raise AppError("ZIP 文件数量超限或含重名条目")
            if any(
                PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or "\\" in name
                or ":" in name
                for name in entries
            ):
                raise AppError("ZIP 含非法路径")
            if sum(member.file_size for member in members) > 256 * 1024 * 1024:
                raise AppError("ZIP 解压总量不得超过 256 MB", 413)
            if (
                "manifest.json" not in entries
                or entries["manifest.json"].file_size > 2 * 1024 * 1024
            ):
                raise AppError("ZIP 根目录须包含不超过 2 MB 的 manifest.json")
            manifest = Manifest.model_validate_json(archive.read("manifest.json"))
            if len({item.file for item in manifest.items}) != len(manifest.items):
                raise AppError("manifest 中存在重复文件")

            def images():
                for item in manifest.items:
                    if item.file not in entries or entries[item.file].file_size > MAX_UPLOAD:
                        raise AppError(f"图片缺失或超过 12 MB：{item.file}")
                    yield item, decode(archive.read(item.file))

            return store_dataset(db, manifest, images())
    except (zipfile.BadZipFile, KeyError, ValidationError, ValueError, RuntimeError) as exc:
        raise AppError(f"无效数据包：{exc}") from exc


def store_dataset(
    db: Session, metadata: DatasetMetadata, images: Iterable[tuple[DatasetItem, np.ndarray]]
) -> Dataset:
    """Share validation/storage between ZIP imports and already decoded browser uploads."""
    directory = DATA / "datasets" / uuid.uuid4().hex
    try:
        references = {
            str(person_id): created.replace(tzinfo=None).isoformat()
            for person_id, created in db.execute(select(Person.id, Person.created_at))
        }
        samples = list(db.execute(select(FaceSample.digest, FaceSample.capture_id)))
        forbidden_hashes = {digest for digest, _ in samples}
        forbidden_captures = {capture for _, capture in samples}
        other_unknowns = set()
        for prior in db.scalars(select(Dataset)):
            if prior.split != metadata.split:
                forbidden_hashes.update(item["digest"] for item in prior.manifest["items"])
                forbidden_captures.update(item["capture_id"] for item in prior.manifest["items"])
                other_unknowns.update(
                    face["subject"]
                    for item in prior.manifest["items"]
                    for face in item["faces"]
                    if face["person_id"] is None
                )
        directory.mkdir(mode=0o700)
        items = []
        for index, (item, image) in enumerate(images):
            if index >= MAX_DATASET_IMAGES:
                raise AppError("数据集图片数量超限")
            image_hash = digest(image)
            if image_hash in forbidden_hashes or item.capture_id in forbidden_captures:
                raise AppError(f"{item.file} 与注册/其他数据划分存在图像或采集会话泄漏", 409)
            forbidden_hashes.add(image_hash)
            if (
                metadata.localization_protocol in {"single_face_presence", "image_identity_presence"}
                and len(item.faces) != 1
            ):
                raise AppError("图片存在性协议须每图恰有一个身份标注")
            for face in item.faces:
                if metadata.localization_protocol == "eye_containment" and face.eyes is None:
                    raise AppError("眼点包含协议需要独立眼点标注")
                if face.eyes and any(
                    not (0 <= x < image.shape[1] and 0 <= y < image.shape[0]) for x, y in face.eyes
                ):
                    raise AppError("眼点坐标超出图像尺寸")
                if face.person_id is not None and str(face.person_id) not in references:
                    raise AppError(f"未知 person_id：{face.person_id}")
                if face.person_id is None and face.subject in other_unknowns:
                    raise AppError("校准与测试的未知身份必须互斥", 409)
                if face.bbox[2] > image.shape[1] or face.bbox[3] > image.shape[0]:
                    raise AppError(f"{item.file} 的标注框超出经 EXIF 纠正后的图像尺寸")
            filename = f"{index}.png"
            path = directory / filename
            path.write_bytes(png(image))
            path.chmod(0o600)
            items.append({**item.model_dump(), "stored_file": filename, "digest": image_hash})
        if not items:
            raise AppError("数据集至少需要一张图片")
        record = Dataset(
            name=metadata.name,
            split=metadata.split,
            directory=directory.name,
            manifest={
                **metadata.model_dump(exclude={"items"}),
                "items": items,
                "person_references": {
                    str(face["person_id"]): references[str(face["person_id"])]
                    for item in items
                    for face in item["faces"]
                    if face["person_id"] is not None
                },
            },
        )
        db.add(record)
        db.commit()
        return record
    except Exception:
        db.rollback()
        shutil.rmtree(directory, ignore_errors=True)
        raise


def dataset_view(record: Dataset, detail: bool = False) -> dict:
    scenes = {}
    for item in record.manifest["items"]:
        scenes[item["scene"]] = scenes.get(item["scene"], 0) + 1
    result = {
        "id": record.id,
        "name": record.name,
        "split": record.split,
        "count": len(record.manifest["items"]),
        "scenes": scenes,
        "real_capture": record.manifest["real_capture"],
        "source": record.manifest["source"],
        "license": record.manifest["license"],
    }
    if detail:
        result["items"] = [
            {k: v for k, v in item.items() if k != "stored_file"}
            for item in record.manifest["items"]
        ]
    return result
