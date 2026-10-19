import logging
import os
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.api.routes import router
from app.core.errors import AppError
from app.core.config import DATA
from app.database.session import Base, engine, SessionLocal
from app.models.entities import Experiment
from app.services.storage import recover_sample_cleanup


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    (DATA / "lumiface.db").chmod(0o600)
    with SessionLocal() as db:
        for experiment in db.scalars(
            select(Experiment).where(Experiment.status.in_(["queued", "running"]))
        ):
            experiment.status = "failed"
            experiment.error = "进程重启导致实验中断，请重新运行；未完成结果不会标为达标"
        db.commit()
        recover_sample_cleanup(db)
    yield


app = FastAPI(title="LumiFace 复杂光照人脸增强系统", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
)
ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
custom_origin = os.environ.get("LUMIFACE_UI_ORIGIN")
FRONTEND_ORIGIN = "http://localhost:5173"
if (
    custom_origin
    and urlparse(custom_origin).scheme == "http"
    and urlparse(custom_origin).hostname in ("127.0.0.1", "localhost")
):
    ORIGINS.append(custom_origin)
    FRONTEND_ORIGIN = custom_origin.rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/", include_in_schema=False)
def frontend_entry() -> RedirectResponse:
    return RedirectResponse(FRONTEND_ORIGIN + "/", status_code=307)


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        count = 0
        limit = 125 * 1024 * 1024

        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > limit:
                raise AppError("请求体超过 125 MB 限制", 413)
            return message

        await self.app(scope, bounded_receive, send)


app.add_middleware(BodyLimitMiddleware)


@app.middleware("http")
async def local_access(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin not in ORIGINS):
        return JSONResponse(
            status_code=403, content={"data": None, "message": "仅允许本地应用访问"}
        )
    try:
        if int(request.headers.get("content-length", "0")) > 125 * 1024 * 1024:
            return JSONResponse(
                status_code=413, content={"data": None, "message": "请求体超过 125 MB"}
            )
    except ValueError:
        return JSONResponse(
            status_code=400, content={"data": None, "message": "无效 Content-Length"}
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status, content={"data": None, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    messages = [".".join(str(x) for x in e["loc"]) + ": " + e["msg"] for e in exc.errors()]
    return JSONResponse(
        status_code=422, content={"data": None, "message": "参数错误：" + "; ".join(messages)}
    )


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409, content={"data": None, "message": "数据冲突，请检查重复样本或关联记录"}
    )


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    logging.exception("Unhandled API error", exc_info=exc)
    return JSONResponse(
        status_code=500, content={"data": None, "message": "处理失败，请查看本地后端日志"}
    )


app.include_router(router)
