"""应用配置：全部从环境变量读取，代码中不得出现密钥。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录（config.py -> core -> app -> backend）
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    app_env: str = os.getenv("APP_ENV", "development")

    # 认证
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    jwt_algorithm: str = "HS256"
    token_expire_seconds: int = int(os.getenv("TOKEN_EXPIRE_SECONDS", str(12 * 3600)))
    remember_expire_seconds: int = int(os.getenv("REMEMBER_EXPIRE_SECONDS", str(7 * 24 * 3600)))

    # 数据库
    sqlite_path: str = os.getenv("SQLITE_PATH", str(BASE_DIR / "travel.db"))

    # DeepSeek（Anthropic 兼容端点）
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    # deepseek-flash 为推理模型，关闭思考可显著降低耗时与 token 消耗
    deepseek_disable_thinking: bool = os.getenv(
        "DEEPSEEK_DISABLE_THINKING", "true"
    ).lower() in ("1", "true", "yes")

    # 安全：接口文档仅开发环境默认开启（生产暴露 /docs 会泄露完整接口结构）
    # 显式设置 ENABLE_DOCS 可覆盖
    _enable_docs_raw: str | None = os.getenv("ENABLE_DOCS")

    # 安全：请求体上限（字节），默认 1MB；计划内容单独限制（见 MAX_PLAN_CONTENT_BYTES）
    max_body_bytes: int = int(os.getenv("MAX_BODY_BYTES", str(1024 * 1024)))
    max_plan_content_bytes: int = int(os.getenv("MAX_PLAN_CONTENT_BYTES", str(512 * 1024)))

    # 安全：限流（单 worker 内存实现；阈值按「IP + 接口」的每分钟次数）
    rate_limit_enabled: bool = _env_bool("RATE_LIMIT_ENABLED", True)
    rate_limit_login: int = int(os.getenv("RATE_LIMIT_LOGIN", "20"))
    rate_limit_register: int = int(os.getenv("RATE_LIMIT_REGISTER", "10"))
    rate_limit_check: int = int(os.getenv("RATE_LIMIT_CHECK", "60"))
    rate_limit_generate: int = int(os.getenv("RATE_LIMIT_GENERATE", "5"))
    rate_limit_save: int = int(os.getenv("RATE_LIMIT_SAVE", "20"))

    # 安全：生成接口全局并发上限（LLM 等待期占用线程，防止并发打满内存与 API 配额）
    generate_concurrency: int = int(os.getenv("GENERATE_CONCURRENCY", "4"))

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def enable_docs(self) -> bool:
        if self._enable_docs_raw is None:
            return self.is_dev
        return self._enable_docs_raw.strip().lower() in ("1", "true", "yes", "on")


settings = Settings()
