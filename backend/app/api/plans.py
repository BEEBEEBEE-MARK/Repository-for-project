"""旅行计划接口：生成、保存、列表、详情、删除。

依据：旅行计划生成-PRD.md v1.5、我的旅行计划-PRD.md v1.3、接口文档.md v1.0
"""

import json
import re
import threading
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import utcnow
from ..models import TravelRecord, User
from ..schemas.plan import GenerateRequest, SavePlanRequest
from ..services.guide_filter import clean_guide_text, has_valid_content
from ..services.llm import LLMError, LLMTimeout, chat_completion
from ..services.pdf_render import build_filename, render_plan_pdf
from ..services.prompts import (
    SYSTEM_PROMPT,
    TITLE_SUMMARY_PROMPT,
    build_title_summary_prompt,
    build_user_prompt,
)
from .deps import get_current_user

router = APIRouter(prefix="/api/plans", tags=["旅行计划"])

VALID_PERIODS = {"morning", "afternoon", "evening"}
VALID_MARKERS = {"fact", "src", "cat", "feedback"}
PAGE_SIZE = 10

# PDF 导出并发限流（部署约定 §5：同时 ≤2 份，防止内存叠峰）
_PDF_SEMAPHORE = threading.Semaphore(2)


def ok(data=None):
    return {"code": 0, "message": "ok", "data": data}


def fail(code: int, message: str):
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": message, "data": None},
    )


def to_number(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_json(text: str) -> dict | None:
    """容错解析模型输出：去除代码块标记，必要时截取大括号区间。"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    for candidate in (text, _slice_braces(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _slice_braces(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else None


# ---------- 生成 ----------

def validate_generate(payload: GenerateRequest) -> str | None:
    if not payload.departure.strip():
        return "请输入出发地"
    if len(payload.departure.strip()) > 50:
        return "出发地不能超过 50 字"
    if not payload.destination.strip():
        return "请输入目的地"
    if len(payload.destination.strip()) > 50:
        return "目的地不能超过 50 字"
    if not 1 <= payload.days <= 15:
        return "出行天数需为 1-15 天"
    if not 1 <= payload.budget_per_person <= 999999:
        return "请输入人均预算（正整数）"
    if not 1 <= payload.people <= 20:
        return "人数需为 1-20 人"
    if len(payload.guides) > 3:
        return "参考攻略最多 3 条，每条文本不超过 500 字"
    for guide in payload.guides:
        if guide.type == "text" and len(guide.content) > 500:
            return "参考攻略最多 3 条，每条文本不超过 500 字"
    if payload.special_needs and len(payload.special_needs) > 200:
        return "特殊需求不能超过 200 字"
    return None


def normalize_tips(tips) -> dict:
    if not isinstance(tips, dict):
        return {}
    markers = tips.get("markers")
    if not isinstance(markers, dict):
        markers = {}
    return {
        "reservation": str(tips.get("reservation") or ""),
        "duration": str(tips.get("duration") or ""),
        "best_time": str(tips.get("best_time") or ""),
        "ticket": str(tips.get("ticket") or ""),
        "gear": str(tips.get("gear") or ""),
        "markers": {k: v for k, v in markers.items() if v in ("fact", "src")},
    }


def normalize_transport(transport):
    if not isinstance(transport, dict):
        return None

    options = []
    for option in (transport.get("options") or [])[:3]:
        if not isinstance(option, dict):
            continue
        options.append({
            "way": str(option.get("way") or ""),
            "duration": str(option.get("duration") or ""),
            "cost": str(option.get("cost") or ""),
        })
    if not options:
        return None

    marker = transport.get("marker")
    return {
        "options": options,
        "recommendation": str(transport.get("recommendation") or ""),
        "marker": marker if marker in ("fact", "src") else "fact",
    }


def normalize_food(nearby):
    if not isinstance(nearby, dict):
        return None

    items = []
    for item in (nearby.get("items") or [])[:4]:
        if not isinstance(item, dict):
            continue
        items.append({
            "name": str(item.get("name") or ""),
            "desc": str(item.get("desc") or ""),
            "price": str(item.get("price") or ""),
        })
    if not items:
        return None

    marker = nearby.get("marker")
    return {
        "marker": marker if marker in ("src", "cat", "fact") else "fact",
        "items": items,
    }


def normalize_segment(segment):
    """单个长途交通段（去程/返程/城际）。"""
    if not isinstance(segment, dict):
        return None

    options = []
    for option in (segment.get("options") or [])[:3]:
        if not isinstance(option, dict):
            continue
        options.append({
            "way": str(option.get("way") or ""),
            "duration": str(option.get("duration") or ""),
            "cost": str(option.get("cost") or ""),
        })
    if not options:
        return None

    marker = segment.get("marker")
    return {
        "from": str(segment.get("from") or ""),
        "to": str(segment.get("to") or ""),
        "options": options,
        "recommendation": str(segment.get("recommendation") or ""),
        "marker": marker if marker in ("fact", "src") else "fact",
    }


def normalize_long_distance(data):
    """往返 + 城际交通。"""
    if not isinstance(data, dict):
        return None

    outbound = normalize_segment(data.get("outbound"))
    returning = normalize_segment(data.get("return"))
    intercity = [normalize_segment(item) for item in (data.get("intercity") or [])[:5]]
    intercity = [item for item in intercity if item]

    if not outbound and not returning and not intercity:
        return None

    return {"outbound": outbound, "return": returning, "intercity": intercity}


def normalize_accommodations(accommodations) -> list[dict]:
    """住宿推荐：按推荐优先级排序，最多 3 条。"""
    result = []
    for index, item in enumerate((accommodations or [])[:3]):
        if not isinstance(item, dict):
            continue
        marker = item.get("marker")
        result.append({
            "rank": to_number(item.get("rank")) or index + 1,
            "area": str(item.get("area") or ""),
            "name": str(item.get("name") or ""),
            "level": str(item.get("level") or ""),
            "price": str(item.get("price") or ""),
            "reason": str(item.get("reason") or ""),
            "marker": marker if marker in ("fact", "src") else "fact",
        })
    result.sort(key=lambda x: x["rank"])
    return [item for item in result if item["area"] or item["name"]]


def normalize_content(content: dict, form: GenerateRequest) -> dict:
    overview = content.get("overview") if isinstance(content.get("overview"), dict) else {}
    theme = str(overview.get("theme") or "")

    daily = []
    for index, day in enumerate((content.get("daily") or [])[: form.days]):
        if not isinstance(day, dict):
            continue

        blocks = []
        for block in (day.get("blocks") or [])[:3]:
            if not isinstance(block, dict):
                continue
            period = block.get("period")
            blocks.append({
                "period": period if period in VALID_PERIODS else "morning",
                "place": str(block.get("place") or ""),
                "spot_tips": normalize_tips(block.get("spot_tips")),
                "transport": normalize_transport(block.get("transport")),
                "nearby_food": normalize_food(block.get("nearby_food")),
                "meal": str(block.get("meal") or ""),
                "cost": to_number(block.get("cost")),
                "note": str(block.get("note") or ""),
                "pitfall": str(block["pitfall"]) if block.get("pitfall") else None,
            })

        daily.append({
            "day": index + 1,
            "date": (form.start_date + timedelta(days=index)).isoformat() if form.start_date else None,
            "blocks": blocks,
            "alternatives": [str(x) for x in (day.get("alternatives") or []) if x],
        })

    # 预算
    budget_in = content.get("budget") if isinstance(content.get("budget"), dict) else {}
    budget_items = []
    for item in budget_in.get("items") or []:
        if not isinstance(item, dict):
            continue
        budget_items.append({
            "name": str(item.get("name") or ""),
            "amount": to_number(item.get("amount")),
        })
    budget = {"items": budget_items, "total": sum(i["amount"] for i in budget_items)}

    # 注意事项
    notices = []
    for notice in content.get("notices") or []:
        if isinstance(notice, str):
            notices.append({"text": notice, "marker": None})
        elif isinstance(notice, dict):
            marker = notice.get("marker")
            notices.append({
                "text": str(notice.get("text") or ""),
                "marker": marker if marker in VALID_MARKERS else None,
            })
    notices = [n for n in notices if n["text"]]

    alternatives = [str(x) for x in (content.get("alternatives") or []) if x]

    # 来源：只接受文本来源，链接由后端补充（AI 不生成 URL）
    sources = []
    for source in content.get("sources") or []:
        if isinstance(source, dict) and source.get("type") == "text":
            sources.append({
                "type": "text",
                "url": None,
                "label": str(source.get("label") or "用户提供的攻略正文"),
            })

    return {
        "overview": {"theme": theme},
        "long_distance_transport": normalize_long_distance(content.get("long_distance_transport")),
        "daily": daily,
        "accommodations": normalize_accommodations(content.get("accommodations")),
        "budget": budget,
        "notices": notices,
        "alternatives": alternatives,
        "sources": sources,
    }


@router.post("/generate")
def generate(payload: GenerateRequest, current_user: User = Depends(get_current_user)):
    error = validate_generate(payload)
    if error:
        return fail(400, error)

    # 仅「粘贴文本」参与生成；清洗广告与联系方式，全部无效则静默降级
    valid_texts = []
    for guide in payload.guides:
        if guide.type != "text":
            continue
        cleaned = clean_guide_text(guide.content)
        if has_valid_content(cleaned):
            valid_texts.append(cleaned)
    guide_text = "\n\n".join(valid_texts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(payload, guide_text)},
    ]

    try:
        raw = chat_completion(messages, timeout=110)
    except LLMTimeout:
        return fail(504, "生成超时，请重试")
    except LLMError:
        return fail(500, "生成失败，请重试")

    data = parse_json(raw)
    if not data:
        return fail(500, "生成失败，请重试")

    content = normalize_content(data.get("plan_content") or {}, payload)
    if not content["daily"]:
        return fail(500, "生成失败，请重试")

    used_guide = bool(data.get("used_guide")) and bool(valid_texts)
    if used_guide and not content["sources"]:
        content["sources"].append(
            {"type": "text", "url": None, "label": "用户提供的攻略正文"}
        )

    # 链接仅作来源记录（不抓取内容）
    for guide in payload.guides:
        if guide.type == "link" and guide.content.strip():
            content["sources"].append({
                "type": "link",
                "url": guide.content.strip(),
                "label": "分享链接",
            })

    title = str(data.get("title") or "").strip()[:100]
    if not title:
        title = f"{payload.destination.strip()} {payload.days} 日游"

    return ok({"title": title, "used_guide": used_guide, "plan_content": content})


# ---------- 保存 ----------

def validate_save(payload: SavePlanRequest) -> str | None:
    if not payload.departure.strip():
        return "请输入出发地"
    if not payload.destination.strip():
        return "请输入目的地"
    if not 1 <= payload.days <= 15:
        return "出行天数需为 1-15 天"
    if not 1 <= payload.budget_per_person <= 999999:
        return "请输入人均预算（正整数）"
    if not 1 <= payload.people <= 20:
        return "人数需为 1-20 人"
    if not isinstance(payload.plan_content, dict) or not payload.plan_content:
        return "参数错误"
    return None


def make_title_summary(payload: SavePlanRequest) -> tuple[str, str]:
    """AI 生成标题与摘要；失败降级为规则文案（列表 PRD §3.6）。"""
    overview = payload.plan_content.get("overview")
    theme = str(overview.get("theme") or "") if isinstance(overview, dict) else ""

    fallback_title = f"{payload.destination.strip()} {payload.days} 日游"
    fallback_summary = (theme or f"{payload.destination.strip()} {payload.days} 日行程安排")[:50]

    try:
        raw = chat_completion(
            [
                {"role": "system", "content": TITLE_SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": build_title_summary_prompt(
                        payload.destination, payload.days, theme, payload.interest_tags
                    ),
                },
            ],
            timeout=45,
            max_tokens=1500,  # 推理模型会消耗 token 在思考上
            temperature=0.8,
        )
        data = parse_json(raw) or {}
        title = str(data.get("title") or "").strip() or fallback_title
        summary = str(data.get("summary") or "").strip() or fallback_summary
        return title[:100], summary[:100]
    except LLMError:
        return fallback_title, fallback_summary


@router.post("")
def save_plan(
    payload: SavePlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    error = validate_save(payload)
    if error:
        return fail(400, error)

    title, summary = make_title_summary(payload)

    record = TravelRecord(
        user_id=current_user.id,
        title=title,
        summary=summary,
        departure=payload.departure.strip()[:50],
        destination=payload.destination.strip()[:50],
        days=payload.days,
        start_date=payload.start_date,
        people=payload.people,
        budget_per_person=payload.budget_per_person,
        interest_tags=json.dumps(payload.interest_tags, ensure_ascii=False) if payload.interest_tags else None,
        pace=payload.pace,
        transport_pref=payload.transport_pref,
        hotel_pref=payload.hotel_pref,
        special_needs=payload.special_needs,
        used_guide=payload.used_guide,
        guide_sources=(
            json.dumps([s.model_dump() for s in payload.guide_sources], ensure_ascii=False)
            if payload.guide_sources else None
        ),
        plan_content=json.dumps(payload.plan_content, ensure_ascii=False),
        created_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return ok({
        "id": record.id,
        "title": record.title,
        "summary": record.summary,
        "created_at": record.created_at.isoformat() + "Z",
    })


# ---------- 列表 / 详情 / 删除 ----------

@router.get("")
def list_plans(
    page: int = 1,
    keyword: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    page = max(1, page)

    stmt = select(TravelRecord).where(TravelRecord.user_id == current_user.id)
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(TravelRecord.title.like(like), TravelRecord.destination.like(like))
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(TravelRecord.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).scalars().all()

    def to_item(record: TravelRecord) -> dict:
        return {
            "id": record.id,
            "title": record.title,
            "summary": record.summary,
            "departure": record.departure,
            "destination": record.destination,
            "days": record.days,
            "start_date": record.start_date.isoformat() if record.start_date else None,
            "people": record.people,
            "budget_per_person": record.budget_per_person,
            "interest_tags": json.loads(record.interest_tags) if record.interest_tags else [],
            "created_at": record.created_at.isoformat() + "Z",
        }

    return ok({
        "list": [to_item(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
    })


def _get_owned_record(plan_id: int, user: User, db: Session):
    record = db.get(TravelRecord, plan_id)
    if not record:
        return None, fail(404, "计划不存在")
    if record.user_id != user.id:
        return None, fail(403, "无权访问")
    return record, None


@router.get("/{plan_id}")
def get_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record, error = _get_owned_record(plan_id, current_user, db)
    if error:
        return error

    return ok({
        "id": record.id,
        "title": record.title,
        "summary": record.summary,
        "departure": record.departure,
        "destination": record.destination,
        "days": record.days,
        "start_date": record.start_date.isoformat() if record.start_date else None,
        "people": record.people,
        "budget_per_person": record.budget_per_person,
        "interest_tags": json.loads(record.interest_tags) if record.interest_tags else [],
        "pace": record.pace,
        "transport_pref": record.transport_pref,
        "hotel_pref": record.hotel_pref,
        "special_needs": record.special_needs,
        "used_guide": record.used_guide,
        "guide_sources": json.loads(record.guide_sources) if record.guide_sources else [],
        "plan_content": json.loads(record.plan_content),
        "created_at": record.created_at.isoformat() + "Z",
    })


@router.get("/{plan_id}/pdf")
def export_plan_pdf(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出 PDF：纯数据渲染，不调用大模型；成功返回文件流，失败返回统一 JSON。"""
    record, error = _get_owned_record(plan_id, current_user, db)
    if error:
        return error

    with _PDF_SEMAPHORE:
        try:
            pdf_bytes = render_plan_pdf(record)
        except Exception:
            return fail(500, "导出失败，请重试")

    filename = build_filename(record)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record, error = _get_owned_record(plan_id, current_user, db)
    if error:
        return error

    db.delete(record)
    db.commit()
    return ok(None)
