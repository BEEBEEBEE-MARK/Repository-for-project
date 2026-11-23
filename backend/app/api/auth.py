"""认证接口：注册、登录、当前用户。

依据：用户注册-需求描述.md v1.3、用户登录-需求描述.md v1.1、接口文档.md
"""

import re
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.security import create_token, hash_password, utcnow, verify_password
from ..models import InviteCode, User
from ..schemas.auth import LoginRequest, RegisterRequest
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9!@#$%^&*]{6,20}$")
INVITE_PATTERN = re.compile(r"^[A-Za-z0-9]{6,20}$")

RESERVED_USERNAMES = {"admin", "root", "administrator"}
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 5


def ok(data=None) -> dict:
    return {"code": 0, "message": "ok", "data": data}


def fail(code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": message, "data": None},
    )


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    username = payload.username.strip()
    email = payload.email.strip()
    password = payload.password
    invite_input = payload.invite_code.strip()

    # 1. 用户名：格式 → 保留字 → 唯一性（不区分大小写）
    if not USERNAME_PATTERN.fullmatch(username):
        return fail(400, "用户名需为 3-20 位字母、数字或下划线")
    if username.lower() in RESERVED_USERNAMES:
        return fail(400, "该用户名为系统保留，请更换")
    exists = db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()
    if exists:
        return fail(400, "用户名已存在")

    # 2. 邮箱：格式 → 唯一性（不区分大小写）
    if not EMAIL_PATTERN.fullmatch(email):
        return fail(400, "请输入正确的邮箱格式")
    exists = db.execute(
        select(User).where(func.lower(User.email) == email.lower())
    ).scalar_one_or_none()
    if exists:
        return fail(400, "邮箱已被注册")

    # 3. 密码
    if not PASSWORD_PATTERN.fullmatch(password):
        return fail(400, "密码需为 6-20 位，且必须包含字母和数字")

    # 4. 邀请码：为空 → 格式 → 存在/启用/未过期/未用满（统一提示）
    if not invite_input:
        return fail(400, "请输入邀请码")
    if not INVITE_PATTERN.fullmatch(invite_input):
        return fail(400, "邀请码错误")

    invite = db.execute(
        select(InviteCode).where(InviteCode.code == invite_input.upper())
    ).scalar_one_or_none()
    now = utcnow()
    if (
        not invite
        or not invite.enabled
        or (invite.expires_at is not None and invite.expires_at <= now)
        or invite.used_count >= invite.max_uses
    ):
        return fail(400, "邀请码错误")

    # 5. 创建用户 + 邀请码计数，同一事务
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        failed_login_count=0,
        locked_until=None,
        created_at=now,
        invite_code_id=invite.id,
    )
    invite.used_count += 1
    db.add(user)
    db.commit()
    db.refresh(user)

    return ok({"id": user.id, "username": user.username, "email": user.email})


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    account = payload.account.strip()
    password = payload.password

    if not account:
        return fail(400, "请输入用户名")
    if not password:
        return fail(400, "请输入密码")

    # 单输入框：含 @ 按邮箱匹配，否则按用户名
    if "@" in account:
        stmt = select(User).where(func.lower(User.email) == account.lower())
    else:
        stmt = select(User).where(func.lower(User.username) == account.lower())
    user = db.execute(stmt).scalar_one_or_none()

    now = utcnow()

    # 锁定期内一律拒绝（即使密码正确）
    if user and user.locked_until and user.locked_until > now:
        return fail(429, "尝试次数过多，请 5 分钟后再试")

    # 锁定已到期：重置计数
    if user and user.locked_until and user.locked_until <= now:
        user.locked_until = None
        user.failed_login_count = 0

    # 凭证校验失败：计数 +1，达到阈值即锁定
    if not user or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_login_count = 0
                db.commit()
                return fail(429, "尝试次数过多，请 5 分钟后再试")
            db.commit()
        return fail(401, "用户名或密码错误")

    # 登录成功：生成 token，清零失败计数
    expires_in = (
        settings.remember_expire_seconds
        if payload.remember_me
        else settings.token_expire_seconds
    )
    token = create_token(user.id, expires_in)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    return ok(
        {
            "token": token,
            "expires_in": expires_in,
            "user": {"id": user.id, "username": user.username},
        }
    )


@router.get("/check")
def check_availability(
    field: str,
    value: str,
    db: Session = Depends(get_db),
):
    """注册唯一性预检（公开接口，供注册页失焦校验）。

    只返回「是否已被占用」，不返回账号其他信息。
    已知风险：可被用于探测用户名/邮箱是否存在，本期接受（注册 PRD 失焦预检要求）。
    """
    field = (field or "").strip().lower()
    value = (value or "").strip()

    if field not in ("username", "email"):
        return fail(400, "参数错误")
    if not value:
        return fail(400, "请输入内容")

    if field == "username":
        if not USERNAME_PATTERN.fullmatch(value):
            return fail(400, "用户名需为 3-20 位字母、数字或下划线")
        if value.lower() in RESERVED_USERNAMES:
            return ok({"exists": True, "message": "该用户名为系统保留，请更换"})

        exists = db.execute(
            select(User).where(func.lower(User.username) == value.lower())
        ).scalar_one_or_none()
        return ok({
            "exists": bool(exists),
            "message": "用户名已存在" if exists else "",
        })

    if not EMAIL_PATTERN.fullmatch(value):
        return fail(400, "请输入正确的邮箱格式")

    exists = db.execute(
        select(User).where(func.lower(User.email) == value.lower())
    ).scalar_one_or_none()
    return ok({
        "exists": bool(exists),
        "message": "邮箱已被注册" if exists else "",
    })


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return ok(
        {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
        }
    )
