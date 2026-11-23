"""应用入口。

启动：uv run uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.auth import router as auth_router
from .api.plans import router as plans_router
from .core.database import Base, SessionLocal, engine
from .core.security import utcnow
from .models import InviteCode  # noqa: F401  （导入以注册模型）

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
DEFAULT_INVITE_CODE = "DEV-DEFAULT"


def _ensure_default_invite() -> None:
    """首次启动且邀请码表为空时，创建本地开发默认邀请码。"""
    db = SessionLocal()
    try:
        if db.query(InviteCode).first():
            return
        db.add(
            InviteCode(
                code=DEFAULT_INVITE_CODE,
                note="本地开发默认邀请码",
                max_uses=999,
                used_count=0,
                expires_at=None,
                enabled=True,
                created_at=utcnow(),
            )
        )
        db.commit()
        print(f"[INIT] 邀请码表为空，已创建默认邀请码：{DEFAULT_INVITE_CODE}（可用 999 次，永不过期）")
    finally:
        db.close()


def _ensure_schema() -> None:
    """建表 + 轻量迁移（SQLite 不支持 create_all 补列，需手动 ALTER）。"""
    Base.metadata.create_all(bind=engine)

    columns = {col["name"] for col in inspect(engine).get_columns("travel_records")}
    if "departure" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE travel_records ADD COLUMN departure VARCHAR(50)"))
        print("[MIGRATE] travel_records 新增 departure 列")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
    _ensure_default_invite()
    yield


app = FastAPI(title="旅梦规划助手 API", lifespan=lifespan)

# 开发环境允许任何 localhost 来源（Live Server 端口可能是 5500/5501 等）
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """把 HTTP 异常（含路由 404/405）转成统一响应格式。

    必须注册 Starlette 的 HTTPException：FastAPI 的 HTTPException 是它的子类，
    注册父类可同时覆盖业务异常与框架级 404/405。
    """
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else "请求失败"

    # Starlette 默认的 404/405 文案是英文，统一转成可展示的中文
    default_messages = {
        "Not Found": "接口不存在",
        "Method Not Allowed": "请求方法不支持",
    }
    message = default_messages.get(message, message)

    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": message, "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"code": 400, "message": "参数错误", "data": None},
    )


@app.get("/api/health")
def health():
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}}


app.include_router(auth_router)
app.include_router(plans_router)

# 生产环境同源托管前端（开发时前端跑在 5500，不受影响）
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
