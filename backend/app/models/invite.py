"""邀请码表。"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 统一存大写，校验时先 upper() 再比对
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    note: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("max_uses >= 1", name="ck_invite_max_uses"),
        CheckConstraint("used_count >= 0", name="ck_invite_used_count"),
    )
