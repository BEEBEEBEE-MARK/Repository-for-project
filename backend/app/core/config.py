"""应用配置：全部从环境变量读取，代码中不得出现密钥。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录（config.py -> core -> app -> backend）
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


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

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()
