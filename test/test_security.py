"""安全配套测试：安全响应头、请求体上限、接口限流、体积校验、LIKE 转义。"""

import json

from app.core.security import utcnow
from app.models import TravelRecord, User

from helpers import create_user


def add_record(db, user_id, title, destination="昆明"):
    record = TravelRecord(
        user_id=user_id,
        title=title,
        summary="摘要",
        departure="上海",
        destination=destination,
        days=1,
        start_date=None,
        people=2,
        budget_per_person=3000,
        interest_tags=None,
        pace=None,
        transport_pref=None,
        hotel_pref=None,
        special_needs=None,
        used_guide=False,
        guide_sources=None,
        plan_content=json.dumps({"daily": []}, ensure_ascii=False),
        created_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------- 安全响应头 ----------

def test_security_headers_present(client):
    resp = client.get("/api/health")

    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert "server" not in resp.headers


# ---------- 接口文档开关 ----------

def test_docs_enabled_in_dev_env(client):
    """测试环境为 development，接口文档应可访问（生产默认关闭）。"""
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


# ---------- 请求体上限 ----------

def test_body_too_large_returns_413(client):
    oversized = b"x" * (1024 * 1024 + 100)
    resp = client.post(
        "/api/auth/register",
        content=oversized,
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 413
    assert resp.json()["code"] == 413
    assert resp.json()["message"] == "请求内容过大，请减小提交内容"


# ---------- 限流 ----------

def test_login_rate_limited(client):
    payload = {"account": "nobody", "password": "abc123456"}

    for _ in range(20):
        assert client.post("/api/auth/login", json=payload).status_code == 401

    resp = client.post("/api/auth/login", json=payload)
    assert resp.status_code == 429
    assert resp.json()["message"] == "操作过于频繁，请稍后再试"
    assert "retry-after" in resp.headers


def test_register_rate_limited(client):
    payload = {
        "username": "tester01",
        "email": "tester01@example.com",
        "password": "abc123456",
        "invite_code": "TEST2026",
    }

    for _ in range(10):
        assert client.post("/api/auth/register", json=payload).status_code == 400

    assert client.post("/api/auth/register", json=payload).status_code == 429


def test_generate_rate_limited_before_auth(client):
    """限流在鉴权之前生效，未登录也会被计数。"""
    for _ in range(5):
        assert client.post("/api/plans/generate", json={}).status_code in (400, 401)

    assert client.post("/api/plans/generate", json={}).status_code == 429


# ---------- 计划内容体积 ----------

def test_plan_content_too_large_rejected(client, db, headers):
    payload = {
        "departure": "上海",
        "destination": "昆明",
        "days": 1,
        "start_date": None,
        "budget_per_person": 3000,
        "people": 2,
        "interest_tags": [],
        "pace": None,
        "transport_pref": None,
        "hotel_pref": None,
        "special_needs": None,
        "used_guide": False,
        "guide_sources": [],
        "plan_content": {"blob": "x" * (600 * 1024)},
    }

    resp = client.post("/api/plans", headers=headers, json=payload)
    body = resp.json()

    assert resp.status_code == 400
    assert body["message"] == "计划内容过大"


# ---------- LIKE 通配符转义 ----------

def test_keyword_wildcards_are_escaped(client, db, headers):
    user = db.query(User).filter_by(username="tester01").first()
    add_record(db, user.id, "abc")
    add_record(db, user.id, "a_c")

    body = client.get("/api/plans", headers=headers, params={"keyword": "_"}).json()

    # 下划线应作为普通字符匹配，只命中 a_c
    assert body["data"]["total"] == 1
    assert body["data"]["list"][0]["title"] == "a_c"
