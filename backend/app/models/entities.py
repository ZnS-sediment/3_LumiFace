from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = {"sqlite_autoincrement": True}
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    samples: Mapped[list["FaceSample"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class FaceSample(Base):
    __tablename__ = "face_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(100))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    capture_id: Mapped[str] = mapped_column(String(120))
    embedding: Mapped[list] = mapped_column(JSON)
    quality: Mapped[dict] = mapped_column(JSON)
    model_fingerprint: Mapped[str] = mapped_column(String(64))
    encodings: Mapped[list["FaceEncoding"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class FaceEncoding(Base):
    """Derived features for another supported backbone; original samples stay intact."""

    __tablename__ = "face_encodings"
    sample_id: Mapped[int] = mapped_column(
        ForeignKey("face_samples.id", ondelete="CASCADE"), primary_key=True
    )
    model_fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    embedding: Mapped[list] = mapped_column(JSON)


class RecognitionRecord(Base):
    __tablename__ = "recognition_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PendingSampleDeletion(Base):
    """Persist file cleanup in the same transaction as identity deletion."""

    __tablename__ = "pending_sample_deletions"
    path: Mapped[str] = mapped_column(String(100), primary_key=True)


class DetectionTask(Base):
    __tablename__ = "detection_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    counts: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    split: Mapped[str] = mapped_column(String(20))
    directory: Mapped[str] = mapped_column(String(100))
    manifest: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    config: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    results: Mapped[list["ExperimentResult"]] = relationship(cascade="all, delete-orphan")


class ExperimentResult(Base):
    __tablename__ = "experiment_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    method: Mapped[str] = mapped_column(String(20))
    scene: Mapped[str] = mapped_column(String(20))
    item_index: Mapped[int]
    detail: Mapped[dict] = mapped_column(JSON)


class Calibration(Base):
    __tablename__ = "calibrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    thresholds: Mapped[dict] = mapped_column(JSON)
    detail: Mapped[dict] = mapped_column(JSON)
