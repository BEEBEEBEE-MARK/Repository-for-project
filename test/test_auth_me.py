"""当前用户接口与 JWT 校验测试。"""

from app.models import User

from helpers import create_user, login_payload


def _login_token(client, db) -> str:
    create_user(db)
    body = client.post("/api/auth/login", json=login_payload()).json()
    return body["data"]["token"]


def test_me_success(client, db):
    token = _login_token(client, db)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["username"] == "tester01"
    assert body["data"]["email"] == "tester01@example.com"


def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    body = resp.json()

    assert resp.status_code == 401
    assert body["code"] == 401
    assert body["message"] == "未登录或登录已过期"


def test_me_invalid_token(client):
    resp = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer invalid.token.value"}
    )

    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_me_token_with_deleted_user(client, db):
    token = _login_token(client, db)

    user = db.query(User).filter(User.username == "tester01").one()
    db.delete(user)
    db.commit()

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.json()["message"] == "未登录或登录已过期"
