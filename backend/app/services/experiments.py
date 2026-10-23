import hashlib
import importlib.metadata
import json
import platform
import os
from pathlib import Path
import threading
import time
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.algorithms.enhancement import enhance
from app.algorithms.face_detector import engine
from app.algorithms.face_recognizer import match
from app.algorithms.metrics import aggregate, score_image, calibrate
from app.algorithms.evidence import assess_target
from app.core.config import DATA, ALGORITHM_VERSION
from app.core.errors import AppError
from app.database.session import SessionLocal
from app.models.entities import Dataset, Experiment, ExperimentResult, Calibration, Person
from app.schemas.contracts import EnhanceOptions, ExperimentRequest
from app.services.images import decode
from app.services.persons import gallery

RUN_LOCK = threading.Lock()
SCENES = ["normal", "low_light", "backlight", "infrared", "overexposed", "uneven"]


def gallery_digest(templates: list[dict]) -> str:
    return hashlib.sha256(json.dumps(templates, sort_keys=True).encode()).hexdigest()


def environment() -> dict:
    packages = {}
    for package in [
        "numpy",
        "opencv-python-headless",
        "insightface",
        "onnxruntime",
        "onnxruntime-gpu",
        "torch",
        "fastapi",
    ]:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            cpu,
        )
    return {
        "cpu_model": cpu,
        "cpu_logical_cores": os.cpu_count(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "packages": packages,
        "model": engine.status(),
        "algorithm_version": ALGORITHM_VERSION,
    }


def create_experiment(db: Session, request: ExperimentRequest) -> tuple[Experiment, list[dict]]:
    dataset = db.get(Dataset, request.dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", 404)
    templates = gallery(db)
    if not templates:
        raise AppError("请先注册参考身份", 409)
    known = {p["id"] for p in templates}
    if any(
        f["person_id"] is not None and f["person_id"] not in known
        for x in dataset.manifest["items"]
        for f in x["faces"]
    ):
        raise AppError("数据集引用的注册身份已删除，请重新映射标签", 409)
    # Legacy SQLite tables may reuse a deleted numeric ID. Bind annotations to the
    # original registration timestamp so they cannot silently refer to another person.
    references = dataset.manifest.get("person_references", {})
    for person_id in {
        f["person_id"]
        for x in dataset.manifest["items"]
        for f in x["faces"]
        if f["person_id"] is not None
    }:
        person = db.get(Person, person_id)
        signature = person.created_at.replace(tzinfo=None).isoformat()
        if references.get(str(person_id)) != signature:
            raise AppError("数据集身份引用已失效或缺少注册绑定，请核实标签后重新导入数据集", 409)
    fingerprint = gallery_digest(templates)
    methods = list(dict.fromkeys(request.methods))
    thresholds = {method: request.threshold for method in methods}
    calibration_real = False
    calibration_note = "未经校准的手动固定阈值，仅探索性评估"
    if request.calibration_id is not None:
        if dataset.split != "test":
            raise AppError("校准结果仅能应用于测试集")
        calibration = db.get(Calibration, request.calibration_id)
        if calibration is None:
            raise AppError("校准记录不存在", 404)
        previous = db.get(Experiment, calibration.experiment_id)
        if (
            previous.config["gallery_digest"] != fingerprint
            or previous.config["environment"]["model"]["fingerprint"] != engine.fingerprint
            or previous.config["environment"]["algorithm_version"] != ALGORITHM_VERSION
            or previous.config.get("detector_size", [640, 640])
            != [engine.detection_size, engine.detection_size]
        ):
            raise AppError("校准后模型、算法或身份库已改变，须重新校准", 409)
        if any(method not in calibration.thresholds for method in methods):
            raise AppError("校准记录未覆盖所选增强方法")
        thresholds = {method: calibration.thresholds[method] for method in methods}
        calibration_real = previous.config["dataset"]["real_capture"]
        calibration_note = "使用独立校准集冻结的分方法阈值"
    config = {
        "kind": dataset.manifest.get("kind", "annotated_dataset"),
        "dataset": {k: v for k, v in dataset.manifest.items() if k != "items"},
        "dataset_digest": hashlib.sha256(
            json.dumps(dataset.manifest, sort_keys=True).encode()
        ).hexdigest(),
        "split": dataset.split,
        "methods": methods,
        "thresholds": thresholds,
        "calibration_id": request.calibration_id,
        "calibration_note": calibration_note,
        "calibration_real_capture": calibration_real,
        "gallery_digest": fingerprint,
        "gallery_ids": sorted(known),
        "environment": environment(),
        "parameters": {m: EnhanceOptions(method=m).model_dump() for m in methods},
        "protocol": dataset.manifest.get("protocol", {}),
        "localization_protocol": dataset.manifest.get("localization_protocol", "iou"),
        "iou_threshold": 0.5,
        "detector_threshold": 0.5,
        "detector_size": [engine.detection_size, engine.detection_size],
    }
    record = Experiment(
        dataset_id=dataset.id, total=len(dataset.manifest["items"]) * len(methods), config=config
    )
    db.add(record)
    db.commit()
    return record, templates


def run_experiment(experiment_id: int, templates: list[dict]) -> None:
    with RUN_LOCK, SessionLocal() as db:
        record = db.get(Experiment, experiment_id)
        try:
            record.status = "running"
            db.commit()
            dataset = db.get(Dataset, record.dataset_id)
            # Load/warm up outside measured intervals; no label-dependent method selection.
            engine.load()
            first = decode(
                (
                    DATA
                    / "datasets"
                    / dataset.directory
                    / dataset.manifest["items"][0]["stored_file"]
                ).read_bytes()
            )
            engine.infer(first)
            grouped = {m: [] for m in record.config["methods"]}
            names = {p["id"]: p["name"] for p in templates}
            for index, item in enumerate(dataset.manifest["items"]):
                image = decode(
                    (DATA / "datasets" / dataset.directory / item["stored_file"]).read_bytes()
                )
                for method in record.config["methods"]:
                    start = time.perf_counter()
                    processed, steps = enhance(
                        image, EnhanceOptions(**record.config["parameters"][method])
                    )
                    faces = engine.infer(processed)
                    predictions = [
                        {k: v for k, v in f.items() if k != "embedding"}
                        | {
                            "match": match(
                                f["embedding"], templates, record.config["thresholds"][method]
                            )
                        }
                        for f in faces
                    ]
                    elapsed = (time.perf_counter() - start) * 1000
                    detail = score_image(
                        item["faces"],
                        predictions,
                        elapsed,
                        protocol=record.config.get("localization_protocol", "iou"),
                    )
                    detail["capture_id"] = item["capture_id"]
                    detail["steps"] = steps
                    if record.config.get("kind") == "image_batch":
                        truth_id = item["faces"][0]["person_id"]
                        prediction = predictions[0]["match"] if len(predictions) == 1 else None
                        if not predictions:
                            outcome = "no_face"
                        elif len(predictions) > 1:
                            outcome = "multiple_faces"
                        elif truth_id is None:
                            outcome = (
                                "false_accept" if prediction["confirmed"] else "unknown_rejected"
                            )
                        elif detail["correct"]:
                            outcome = "correct"
                        else:
                            outcome = "wrong_identity" if prediction["confirmed"] else "rejected"
                        detail.update(
                            {
                                "filename": item["display_file"],
                                "expected_name": names.get(truth_id, "未知身份"),
                                "predicted_name": prediction["name"]
                                if prediction
                                else "未执行匹配",
                                "similarity": prediction["similarity"] if prediction else None,
                                "outcome": outcome,
                            }
                        )
                    grouped[method].append((item["scene"], detail))
                    db.add(
                        ExperimentResult(
                            experiment_id=record.id,
                            method=method,
                            scene=item["scene"],
                            item_index=index,
                            detail=detail,
                        )
                    )
                    record.progress += 1
                    db.commit()
            summary = {}
            for method, rows in grouped.items():
                scenes = {scene: aggregate([r for s, r in rows if s == scene]) for scene in SCENES}
                summary[method] = {"overall": aggregate([r for _, r in rows]), "scenes": scenes}
                if record.config.get("kind") == "image_batch":
                    summary[method]["overall"]["no_face"] = sum(
                        r.get("outcome") == "no_face" for _, r in rows
                    )
                    summary[method]["overall"]["multiple_faces"] = sum(
                        r.get("outcome") == "multiple_faces" for _, r in rows
                    )
                actual = dataset.manifest["real_capture"] and record.config["split"] == "test"
                calibrated = record.config["calibration_id"] is not None and record.config.get(
                    "calibration_real_capture", False
                )
                targets = {}
                for label, stats, coverage in [
                    ("infrared", scenes["infrared"], scenes["infrared"]["known"] > 0),
                    ("backlight", scenes["backlight"], scenes["backlight"]["known"] > 0),
                    (
                        "overall",
                        summary[method]["overall"],
                        all(scenes[s]["known"] > 0 for s in ["normal", "low_light", "backlight"]),
                    ),
                ]:
                    targets[label] = assess_target(
                        label,
                        stats,
                        real_capture=actual,
                        independent_calibration=calibrated,
                        protocol=record.config.get("protocol", {}),
                        coverage=coverage,
                    )
                summary[method]["targets"] = targets
            record.summary = summary
            record.status = "completed"
            record.config = {**record.config, "finished_at": datetime.now(timezone.utc).isoformat()}
            db.commit()
        except Exception as exc:
            db.rollback()
            record = db.get(Experiment, experiment_id)
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
            db.commit()


def save_calibration(db: Session, experiment_id: int, target_far: float) -> Calibration:
    record = db.get(Experiment, experiment_id)
    if record is None or record.status != "completed" or record.config["split"] != "calibration":
        raise AppError("必须选择已完成的 calibration 实验")
    details = {}
    for method in record.config["methods"]:
        rows = db.scalars(
            select(ExperimentResult).where(
                ExperimentResult.experiment_id == record.id, ExperimentResult.method == method
            )
        ).all()
        try:
            details[method] = calibrate(
                [d for row in rows for d in row.detail["decisions"]], target_far
            )
        except ValueError as exc:
            raise AppError(str(exc), 422) from exc
    result = Calibration(
        experiment_id=record.id,
        thresholds={m: d["threshold"] for m, d in details.items()},
        detail=details,
    )
    db.add(result)
    db.commit()
    return result


def experiment_view(record: Experiment) -> dict:
    return {
        "id": record.id,
        "dataset_id": record.dataset_id,
        "status": record.status,
        "progress": record.progress,
        "total": record.total,
        "config": record.config,
        "summary": record.summary,
        "error": record.error,
        "created_at": record.created_at.isoformat(),
    }
