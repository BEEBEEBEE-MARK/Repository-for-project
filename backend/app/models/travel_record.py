"""旅行计划记录表（已保存的计划）。

只增不覆盖：不设 updated_at；删除为硬删除。
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class TravelRecord(Base):
    __tablename__ = "travel_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # AI 生成并落库的轻量文案（失败时降级为规则文案）
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(100), nullable=False)

    # 生成条件
    departure: Mapped[str | None] = mapped_column(String(50), nullable=True)
    destination: Mapped[str] = mapped_column(String(50), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    people: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_per_person: Mapped[int] = mapped_column(Integer, nullable=False)
    interest_tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组
    pace: Mapped[str | None] = mapped_column(String(10), nullable=True)
    transport_pref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hotel_pref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    special_needs: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 攻略标记与来源（不存粘贴正文）
    used_guide: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    guide_sources: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组

    # 完整计划内容（JSON，结构见 数据库设计 §6.1）
    plan_content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("days BETWEEN 1 AND 15", name="ck_travel_days"),
        CheckConstraint("people BETWEEN 1 AND 20", name="ck_travel_people"),
        CheckConstraint("budget_per_person >= 1", name="ck_travel_budget"),
        Index("idx_travel_records_user_time", "user_id", text("created_at DESC")),
    )
