import csv
import io
import json
import math
import time
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response as RawResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.algorithms.enhancement import enhance
from app.algorithms.face_detector import annotate, detect, engine, public_faces
from app.algorithms.face_recognizer import match
from app.algorithms.light_analysis import analyze
from app.core.config import DATA, MAX_ARCHIVE, ROOT, DEFAULT_THRESHOLD
from app.core.errors import AppError
from app.database.session import get_db
from app.models.entities import (
    Person,
    FaceSample,
    RecognitionRecord,
    DetectionTask,
    Dataset,
    Experiment,
    ExperimentResult,
    Calibration,
)
from app.schemas.contracts import (
    Response,
    EnhanceOptions,
    PersonEdit,
    PersonBatchDelete,
    ExperimentRequest,
    CalibrationRequest,
)
from app.services.images import read_upload, data_url, decode
from app.services.persons import register, get_person, person_view, gallery, delete_people
from app.services.datasets import import_dataset, dataset_view
from app.services.experiments import (
    create_experiment,
    run_experiment,
    experiment_view,
    save_calibration,
)

router = APIRouter(prefix="/api")


def options_from_json(raw: str) -> EnhanceOptions:
    try:
        return EnhanceOptions.model_validate_json(raw)
    except ValidationError as exc:
        raise AppError(f"增强参数无效：{exc}", 422) from exc


@router.get("/system/overview", response_model=Response)
def overview(db: Session = Depends(get_db)) -> dict:
    latest = db.scalar(select(Experiment).order_by(Experiment.id.desc()))
    return {
        "data": {
            "persons": db.scalar(select(func.count(Person.id))),
            "samples": db.scalar(select(func.count(FaceSample.id))),
            "detections": db.scalar(select(func.count(DetectionTask.id))),
            "recognitions": db.scalar(select(func.count(RecognitionRecord.id))),
            "datasets": db.scalar(select(func.count(Dataset.id))),
            "experiments": db.scalar(select(func.count(Experiment.id))),
            "model": engine.status(),
            "latest_experiment": experiment_view(latest) if latest else None,
        }
    }


@router.post("/system/model/load", response_model=Response)
def load_model() -> dict:
    engine.load()
    return {"data": engine.status()}


@router.post("/enhance/analyze", response_model=Response)
def analyze_image(file: UploadFile = File(...)) -> dict:
    _, image = read_upload(file)
    return {"data": analyze(image)}


@router.post("/enhance/process", response_model=Response)
def process(file: UploadFile = File(...), options: str = Form("{}")) -> dict:
    params = options_from_json(options)
    _, image = read_upload(file)
    start = time.perf_counter()
    processed, steps = enhance(image, params)
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "data": {
            "original": data_url(image),
            "enhanced": data_url(processed),
            "before": analyze(image),
            "after": analyze(processed),
            "steps": steps,
            "elapsed_ms": elapsed,
            "parameters": params.model_dump(),
        }
    }


@router.post("/face/detect", response_model=Response)
def face_detect(
    file: UploadFile = File(...), options: str = Form("{}"), db: Session = Depends(get_db)
) -> dict:
    params = options_from_json(options)
    _, image = read_upload(file)
    engine.load()
    original = detect(image)
    start = time.perf_counter()
    processed, steps = enhance(image, params)
    enhancement_ms = (time.perf_counter() - start) * 1000
    enhanced = detect(processed)
    enhanced["enhancement_ms"] = enhancement_ms
    enhanced["total_ms"] = enhanced["elapsed_ms"] + enhancement_ms
    db.add(
        DetectionTask(
            counts={
                "original": original["count"],
                "enhanced": enhanced["count"],
                "method": params.method,
            }
        )
    )
    db.commit()
    return {
        "data": {
            "original": original,
            "enhanced": enhanced,
            "steps": steps,
            "analysis": analyze(image),
        }
    }


@router.post("/person/register", response_model=Response)
def person_register(
    name: str = Form(...),
    note: str = Form(""),
    capture_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if not 1 <= len(files) <= 10:
        raise AppError("请上传 1–10 张照片")
    images = [read_upload(f)[1] for f in files]
    person = register(db, name, note, images, capture_id)
    return {"data": person_view(person, True)}


@router.get("/person", response_model=Response)
def person_list(q: str = Query("", max_length=80), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Person).where(Person.name.contains(q, autoescape=True)).order_by(Person.id.asc())
    )
    return {"data": [person_view(p) for p in rows]}


@router.get("/person/demo-dataset")
def person_demo_dataset() -> FileResponse:
    archive = ROOT / "datasets" / "att_faces_demo.zip"
    if not archive.is_file():
        raise AppError(
            "演示数据包尚未准备，请在项目目录运行 scripts/prepare_att_faces_demo.py", 404
        )
    return FileResponse(archive, media_type="application/zip", filename="att_faces_demo.zip")


@router.get("/person/simulated-dataset")
def person_simulated_dataset() -> FileResponse:
    archive = ROOT / "datasets" / "att_lighting_three_scenes.zip"
    if not archive.is_file():
        raise AppError("三类光照数据包尚未准备，请运行 scripts/prepare_three_scene_demo.py", 404)
    return FileResponse(
        archive, media_type="application/zip", filename="att_lighting_three_scenes.zip"
    )


@router.post("/person/batch-delete", response_model=Response)
def person_batch_delete(request: PersonBatchDelete, db: Session = Depends(get_db)) -> dict:
    return {"data": delete_people(db, request.person_ids)}


@router.get("/person/{person_id}", response_model=Response)
def person_detail(person_id: int, db: Session = Depends(get_db)) -> dict:
    return {"data": person_view(get_person(db, person_id), True)}


@router.patch("/person/{person_id}", response_model=Response)
def person_edit(person_id: int, request: PersonEdit, db: Session = Depends(get_db)) -> dict:
    person = get_person(db, person_id)
    if not request.name.strip():
        raise AppError("姓名不能为空")
    person.name, person.note = request.name.strip(), request.note.strip()
    db.commit()
    return {"data": person_view(person)}


@router.delete("/person/{person_id}", response_model=Response)
def person_delete(person_id: int, db: Session = Depends(get_db)) -> dict:
    get_person(db, person_id)
    result = delete_people(db, [person_id])
    return {"data": {"deleted": person_id, "cleanup": result["cleanup"]}}


@router.get("/person/{person_id}/samples/{sample_id}")
def sample_image(person_id: int, sample_id: int, db: Session = Depends(get_db)) -> FileResponse:
    get_person(db, person_id)
    sample = db.get(FaceSample, sample_id)
    if sample is None or sample.person_id != person_id:
        raise AppError("样本不存在", 404)
    return FileResponse(
        DATA / "samples" / sample.path,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


def recognize(
    file: UploadFile, options: str, threshold: float, db: Session, target: int | None
) -> dict:
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise AppError("相似度阈值须在 [-1,1] 内", 422)
    params = options_from_json(options)
    _, image = read_upload(file)
    templates = gallery(db, target)
    start = time.perf_counter()
    processed, steps = enhance(image, params)
    faces = engine.infer(processed)
    if len(faces) != 1:
        raise AppError(f"身份确认须恰有一张人脸，当前检测到 {len(faces)} 张", 422)
    result = match(faces[0]["embedding"], templates, threshold)
    elapsed = (time.perf_counter() - start) * 1000
    result.update(
        {
            "elapsed_ms": elapsed,
            "method": params.method,
            "mode": "verify" if target is not None else "identify",
            "model_fingerprint": engine.fingerprint,
            "target_person_id": target,
        }
    )
    db.add(RecognitionRecord(person_id=result["person_id"], mode=result["mode"], result=result))
    db.commit()
    return {
        "data": {
            **result,
            "original": data_url(image),
            "enhanced": data_url(annotate(processed, faces)),
            "faces": public_faces(processed, faces),
            "steps": steps,
            "analysis": analyze(image),
            "threshold_note": "手动阈值仅用于演示；正式报告请使用独立校准集",
        }
    }


@router.post("/recognition/verify", response_model=Response)
def verify(
    file: UploadFile = File(...),
    person_id: int = Form(...),
    options: str = Form("{}"),
    threshold: float = Form(DEFAULT_THRESHOLD),
    db: Session = Depends(get_db),
) -> dict:
    return recognize(file, options, threshold, db, person_id)


@router.post("/recognition/identify", response_model=Response)
def identify(
    file: UploadFile = File(...),
    options: str = Form("{}"),
    threshold: float = Form(DEFAULT_THRESHOLD),
    db: Session = Depends(get_db),
) -> dict:
    return recognize(file, options, threshold, db, None)


@router.get("/recognition/records", response_model=Response)
def records(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(RecognitionRecord).order_by(RecognitionRecord.id.desc()).limit(50))
    return {
        "data": [{"id": r.id, "created_at": r.created_at.isoformat(), **r.result} for r in rows]
    }


@router.post("/dataset/import", response_model=Response)
def dataset_import(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    record = import_dataset(db, file.file.read(MAX_ARCHIVE + 1))
    return {"data": dataset_view(record)}


@router.get("/dataset", response_model=Response)
def datasets(db: Session = Depends(get_db)) -> dict:
    return {
        "data": [dataset_view(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
    }


@router.get("/dataset/{dataset_id}", response_model=Response)
def dataset_detail(dataset_id: int, db: Session = Depends(get_db)) -> dict:
    record = db.get(Dataset, dataset_id)
    if record is None:
        raise AppError("数据集不存在", 404)
    return {"data": dataset_view(record, True)}


@router.delete("/dataset/{dataset_id}", response_model=Response)
def dataset_delete(dataset_id: int, db: Session = Depends(get_db)) -> dict:
    import shutil

    record = db.get(Dataset, dataset_id)
    if record is None:
        raise AppError("数据集不存在", 404)
    if db.scalar(select(Experiment.id).where(Experiment.dataset_id == dataset_id).limit(1)):
        raise AppError("请先删除引用此数据集的实验", 409)
    folder = DATA / "datasets" / record.directory
    db.delete(record)
    db.commit()
    shutil.rmtree(folder)
    return {"data": {"deleted": dataset_id}}


@router.post("/experiment/run", response_model=Response)
def experiment_run(
    request: ExperimentRequest, background: BackgroundTasks, db: Session = Depends(get_db)
) -> dict:
    record, templates = create_experiment(db, request)
    background.add_task(run_experiment, record.id, templates)
    return {"data": experiment_view(record)}


@router.get("/experiment", response_model=Response)
def experiments(db: Session = Depends(get_db)) -> dict:
    return {
        "data": [
            experiment_view(e)
            for e in db.scalars(select(Experiment).order_by(Experiment.id.desc()).limit(100))
        ]
    }


@router.get("/experiment/{experiment_id}", response_model=Response)
def experiment_detail(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    record = db.get(Experiment, experiment_id)
    if record is None:
        raise AppError("实验不存在", 404)
    return {"data": experiment_view(record)}


@router.get("/experiment/{experiment_id}/results", response_model=Response)
def experiment_results(
    experiment_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    experiment_detail(experiment_id, db)
    rows = db.scalars(
        select(ExperimentResult)
        .where(ExperimentResult.experiment_id == experiment_id)
        .order_by(ExperimentResult.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "data": [
            {
                "id": r.id,
                "method": r.method,
                "scene": r.scene,
                "item_index": r.item_index,
                **r.detail,
            }
            for r in rows
        ]
    }


@router.get("/experiment/{experiment_id}/preview/{result_id}", response_model=Response)
def experiment_preview(experiment_id: int, result_id: int, db: Session = Depends(get_db)) -> dict:
    experiment = db.get(Experiment, experiment_id)
    row = db.get(ExperimentResult, result_id)
    if experiment is None or row is None or row.experiment_id != experiment_id:
        raise AppError("结果不存在", 404)
    dataset = db.get(Dataset, experiment.dataset_id)
    item = dataset.manifest["items"][row.item_index]
    image = decode((DATA / "datasets" / dataset.directory / item["stored_file"]).read_bytes())
    processed, _ = enhance(image, EnhanceOptions(**experiment.config["parameters"][row.method]))
    return {
        "data": {
            "original": data_url(image),
            "enhanced": data_url(annotate(processed, row.detail["predictions"])),
            "truth": item["faces"],
        }
    }


@router.get("/experiment/{experiment_id}/csv")
def experiment_csv(experiment_id: int, db: Session = Depends(get_db)) -> RawResponse:
    experiment_detail(experiment_id, db)
    rows = db.scalars(
        select(ExperimentResult)
        .where(ExperimentResult.experiment_id == experiment_id)
        .order_by(ExperimentResult.id)
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    fields = [
        "tp",
        "fp",
        "fn",
        "known",
        "unknown",
        "correct",
        "false_accept",
        "detected_known",
        "detected_unknown",
        "elapsed_ms",
    ]
    writer.writerow(["method", "scene", "item_index", *fields])
    for row in rows:
        writer.writerow([row.method, row.scene, row.item_index, *[row.detail[k] for k in fields]])
    return RawResponse(
        "\ufeff" + buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="experiment-{experiment_id}.csv"'},
    )


@router.delete("/experiment/{experiment_id}", response_model=Response)
def experiment_delete(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    record = db.get(Experiment, experiment_id)
    if record is None:
        raise AppError("实验不存在", 404)
    if record.status in ("queued", "running"):
        raise AppError("运行中的实验不能删除", 409)
    for calibration in db.scalars(
        select(Calibration).where(Calibration.experiment_id == record.id)
    ):
        if any(
            e.config.get("calibration_id") == calibration.id for e in db.scalars(select(Experiment))
        ):
            raise AppError("此校准被测试实验引用，须先删除测试实验", 409)
        db.delete(calibration)
    db.delete(record)
    db.commit()
    return {"data": {"deleted": experiment_id}}


@router.post("/calibration", response_model=Response)
def calibration_create(request: CalibrationRequest, db: Session = Depends(get_db)) -> dict:
    result = save_calibration(db, request.experiment_id, request.target_far)
    return {"data": {"id": result.id, "thresholds": result.thresholds, "detail": result.detail}}


@router.get("/calibration", response_model=Response)
def calibration_list(db: Session = Depends(get_db)) -> dict:
    return {
        "data": [
            {
                "id": c.id,
                "experiment_id": c.experiment_id,
                "thresholds": c.thresholds,
                "detail": c.detail,
            }
            for c in db.scalars(select(Calibration).order_by(Calibration.id.desc()))
        ]
    }


@router.get("/research/benchmarks", response_model=Response)
def research_reports() -> dict:
    from app.services.research import reports

    return {"data": reports()}


@router.get("/research/benchmarks/{dataset}/csv")
def research_csv(dataset: str) -> FileResponse:
    from app.services.research import benchmark_file

    return FileResponse(
        benchmark_file(dataset, "results.csv"),
        media_type="text/csv",
        filename=f"{dataset}-real-results.csv",
    )


@router.get("/research/benchmarks/{dataset}/protocol", response_model=Response)
def research_protocol(dataset: str) -> dict:
    from app.services.research import benchmark_file

    return {"data": json.loads(benchmark_file(dataset, "protocol-frozen.json").read_text())}
