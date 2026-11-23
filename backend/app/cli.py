"""命令行工具：邀请码管理。

用法（在 backend/ 目录执行）：
    uv run python -m app.cli invite create --note "老王" --max-uses 1 --days 30
    uv run python -m app.cli invite list
    uv run python -m app.cli invite show TEST2026
    uv run python -m app.cli invite disable TEST2026
    uv run python -m app.cli invite enable TEST2026
    uv run python -m app.cli invite delete TEST2026
"""

import argparse
import secrets
import string
import sys
from datetime import timedelta

from .core.database import Base, SessionLocal, engine
from .core.security import utcnow
from .models import InviteCode, User

# Windows 终端中文输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass


def _generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _expires_at(days: int):
    return None if days == 0 else utcnow() + timedelta(days=days)


def _find(db, code: str) -> InviteCode | None:
    return db.query(InviteCode).filter(InviteCode.code == code.strip().upper()).first()


def _status(invite: InviteCode) -> str:
    now = utcnow()
    if not invite.enabled:
        return "已停用"
    if invite.expires_at and invite.expires_at <= now:
        return "已过期"
    if invite.used_count >= invite.max_uses:
        return "已用尽"
    return "使用中"


# ---------- 子命令 ----------

def cmd_create(args):
    if args.max_uses < 1:
        print("--max-uses 必须大于等于 1")
        return 1
    if args.days < 0:
        print("--days 不能为负数")
        return 1

    db = SessionLocal()
    try:
        code = (args.code or _generate_code()).strip().upper()

        if _find(db, code):
            print(f"邀请码 {code} 已存在，请换一个")
            return 1

        invite = InviteCode(
            code=code,
            note=args.note,
            max_uses=args.max_uses,
            used_count=0,
            expires_at=_expires_at(args.days),
            enabled=True,
            created_at=utcnow(),
        )
        db.add(invite)
        db.commit()

        expire_text = "永不过期" if invite.expires_at is None else invite.expires_at.strftime("%Y-%m-%d %H:%M")
        print(f"已生成邀请码：{code}")
        print(f"  备注：{invite.note or '—'}　可用 {invite.max_uses} 次　有效期至：{expire_text}")
        print("把该码发给对方，对方在注册页填写即可。")
        return 0
    finally:
        db.close()


def cmd_list(args):
    db = SessionLocal()
    try:
        invites = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
        if not invites:
            print("暂无邀请码。使用 invite create 生成。")
            return 0

        print(f"{'CODE':<12}{'备注':<10}{'使用':<8}{'状态':<8}过期时间")
        print("-" * 62)
        for inv in invites:
            expire = "永不过期" if inv.expires_at is None else inv.expires_at.strftime("%Y-%m-%d")
            print(
                f"{inv.code:<12}{(inv.note or '—'):<10}"
                f"{str(inv.used_count) + '/' + str(inv.max_uses):<8}"
                f"{_status(inv):<8}{expire}"
            )
        return 0
    finally:
        db.close()


def cmd_show(args):
    db = SessionLocal()
    try:
        invite = _find(db, args.code)
        if not invite:
            print(f"邀请码 {args.code} 不存在")
            return 1

        expire = "永不过期" if invite.expires_at is None else invite.expires_at.strftime("%Y-%m-%d %H:%M")
        print(f"邀请码：{invite.code}（备注：{invite.note or '—'}）")
        print(f"状态：{_status(invite)}　{invite.used_count}/{invite.max_uses}　过期：{expire}")

        users = db.query(User).filter(User.invite_code_id == invite.id).order_by(User.created_at).all()
        if not users:
            print("\n使用人：暂无")
            return 0

        print("\n使用人：")
        print(f"{'用户名':<16}{'邮箱':<28}注册时间")
        print("-" * 66)
        for user in users:
            print(
                f"{user.username:<16}{user.email:<28}"
                f"{user.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        return 0
    finally:
        db.close()


def _set_enabled(args, enabled: bool):
    db = SessionLocal()
    try:
        invite = _find(db, args.code)
        if not invite:
            print(f"邀请码 {args.code} 不存在")
            return 1
        invite.enabled = enabled
        db.commit()
        print(f"邀请码 {invite.code} 已{'启用' if enabled else '停用'}")
        return 0
    finally:
        db.close()


def cmd_enable(args):
    return _set_enabled(args, True)


def cmd_disable(args):
    return _set_enabled(args, False)


def cmd_delete(args):
    db = SessionLocal()
    try:
        invite = _find(db, args.code)
        if not invite:
            print(f"邀请码 {args.code} 不存在")
            return 1
        code = invite.code
        db.delete(invite)
        db.commit()
        print(f"邀请码 {code} 已删除（使用者的邀请来源记录将被置空）")
        return 0
    finally:
        db.close()


# ---------- 入口 ----------

def main(argv: list[str] | None = None) -> int:
    Base.metadata.create_all(bind=engine)

    parser = argparse.ArgumentParser(prog="app.cli", description="旅梦规划助手命令行工具")
    groups = parser.add_subparsers(dest="group", required=True)

    invite_parser = groups.add_parser("invite", help="邀请码管理")
    actions = invite_parser.add_subparsers(dest="action", required=True)

    create = actions.add_parser("create", help="生成邀请码")
    create.add_argument("--note", default=None, help="备注：发给谁 / 用途")
    create.add_argument("--max-uses", type=int, default=1, help="最大可用次数（默认 1）")
    create.add_argument("--days", type=int, default=30, help="有效天数，0 表示永不过期（默认 30）")
    create.add_argument("--code", default=None, help="自定义邀请码（默认随机 8 位）")
    create.set_defaults(func=cmd_create)

    listing = actions.add_parser("list", help="查看全部邀请码")
    listing.set_defaults(func=cmd_list)

    show = actions.add_parser("show", help="查看某个码的使用人")
    show.add_argument("code")
    show.set_defaults(func=cmd_show)

    disable = actions.add_parser("disable", help="停用邀请码")
    disable.add_argument("code")
    disable.set_defaults(func=cmd_disable)

    enable = actions.add_parser("enable", help="启用邀请码")
    enable.add_argument("code")
    enable.set_defaults(func=cmd_enable)

    delete = actions.add_parser("delete", help="删除邀请码")
    delete.add_argument("code")
    delete.set_defaults(func=cmd_delete)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
