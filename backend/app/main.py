"""应用入口。

启动：uv run uvicorn app.main:app --reload --port 8000
"""

import logging
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
from .core.config import settings
from .core.database import Base, SessionLocal, engine
from .core.limits import RateLimiterRegistry
from .core.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from .core.security import utcnow
from .models import InviteCode  # noqa: F401  （导入以注册模型）

logger = logging.getLogger("app.main")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
DEFAULT_INVITE_CODE = "DEV-DEFAULT"


def _ensure_default_invite() -> None:
    """首次启动且邀请码表为空时，创建本地开发默认邀请码。

    生产环境禁止自动创建：否则邀请码表一旦被清空，会重新出现 999 次永不过期的万能码。
    """
    if not settings.is_dev:
        return

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


app = FastAPI(
    title="旅梦规划助手 API",
    lifespan=lifespan,
    # 生产默认关闭接口文档（/docs、/openapi.json 会暴露完整接口结构）
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

# 限流规则集中维护（测试可调用 RATE_LIMITER.reset() 清空计数）
RATE_LIMITER = RateLimiterRegistry([
    ("/api/auth/login", "POST", settings.rate_limit_login, 60),
    ("/api/auth/register", "POST", settings.rate_limit_register, 60),
    ("/api/auth/check", "GET", settings.rate_limit_check, 60),
    ("/api/plans/generate", "POST", settings.rate_limit_generate, 60),
    ("/api/plans", "POST", settings.rate_limit_save, 60),
])

# 安全中间件注册顺序：后添加的在外层。
# 最终由外到内：SecurityHeaders → RateLimit → CORS → BodySize
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
if settings.rate_limit_enabled:
    app.add_middleware(RateLimitMiddleware, registry=RATE_LIMITER)

# 开发环境允许任何 localhost 来源（Live Server 端口可能是 5500/5501 等）
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)


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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未处理异常统一兜底：对外只给通用文案，细节只写入服务器日志。"""
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器开小差了，请稍后重试", "data": None},
    )


@app.get("/api/health")
def health():
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}}


app.include_router(auth_router)
app.include_router(plans_router)

# 生产环境同源托管前端（开发时前端跑在 5500，不受影响）
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
