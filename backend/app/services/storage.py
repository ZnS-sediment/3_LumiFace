"""Clean only application-generated registration copies, never download datasets."""

import logging
import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA
from app.core.errors import AppError
from app.models.entities import FaceSample, PendingSampleDeletion

SAMPLE_NAME = re.compile(r"[0-9a-f]{32}\.png")
logger = logging.getLogger(__name__)


def queue_sample_deletion(db: Session, filenames: list[str]) -> None:
    """The caller commits these jobs together with the owning database rows."""
    if any(not SAMPLE_NAME.fullmatch(name) for name in filenames):
        raise AppError("注册照片路径无效，已取消删除，请检查本地存储", 409)
    existing = set(db.scalars(select(PendingSampleDeletion.path)))
    db.add_all(PendingSampleDeletion(path=name) for name in set(filenames) - existing)


def purge_pending_samples(db: Session) -> dict:
    removed = 0
    pending = 0
    folder = DATA / "samples"
    referenced = set(db.scalars(select(FaceSample.path)))
    for job in db.scalars(select(PendingSampleDeletion)).all():
        if job.path in referenced:
            logger.warning("Cancelled cleanup of an actively registered sample: %s", job.path)
            db.delete(job)
            continue
        # Filenames are generated UUIDs; no caller-supplied path can escape samples.
        if not SAMPLE_NAME.fullmatch(job.path) or folder.is_symlink():
            logger.error("Rejected unsafe sample cleanup path: %s", job.path)
            pending += 1
            continue
        try:
            (folder / job.path).unlink(missing_ok=True)
        except OSError:
            logger.exception("Sample cleanup will be retried: %s", job.path)
            pending += 1
            continue
        db.delete(job)
        removed += 1
    db.commit()
    return {"deleted_files": removed, "pending_files": pending}


def recover_sample_cleanup(db: Session) -> dict:
    """Recover old interrupted imports and retry committed deletion jobs at startup."""
    referenced = set(db.scalars(select(FaceSample.path)))
    folder = DATA / "samples"
    if not folder.is_symlink():
        # Recent writes may belong to another starting worker; never sweep them.
        cutoff = time.time() - 3600
        abandoned = [
            path.name
            for path in folder.glob("*.png")
            if SAMPLE_NAME.fullmatch(path.name)
            and path.name not in referenced
            and path.lstat().st_mtime < cutoff
        ]
        queue_sample_deletion(db, abandoned)
        db.commit()
    return purge_pending_samples(db)
