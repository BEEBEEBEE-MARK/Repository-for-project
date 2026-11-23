"""旅行计划相关请求模型。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class GuideItem(BaseModel):
    type: Literal["link", "text"]
    content: str


class GenerateRequest(BaseModel):
    departure: str
    destination: str
    days: int
    start_date: date | None = None
    budget_per_person: int
    people: int
    interest_tags: list[str] = Field(default_factory=list)
    pace: str | None = None
    transport_pref: str | None = None
    hotel_pref: str | None = None
    special_needs: str | None = None
    guides: list[GuideItem] = Field(default_factory=list)


class GuideSource(BaseModel):
    type: str
    url: str | None = None
    label: str | None = None


class SavePlanRequest(BaseModel):
    departure: str
    destination: str
    days: int
    start_date: date | None = None
    budget_per_person: int
    people: int
    interest_tags: list[str] = Field(default_factory=list)
    pace: str | None = None
    transport_pref: str | None = None
    hotel_pref: str | None = None
    special_needs: str | None = None
    used_guide: bool = False
    guide_sources: list[GuideSource] = Field(default_factory=list)
    plan_content: dict
