"""用户表。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)

    # 登录锁定（登录 PRD §5）
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 邀请来源（仅溯源，不参与登录/权限/展示）
    invite_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("invite_codes.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        # 用户名、邮箱唯一且不区分大小写（SQLite 普通唯一索引区分大小写）
        Index("uk_users_username", text("username COLLATE NOCASE"), unique=True),
        Index("uk_users_email", text("email COLLATE NOCASE"), unique=True),
        Index("idx_users_invite", "invite_code_id"),
    )
