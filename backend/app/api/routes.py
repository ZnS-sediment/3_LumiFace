import json
import math
import time
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Query, UploadFile, Request
from fastapi.responses import FileResponse, Response as RawResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.algorithms.enhancement import enhance, resolve_options
from app.algorithms.face_detector import annotate, detect, engine, public_faces
from app.algorithms.face_recognizer import match, summarize_matches
from app.algorithms.recognition import recognition_faces, RECOGNITION_POLICY
from app.algorithms.light_analysis import analyze
from app.core.config import DATA, MAX_ARCHIVE, ROOT, DEFAULT_THRESHOLD, DEFAULT_THRESHOLD_POLICY, MAX_DATASET_IMAGES
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
    ExperimentRename,
    CalibrationRequest,
    ImageTestRequest,
)
from app.services import directory_picker
from app.services.images import read_upload, data_url, decode
from app.services.persons import register, get_person, person_view, gallery, delete_people
from app.services.datasets import import_dataset, dataset_view
from app.services.experiments import (
    create_experiment,
    run_experiment,
    experiment_view,
    error_summary,
    save_calibration,
)

router = APIRouter(prefix="/api")


def options_from_json(raw: str) -> EnhanceOptions:
    try:
        return EnhanceOptions.model_validate_json(raw)
    except ValidationError as exc:
        raise AppError(f"增强参数无效：{exc}", 422) from exc


@router.get("/system/directory-picker", response_model=Response)
def directory_picker_status() -> dict:
    return {"data": {"available": directory_picker.available()}}


@router.post("/system/directory-picker", response_model=Response)
def select_identity_directory(x_lumiface_picker: str = Header("")) -> dict:
    if x_lumiface_picker != "1":
        raise AppError("请从批量导入身份窗口选择目录", 403)
    return {"data": directory_picker.choose()}


@router.get("/system/directory-picker/{token}/photos/{index}")
def selected_photo(token: str, index: int, preview: bool = False) -> RawResponse:
    raw, media_type = directory_picker.read_photo(token, index)
    if preview:
        import cv2

        image = decode(raw)
        h, w = image.shape[:2]
        scale = min(1, 96 / max(h, w))
        image = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))))
        _, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        raw, media_type = encoded.tobytes(), "image/jpeg"
    return RawResponse(raw, media_type=media_type, headers={"Cache-Control": "private, no-store"})


@router.delete("/system/directory-picker/{token}", response_model=Response)
def release_identity_directory(token: str) -> dict:
    directory_picker.release(token)
    return {"data": True}


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


@router.get("/system/model", response_model=Response)
def model_status() -> dict:
    return {"data": engine.status()}


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
    resolved = resolve_options(image, params)
    processed, steps = enhance(image, resolved)
    if params.auto_parameters:
        steps = ["自动参数 " + step for step in steps]
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "data": {
            "original": data_url(image),
            "enhanced": data_url(processed),
            "before": analyze(image),
            "after": analyze(processed),
            "steps": steps,
            "elapsed_ms": elapsed,
            "parameters": resolved.model_dump(),
            "parameter_mode": "auto" if params.auto_parameters else "fixed",
        }
    }


@router.post("/face/detect", response_model=Response)
def face_detect(
    file: UploadFile = File(...), options: str = Form("{}"), db: Session = Depends(get_db)
) -> dict:
    params = options_from_json(options)
    _, image = read_upload(file)
    engine.load()
    start = time.perf_counter()
    processed, steps = enhance(image, params)
    enhancement_ms = (time.perf_counter() - start) * 1000
    result = detect(processed)
    result["enhancement_ms"] = enhancement_ms
    result["total_ms"] = result["elapsed_ms"] + enhancement_ms
    db.add(
        DetectionTask(
            counts={
                "count": result["count"],
                "method": params.method,
            }
        )
    )
    db.commit()
    return {
        "data": {
            **result,
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
    rows = db.execute(
        select(
            Person.id,
            Person.name,
            Person.note,
            Person.created_at,
            func.count(FaceSample.id).label("sample_count"),
        )
        .outerjoin(FaceSample, FaceSample.person_id == Person.id)
        .where(Person.name.contains(q, autoescape=True))
        .group_by(Person.id)
        .order_by(Person.id.asc())
    ).mappings()
    return {"data": [{**row, "created_at": row["created_at"].isoformat()} for row in rows]}


@router.get("/person/lfw-dataset")
def person_lfw_dataset() -> FileResponse:
    archive = ROOT / "datasets" / "lfw_120_lighting.zip"
    if not archive.is_file():
        raise AppError("原 120 人数据尚未准备，请运行 scripts/prepare_lfw_lighting.py", 404)
    return FileResponse(archive, media_type="application/zip", filename=archive.name)


@router.get("/person/lfw-new-dataset")
def person_lfw_new_dataset() -> FileResponse:
    archive = ROOT / "datasets" / "lfw_280_new_lighting.zip"
    if not archive.is_file():
        raise AppError("新增人员数据尚未准备，请运行 scripts/prepare_lfw_disjoint.py", 404)
    return FileResponse(archive, media_type="application/zip", filename=archive.name)


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
    policy = (
        RECOGNITION_POLICY
        if params.auto_parameters and params.method != "original" else "processed-v1"
    )
    faces = recognition_faces(image, processed, policy, enhancement_method=params.method)
    if policy == RECOGNITION_POLICY:
        steps.append("对齐后按人脸处理光照并融合镜像特征" if params.method == "clahe" else "同位置对齐，融合原图与增强特征")
    if not faces:
        raise AppError("未检测到人脸，请更换图片", 422)
    matches = [match(face["embedding"], templates, threshold) for face in faces]
    result = summarize_matches(matches, threshold)
    elapsed = (time.perf_counter() - start) * 1000
    result.update(
        {
            "elapsed_ms": elapsed,
            "method": params.method,
            "mode": "verify" if target is not None else "identify",
            "model_fingerprint": engine.fingerprint,
            "target_person_id": target,
            "face_matches": matches,
            "recognition_policy": policy,
        }
    )
    db.add(RecognitionRecord(person_id=result["person_id"], mode=result["mode"], result=result))
    db.commit()
    return {
        "data": {
            **result,
            "original": data_url(image),
            "enhanced": data_url(annotate(processed, faces)),
            "faces": [
                {**face, "match": decision}
                for face, decision in zip(public_faces(processed, faces), matches)
            ],
            "steps": steps,
            "analysis": analyze(image),
            "threshold_policy": DEFAULT_THRESHOLD_POLICY if threshold == DEFAULT_THRESHOLD else "explicit",
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


@router.post("/experiment/images", response_model=Response)
async def experiment_images(
    http_request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    from app.services.image_tests import create_image_test

    # Starlette defaults to 1000 files, below the 1200 queries in one 400-person scene.
    # Spool multipart files, bound their count and bytes, and close all handles on errors too.
    async with http_request.form(max_files=MAX_DATASET_IMAGES, max_fields=1) as form:
        files = form.getlist("files")
        labels = form.get("labels")
        if not isinstance(labels, str) or not files or any(not isinstance(f, StarletteUploadFile) for f in files):
            raise AppError("请提交测试图片及对应的身份标签", 422)
        try:
            request = ImageTestRequest.model_validate_json(labels)
        except ValidationError as exc:
            raise AppError(f"图片标签或测试参数无效：{exc}", 422) from exc
        record, templates = await run_in_threadpool(create_image_test, db, files, request)
        result = experiment_view(record)
    background.add_task(run_experiment, record.id, templates)
    return {"data": result}


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
    return {"data": {**experiment_view(record), "error_summary": error_summary(db, record)}}


@router.patch("/experiment/{experiment_id}", response_model=Response)
def experiment_rename(
    experiment_id: int, request: ExperimentRename, db: Session = Depends(get_db)
) -> dict:
    record = db.get(Experiment, experiment_id)
    if record is None:
        raise AppError("实验不存在", 404)
    if record.status in ("queued", "running"):
        raise AppError("请等待测试结束后再重命名", 409)
    record.config = {**record.config, "display_name": request.name}
    db.commit()
    return experiment_detail(experiment_id, db)


@router.get("/experiment/{experiment_id}/results", response_model=Response)
def experiment_results(
    experiment_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Experiment, experiment_id) is None:
        raise AppError("实验不存在", 404)
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
    processed, _ = enhance(
        image,
        EnhanceOptions(**row.detail.get("parameters", experiment.config["parameters"][row.method])),
    )
    return {
        "data": {
            "original": data_url(image),
            "enhanced": data_url(annotate(processed, row.detail["predictions"])),
            "truth": item["faces"],
        }
    }


@router.delete("/experiment/{experiment_id}", response_model=Response)
def experiment_delete(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    import shutil

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
    dataset = (
        db.get(Dataset, record.dataset_id) if record.config.get("kind") == "image_batch" else None
    )
    db.delete(record)
    db.flush()
    if dataset and not db.scalar(
        select(Experiment.id).where(Experiment.dataset_id == dataset.id).limit(1)
    ):
        db.delete(dataset)
    else:
        dataset = None
    db.commit()
    if dataset:
        shutil.rmtree(DATA / "datasets" / dataset.directory, ignore_errors=True)
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
