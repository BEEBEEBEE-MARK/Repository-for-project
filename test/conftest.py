"""pytest 公共配置。

关键约束：测试使用**独立的临时数据库**，绝不触碰 backend/travel.db。
必须在导入 app 之前设置 SQLITE_PATH（config 在导入时读取）。
"""

import os
import sys
import tempfile
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEST_DIR.parent / "backend"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TEST_DIR))

_TEST_DIR = tempfile.mkdtemp(prefix="travel_plan_test_")
os.environ["SQLITE_PATH"] = str(Path(_TEST_DIR) / "test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import RATE_LIMITER, app  # noqa: E402
from app.models import InviteCode, TravelRecord, User  # noqa: E402
from helpers import auth_headers  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """每个用例前清空数据，保证用例互不影响。"""
    db = SessionLocal()
    try:
        db.query(TravelRecord).delete()
        db.query(User).delete()
        db.query(InviteCode).delete()
        db.commit()
    finally:
        db.close()
    RATE_LIMITER.reset()
    yield


@pytest.fixture()
def client():
    # 不使用 with，避免触发 lifespan（会自动创建默认邀请码）
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def headers(client, db):
    """创建默认用户并登录，返回带 Bearer token 的请求头。"""
    return auth_headers(client, db)
