import hashlib
from contextlib import contextmanager
import importlib.metadata
import json
import platform
import os
from pathlib import Path
import threading
import time
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.algorithms.enhancement import enhance, resolve_options
from app.algorithms.recognition import recognition_faces, RECOGNITION_POLICY, PREVIOUS_RECOGNITION_POLICY, LEGACY_FUSION_POLICY, ENHANCED_WEIGHT, LOCAL_POLICIES, METHOD_ENHANCED_WEIGHTS
from app.algorithms.face_detector import engine
from app.algorithms.face_recognizer import match
from app.algorithms.metrics import aggregate, score_image, calibrate
from app.algorithms.evidence import assess_target
from app.core.config import DEFAULT_THRESHOLD_POLICY, DATA, ALGORITHM_VERSION
from app.core.errors import AppError
from app.database.session import SessionLocal
from app.models.entities import Dataset, Experiment, ExperimentResult, Calibration, Person
from app.schemas.contracts import EnhanceOptions, ExperimentRequest
from app.services.images import decode
from app.services.persons import gallery

RUN_LOCK = threading.Lock()
CREATION_LOCK = threading.RLock()
SCENES = ["normal", "low_light", "backlight", "infrared", "overexposed", "uneven"]


@contextmanager
def experiment_creation(db: Session):
    # Cover validation/storage through the queued-record commit. Image uploads
    # reenter this guard when they call create_experiment in the same worker.
    if not CREATION_LOCK.acquire(blocking=False):
        raise AppError("已有测试正在创建，请等待当前操作完成", 409)
    try:
        active = db.scalar(
            select(Experiment.id).where(Experiment.status.in_(["queued", "running"])).limit(1)
        )
        if active is not None:
            raise AppError("已有测试正在排队或运行，请等待当前测试结束后再创建", 409)
        yield
    finally:
        CREATION_LOCK.release()


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
    with experiment_creation(db):
        return _create_experiment(db, request)


def _create_experiment(db: Session, request: ExperimentRequest) -> tuple[Experiment, list[dict]]:
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
    default_threshold = "threshold" not in request.model_fields_set
    threshold_policy = DEFAULT_THRESHOLD_POLICY if default_threshold else "explicit"
    calibration_note = (
        "预置公开模拟数据开发集校准值；不是当前图库或真实场景验收校准"
        if default_threshold and DEFAULT_THRESHOLD_POLICY != "legacy-uncalibrated"
        else "未经校准的手动固定阈值，仅探索性评估"
    )
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
        if any(
            previous.config["parameters"].get(method, {}).get("auto_parameters", False)
            != request.auto_parameters
            for method in methods
            if method != "original"
        ):
            raise AppError("校准与测试的自动参数模式不同，须重新校准", 409)
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
        "threshold_policy": "calibration" if request.calibration_id is not None else threshold_policy,
        "calibration_id": request.calibration_id,
        "calibration_note": calibration_note,
        "calibration_real_capture": calibration_real,
        "gallery_digest": fingerprint,
        "gallery_ids": sorted(known),
        "environment": environment(),
        "parameters": {
            m: EnhanceOptions(method=m, auto_parameters=request.auto_parameters).model_dump()
            for m in methods
        },
        "parameter_policy": "image-statistics-v1" if request.auto_parameters else "fixed",
        "recognition_policy": RECOGNITION_POLICY if request.auto_parameters else "processed-v1",
        "enhanced_feature_weight": None,
        "recognition_parameters": {
            m: ({"mode": "face_local_mirror", **LOCAL_POLICIES[m]}
                if m in LOCAL_POLICIES else {"mode": "aligned_fusion", "enhanced_weight": METHOD_ENHANCED_WEIGHTS.get(m, ENHANCED_WEIGHT)}
                if m != "original" else {"mode": "original"})
            for m in methods
        } if request.auto_parameters else {},
        "protocol": dataset.manifest.get("protocol", {}),
        "localization_protocol": dataset.manifest.get("localization_protocol", "iou"),
        "iou_threshold": 0.5,
        "detector_threshold": 0.5,
        "detector_size": [engine.detection_size, engine.detection_size],
    }
    if request.name:
        config["display_name"] = request.name
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
                policy = record.config.get("recognition_policy", "processed-v1")
                shared_faces, shared_ms = None, 0.0
                if policy in (RECOGNITION_POLICY, PREVIOUS_RECOGNITION_POLICY):
                    shared_start = time.perf_counter()
                    shared_faces = engine.infer(image)
                    shared_ms = (time.perf_counter() - shared_start) * 1000
                for method in record.config["methods"]:
                    start = time.perf_counter()
                    requested = EnhanceOptions(**record.config["parameters"][method])
                    resolved = resolve_options(image, requested)
                    processed, steps = enhance(image, resolved)
                    if requested.auto_parameters and method != "original":
                        steps = ["自动参数 " + step for step in steps]
                    faces = shared_faces if method == "original" and shared_faces is not None else recognition_faces(
                        image,
                        processed,
                        policy if method != "original" else "processed-v1",
                        record.config.get("enhanced_feature_weight") if record.config.get("enhanced_feature_weight") is not None else ENHANCED_WEIGHT,
                        original_faces=shared_faces,
                        enhancement_method=method,
                    )
                    if policy in (RECOGNITION_POLICY, PREVIOUS_RECOGNITION_POLICY, LEGACY_FUSION_POLICY) and method != "original":
                        steps.append("对齐后按人脸处理光照并融合镜像特征" if policy == RECOGNITION_POLICY and method in LOCAL_POLICIES else "同位置对齐，融合原图与增强特征")
                    predictions = [
                        {k: v for k, v in f.items() if k != "embedding"}
                        | {
                            "match": match(
                                f["embedding"], templates, record.config["thresholds"][method]
                            )
                        }
                        for f in faces
                    ]
                    method_ms = (time.perf_counter() - start) * 1000
                    # Charge the original inference to EVERY method, including
                    # cache hits: these are standalone costs, not free baselines.
                    elapsed = method_ms + shared_ms
                    detail = score_image(
                        item["faces"],
                        predictions,
                        elapsed,
                        protocol=record.config.get("localization_protocol", "iou"),
                    )
                    detail["timing"] = {
                        "original_inference_ms": shared_ms,
                        "method_ms": method_ms,
                        "accounting": "standalone_with_shared_original" if shared_faces is not None else "standalone",
                    }
                    detail["capture_id"] = item["capture_id"]
                    detail["steps"] = steps
                    detail["parameters"] = resolved.model_dump()
                    if record.config.get("kind") == "image_batch":
                        truth_id = item["faces"][0]["person_id"]
                        prediction = predictions[0]["match"] if len(predictions) == 1 else None
                        multi_policy = (
                            record.config.get("localization_protocol") == "image_identity_presence"
                        )
                        accepted = [p["match"] for p in predictions if p["match"]["confirmed"]]
                        if not predictions:
                            outcome = "no_face"
                        elif len(predictions) > 1 and not multi_policy:
                            outcome = "multiple_faces"
                        elif truth_id is None:
                            outcome = (
                                "false_accept" if accepted else "unknown_rejected"
                            )
                        elif detail["correct"]:
                            outcome = "correct"
                        else:
                            outcome = "wrong_identity" if accepted else "rejected"
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
                        if multi_policy:
                            detail["face_count"] = len(predictions)
                            detail["recognized_identities"] = list({
                                m["person_id"]: {"person_id": m["person_id"], "name": m["name"]}
                                for m in accepted
                            }.values())
                            detail["predicted_name"] = "、".join(
                                identity["name"] for identity in detail["recognized_identities"]
                            ) or ("未知身份" if predictions else "未检测到人脸")
                            detail["similarity"] = detail["decisions"][0]["score"]
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
                        len(r["predictions"]) > 1 for _, r in rows
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
    if record.config.get("localization_protocol") == "image_identity_presence":
        raise AppError("多脸图片的存在性评估不可用于单脸阈值校准，请使用逐脸标注校准集", 422)
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


def error_summary(db: Session, record: Experiment) -> dict | None:
    """Count saved outcomes across the entire batch, including historical runs."""
    if record.config.get("kind") != "image_batch":
        return None
    error_types = ("no_face", "multiple_faces", "rejected", "wrong_identity", "false_accept")

    def empty() -> dict:
        return {
            "images": 0,
            "total_errors": 0,
            "unclassified": 0,
            "counts": dict.fromkeys(error_types, 0),
        }

    summary = {
        method: {"overall": empty(), "scenes": {scene: empty() for scene in SCENES}}
        for method in record.config["methods"]
    }
    outcome = ExperimentResult.detail["outcome"].as_string()
    rows = db.execute(
        select(ExperimentResult.method, ExperimentResult.scene, outcome, func.count())
        .where(ExperimentResult.experiment_id == record.id)
        .group_by(ExperimentResult.method, ExperimentResult.scene, outcome)
    )
    for method, scene, kind, count in rows:
        if method not in summary:
            continue
        scopes = [summary[method]["overall"]]
        if scene in summary[method]["scenes"]:
            scopes.append(summary[method]["scenes"][scene])
        for stats in scopes:
            stats["images"] += count
            if kind in error_types:
                stats["counts"][kind] += count
                stats["total_errors"] += count
            elif kind not in ("correct", "unknown_rejected"):
                stats["unclassified"] += count
    return summary


def experiment_view(record: Experiment) -> dict:
    return {
        "id": record.id,
        "dataset_id": record.dataset_id,
        "name": record.config.get("display_name") or record.config["dataset"]["name"],
        "status": record.status,
        "progress": record.progress,
        "total": record.total,
        "config": record.config,
        "summary": record.summary,
        "error": record.error,
        "created_at": record.created_at.isoformat(),
    }
