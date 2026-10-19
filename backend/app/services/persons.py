import logging
import uuid
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.algorithms.face_detector import engine
from app.algorithms.face_recognizer import unit
from app.algorithms.light_analysis import analyze
from app.core.config import DATA
from app.core.errors import AppError
from app.models.entities import Person, FaceSample, Dataset, RecognitionRecord
from app.services.images import digest, png
from app.services.storage import queue_sample_deletion, purge_pending_samples

logger = logging.getLogger(__name__)


def person_view(person: Person, detail: bool = False) -> dict:
    result = {
        "id": person.id,
        "name": person.name,
        "note": person.note,
        "created_at": person.created_at.isoformat(),
        "sample_count": len(person.samples),
    }
    if detail:
        result["samples"] = [
            {
                "id": s.id,
                "quality": s.quality,
                "dimensions": len(s.embedding),
                "capture_id": s.capture_id,
                "model_fingerprint": s.model_fingerprint,
                "image_url": f"/api/person/{person.id}/samples/{s.id}",
            }
            for s in person.samples
        ]
    return result


def get_person(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise AppError("人员不存在", 404)
    return person


def register(
    db: Session, name: str, note: str, images: list[np.ndarray], capture_id: str
) -> Person:
    if not name.strip() or len(name.strip()) > 80 or len(note) > 500:
        raise AppError("姓名须为 1–80 个字符，备注最多 500 字")
    if not 1 <= len(images) <= 10:
        raise AppError("每次注册须上传 1–10 张参考照片")
    if not capture_id.strip() or len(capture_id) > 120:
        raise AppError("请提供 1–120 字的采集会话编号，用于防止评估泄漏")
    seen = set(db.scalars(select(FaceSample.digest)).all())
    captures = set()
    for dataset in db.scalars(select(Dataset)):
        seen.update(x["digest"] for x in dataset.manifest["items"])
        captures.update(x["capture_id"] for x in dataset.manifest["items"])
    if capture_id in captures:
        raise AppError("采集会话已用于校准或测试，不可用于注册", 409)
    prepared = []
    for index, image in enumerate(images):
        hash_value = digest(image)
        if hash_value in seen:
            raise AppError(f"第 {index + 1} 张照片重复，或已用于校准/测试", 409)
        seen.add(hash_value)
        faces = engine.infer(image)
        if len(faces) != 1:
            raise AppError(
                f"第 {index + 1} 张照片检测到 {len(faces)} 张人脸；注册必须恰有一张人脸", 422
            )
        prepared.append((image, hash_value, faces[0]))
    person = Person(name=name.strip(), note=note.strip())
    written = []
    try:
        db.add(person)
        db.flush()
        for image, hash_value, face in prepared:
            filename = f"{uuid.uuid4().hex}.png"
            path = DATA / "samples" / filename
            written.append(path)
            path.write_bytes(png(image))
            path.chmod(0o600)
            x1, y1, x2, y2 = map(int, face["bbox"])
            crop = image[max(0, y1) : min(image.shape[0], y2), max(0, x1) : min(image.shape[1], x2)]
            quality = analyze(crop) if min(crop.shape[:2]) >= 8 else analyze(image)
            quality["detection_confidence"] = face["confidence"]
            db.add(
                FaceSample(
                    person_id=person.id,
                    path=filename,
                    digest=hash_value,
                    capture_id=capture_id,
                    embedding=face["embedding"],
                    quality=quality,
                    model_fingerprint=engine.fingerprint,
                )
            )
        db.commit()
        return person
    except Exception:
        db.rollback()
        if written:
            try:
                queue_sample_deletion(db, [path.name for path in written])
                db.commit()
                purge_pending_samples(db)
            except Exception:
                db.rollback()
                logger.exception("Interrupted registration files will be recovered at startup")
        raise


def gallery(db: Session, target: int | None = None) -> list[dict]:
    engine.load()
    persons = (
        [get_person(db, target)]
        if target is not None
        else list(db.scalars(select(Person).order_by(Person.id)))
    )
    result = []
    for person in persons:
        if any(s.model_fingerprint != engine.fingerprint for s in person.samples):
            raise AppError("身份库模型指纹与当前模型不一致，请重新注册相关样本", 409)
        if person.samples:
            template = unit(np.mean([unit(s.embedding) for s in person.samples], axis=0))
            result.append({"id": person.id, "name": person.name, "embedding": template.tolist()})
    return result


def delete_people(db: Session, person_ids: list[int]) -> dict:
    """Validate the entire selection before deleting any identities or files."""
    ids = sorted(set(person_ids))
    people = list(db.scalars(select(Person).where(Person.id.in_(ids)).order_by(Person.id)))
    missing = set(ids) - {person.id for person in people}
    if missing:
        raise AppError(
            "部分身份已不存在，请刷新列表后重新选择（编号："
            + "、".join(map(str, sorted(missing)))
            + "）",
            409,
        )
    queue_sample_deletion(db, [sample.path for person in people for sample in person.samples])
    selected = set(ids)
    for row in db.scalars(select(RecognitionRecord)):
        result = row.result
        if (
            row.person_id in selected
            or result.get("target_person_id") in selected
            or any(
                candidate.get("person_id") in selected for candidate in result.get("candidates", [])
            )
        ):
            db.delete(row)
    for person in people:
        db.delete(person)
    db.commit()
    cleanup = purge_pending_samples(db)
    return {"deleted": ids, "count": len(ids), "cleanup": cleanup}
