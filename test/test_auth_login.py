"""登录接口测试（依据《用户登录-需求描述.md》v1.1）。"""

from datetime import timedelta

from app.core.security import utcnow
from app.models import User

from helpers import create_user, login_payload


def test_login_by_username(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload()).json()

    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["user"]["username"] == "tester01"


def test_login_by_email(client, db):
    create_user(db)

    body = client.post(
        "/api/auth/login", json=login_payload(account="tester01@example.com")
    ).json()

    assert body["code"] == 0


def test_login_username_case_insensitive(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload(account="TESTER01")).json()

    assert body["code"] == 0


def test_login_email_case_insensitive(client, db):
    create_user(db)

    body = client.post(
        "/api/auth/login", json=login_payload(account="TESTER01@EXAMPLE.COM")
    ).json()

    assert body["code"] == 0


def test_login_account_trims_spaces(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload(account="  tester01  ")).json()

    assert body["code"] == 0


def test_login_wrong_password(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload(password="wrong123")).json()

    assert body["code"] == 401
    assert body["message"] == "用户名或密码错误"


def test_login_unknown_account_uses_same_message(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload(account="nobody")).json()

    assert body["code"] == 401
    assert body["message"] == "用户名或密码错误"


def test_login_empty_account(client, db):
    body = client.post("/api/auth/login", json=login_payload(account="")).json()

    assert body["code"] == 400
    assert body["message"] == "请输入用户名"


def test_login_empty_password(client, db):
    body = client.post("/api/auth/login", json=login_payload(password="")).json()

    assert body["code"] == 400
    assert body["message"] == "请输入密码"


def test_login_default_expiry_is_12_hours(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload()).json()

    assert body["data"]["expires_in"] == 12 * 3600


def test_login_remember_me_expiry_is_7_days(client, db):
    create_user(db)

    body = client.post("/api/auth/login", json=login_payload(remember_me=True)).json()

    assert body["data"]["expires_in"] == 7 * 24 * 3600


def test_login_lock_after_five_failures(client, db):
    create_user(db)

    for _ in range(4):
        body = client.post("/api/auth/login", json=login_payload(password="wrong123")).json()
        assert body["code"] == 401

    body = client.post("/api/auth/login", json=login_payload(password="wrong123")).json()
    assert body["code"] == 429
    assert body["message"] == "尝试次数过多，请 5 分钟后再试"


def test_login_locked_rejects_correct_password(client, db):
    create_user(db, failed_login_count=5, locked_until=utcnow() + timedelta(minutes=5))

    body = client.post("/api/auth/login", json=login_payload()).json()

    assert body["code"] == 429
    assert body["message"] == "尝试次数过多，请 5 分钟后再试"


def test_four_failures_do_not_lock(client, db):
    user = create_user(db)

    for _ in range(4):
        client.post("/api/auth/login", json=login_payload(password="wrong123"))

    db.expire_all()
    refreshed = db.get(User, user.id)
    assert refreshed.failed_login_count == 4
    assert refreshed.locked_until is None


def test_login_success_resets_failure_count(client, db):
    user = create_user(db)

    for _ in range(3):
        client.post("/api/auth/login", json=login_payload(password="wrong123"))

    body = client.post("/api/auth/login", json=login_payload()).json()
    assert body["code"] == 0

    db.expire_all()
    refreshed = db.get(User, user.id)
    assert refreshed.failed_login_count == 0
    assert refreshed.locked_until is None
    assert refreshed.last_login_at is not None


def test_login_unlocks_after_lock_expires(client, db):
    create_user(db, failed_login_count=5, locked_until=utcnow() - timedelta(minutes=1))

    body = client.post("/api/auth/login", json=login_payload()).json()

    assert body["code"] == 0
