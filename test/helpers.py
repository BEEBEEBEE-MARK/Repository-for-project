"""测试数据构造工具（与 conftest 的 fixture 分离，便于直接导入）。"""

from datetime import timedelta

from app.core.security import hash_password, utcnow
from app.models import InviteCode, User


def create_invite(
    db,
    code: str = "TEST2026",
    max_uses: int = 5,
    days: int | None = 30,
    enabled: bool = True,
    used_count: int = 0,
) -> InviteCode:
    now = utcnow()
    invite = InviteCode(
        code=code.upper(),
        note="测试邀请码",
        max_uses=max_uses,
        used_count=used_count,
        expires_at=None if days is None else now + timedelta(days=days),
        enabled=enabled,
        created_at=now,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def create_user(
    db,
    username: str = "tester01",
    email: str = "tester01@example.com",
    password: str = "abc123456",
    failed_login_count: int = 0,
    locked_until=None,
) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        failed_login_count=failed_login_count,
        locked_until=locked_until,
        created_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register_payload(**overrides) -> dict:
    payload = {
        "username": "tester01",
        "email": "tester01@example.com",
        "password": "abc123456",
        "invite_code": "TEST2026",
    }
    payload.update(overrides)
    return payload


def auth_headers(client, db, username: str = "tester01", password: str = "abc123456") -> dict:
    """创建用户并登录，返回带 Bearer token 的请求头。"""
    create_user(db, username=username, email=f"{username}@example.com", password=password)
    body = client.post(
        "/api/auth/login", json={"account": username, "password": password}
    ).json()
    return {"Authorization": f"Bearer {body['data']['token']}"}


def login_payload(**overrides) -> dict:
    payload = {
        "account": "tester01",
        "password": "abc123456",
        "remember_me": False,
    }
    payload.update(overrides)
    return payload
