"""注册接口测试（依据《用户注册-需求描述.md》v1.3）。"""

import pytest
from sqlalchemy import select

from app.models import User

from helpers import create_invite, create_user, register_payload


def test_register_success(client, db):
    create_invite(db)

    resp = client.post("/api/auth/register", json=register_payload())
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["username"] == "tester01"
    assert body["data"]["email"] == "tester01@example.com"
    # 注册成功后不自动登录（不返回 token）
    assert "token" not in body["data"]

    user = db.execute(select(User).where(User.username == "tester01")).scalar_one()
    assert user.password_hash != "abc123456"  # 必须哈希存储
    assert user.password_hash.startswith("$2")  # bcrypt


def test_register_records_invite_source_and_increments_usage(client, db):
    invite = create_invite(db, max_uses=5)

    client.post("/api/auth/register", json=register_payload())

    user = db.execute(select(User).where(User.username == "tester01")).scalar_one()
    db.refresh(invite)

    assert user.invite_code_id == invite.id  # 记录邀请来源
    assert invite.used_count == 1  # 使用次数 +1


@pytest.mark.parametrize(
    "username",
    ["ab", "a" * 21, "中文名", "bad-name", "bad name", "user!", ""],
)
def test_register_invalid_username_format(client, db, username):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(username=username)).json()
    assert body["code"] == 400
    # 空用户名会先命中「请输入目的地」之外的字段校验，统一为格式提示
    assert body["message"] == "用户名需为 3-20 位字母、数字或下划线"


@pytest.mark.parametrize("username", ["admin", "root", "administrator", "ADMIN", "Root"])
def test_register_reserved_username(client, db, username):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(username=username)).json()
    assert body["code"] == 400
    assert body["message"] == "该用户名为系统保留，请更换"


def test_register_duplicate_username_case_insensitive(client, db):
    create_invite(db)
    create_user(db, username="tester01", email="other@example.com")

    body = client.post(
        "/api/auth/register",
        json=register_payload(username="TESTER01", email="new@example.com"),
    ).json()

    assert body["code"] == 400
    assert body["message"] == "用户名已存在"


@pytest.mark.parametrize("email", ["bad", "a@b", "@example.com", "a b@example.com", ""])
def test_register_invalid_email_format(client, db, email):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(email=email)).json()
    assert body["code"] == 400
    assert body["message"] == "请输入正确的邮箱格式"


def test_register_duplicate_email_case_insensitive(client, db):
    create_invite(db)
    create_user(db, username="otheruser", email="tester01@example.com")

    body = client.post(
        "/api/auth/register",
        json=register_payload(username="tester02", email="TESTER01@example.com"),
    ).json()

    assert body["code"] == 400
    assert body["message"] == "邮箱已被注册"


@pytest.mark.parametrize("password", ["123456", "abcdef", "abc 123", "a1", "a" * 21 + "1"])
def test_register_weak_password(client, db, password):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(password=password)).json()
    assert body["code"] == 400
    assert body["message"] == "密码需为 6-20 位，且必须包含字母和数字"


def test_register_empty_invite(client, db):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(invite_code="")).json()
    assert body["code"] == 400
    assert body["message"] == "请输入邀请码"


@pytest.mark.parametrize("code", ["ABC", "a" * 21, "bad-code", "邀请码"])
def test_register_invalid_invite_format(client, db, code):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(invite_code=code)).json()
    assert body["code"] == 400
    assert body["message"] == "邀请码错误"


def test_register_invite_not_found(client, db):
    create_invite(db)

    body = client.post("/api/auth/register", json=register_payload(invite_code="NOTEXIST")).json()
    assert body["code"] == 400
    assert body["message"] == "邀请码错误"


def test_register_invite_expired(client, db):
    create_invite(db, days=-1)

    body = client.post("/api/auth/register", json=register_payload()).json()
    assert body["code"] == 400
    assert body["message"] == "邀请码错误"


def test_register_invite_disabled(client, db):
    create_invite(db, enabled=False)

    body = client.post("/api/auth/register", json=register_payload()).json()
    assert body["code"] == 400
    assert body["message"] == "邀请码错误"


def test_register_invite_exhausted(client, db):
    create_invite(db, max_uses=1, used_count=1)

    body = client.post("/api/auth/register", json=register_payload()).json()
    assert body["code"] == 400
    assert body["message"] == "邀请码错误"


def test_register_invite_case_insensitive(client, db):
    create_invite(db, code="TEST2026")

    body = client.post(
        "/api/auth/register",
        json=register_payload(invite_code="test2026"),
    ).json()

    assert body["code"] == 0


def test_register_failed_does_not_consume_invite(client, db):
    invite = create_invite(db, max_uses=1)

    # 用户名为保留字，注册失败
    client.post("/api/auth/register", json=register_payload(username="admin"))

    db.refresh(invite)
    assert invite.used_count == 0
