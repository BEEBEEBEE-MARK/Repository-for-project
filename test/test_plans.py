"""旅行计划接口测试（生成 / 保存 / 列表 / 详情 / 删除）。

LLM 调用全部 mock，不产生真实 API 费用。
"""

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import utcnow
from app.models import TravelRecord, User
from app.services.llm import LLMError, LLMTimeout

from helpers import auth_headers, create_user


# ---------- 测试数据 ----------

def fake_plan(days: int = 2) -> dict:
    return {
        "title": "测试计划标题",
        "used_guide": False,
        "plan_content": {
            "overview": {"theme": "测试主题"},
            "long_distance_transport": {
                "outbound": {
                    "from": "上海", "to": "昆明",
                    "options": [{"way": "飞机", "duration": "3 小时", "cost": "¥900"}],
                    "recommendation": "推荐飞机", "marker": "fact",
                },
                "return": {
                    "from": "昆明", "to": "上海",
                    "options": [{"way": "飞机", "duration": "3 小时", "cost": "¥900"}],
                    "recommendation": "推荐飞机", "marker": "fact",
                },
                "intercity": [],
            },
            "daily": [
                {
                    "day": index + 1,
                    "blocks": [
                        {
                            "period": "morning",
                            "place": f"景点A{index + 1}",
                            "spot_tips": {
                                "reservation": "无需预约", "duration": "2 小时",
                                "best_time": "上午", "ticket": "免费", "gear": "运动鞋",
                                "markers": {"ticket": "fact"},
                            },
                            "transport": {
                                "options": [
                                    {"way": "地铁", "duration": "20 分钟", "cost": "¥3"},
                                    {"way": "打车", "duration": "10 分钟", "cost": "¥20"},
                                ],
                                "recommendation": "推荐地铁", "marker": "fact",
                            },
                            "nearby_food": {
                                "marker": "fact",
                                "items": [{"name": "某米线店", "desc": "招牌米线", "price": "¥30"}],
                            },
                            "meal": "当地早餐", "cost": 50, "note": "", "pitfall": None,
                        },
                        {
                            "period": "afternoon",
                            "place": f"景点B{index + 1}",
                            "spot_tips": {},
                            "transport": None,
                            "nearby_food": None,
                            "meal": "午餐", "cost": 80, "note": "", "pitfall": None,
                        },
                    ],
                    "alternatives": ["雨天改室内"],
                }
                for index in range(days)
            ],
            "accommodations": [
                {
                    "rank": 1, "area": "市中心", "name": "某连锁",
                    "level": "舒适型", "price": "¥300-400",
                    "reason": "交通方便", "marker": "fact",
                }
            ],
            "budget": {
                "items": [{"name": "交通", "amount": 800}, {"name": "住宿", "amount": 1000}],
                "total": 1800,
            },
            "notices": [{"text": "注意防晒", "marker": None}],
            "alternatives": ["可替换为博物馆"],
            "sources": [],
        },
    }


def fake_llm(messages, **kwargs):
    system = messages[0].get("content", "") if messages else ""
    if "文案编辑" in system:
        return json.dumps({"title": "AI生成标题", "summary": "AI生成摘要"}, ensure_ascii=False)
    return json.dumps(fake_plan(2), ensure_ascii=False)


def gen_payload(**overrides) -> dict:
    payload = {
        "departure": "上海",
        "destination": "昆明",
        "days": 2,
        "start_date": None,
        "budget_per_person": 3000,
        "people": 2,
        "interest_tags": ["自然风光"],
        "pace": "适中",
        "transport_pref": "公共交通为主",
        "hotel_pref": "舒适型",
        "special_needs": None,
        "guides": [],
    }
    payload.update(overrides)
    return payload


def save_payload(**overrides) -> dict:
    payload = {
        "departure": "上海",
        "destination": "昆明",
        "days": 2,
        "start_date": None,
        "budget_per_person": 3000,
        "people": 2,
        "interest_tags": ["自然风光"],
        "pace": "适中",
        "transport_pref": None,
        "hotel_pref": None,
        "special_needs": None,
        "used_guide": False,
        "guide_sources": [],
        "plan_content": fake_plan(2)["plan_content"],
    }
    payload.update(overrides)
    return payload


def add_record(db, user_id, title="已有计划", destination="昆明", minutes_ago=0):
    record = TravelRecord(
        user_id=user_id,
        title=title,
        summary="摘要",
        departure="上海",
        destination=destination,
        days=2,
        start_date=None,
        people=2,
        budget_per_person=3000,
        interest_tags=json.dumps(["自然风光"], ensure_ascii=False),
        pace="适中",
        transport_pref=None,
        hotel_pref=None,
        special_needs=None,
        used_guide=False,
        guide_sources=None,
        plan_content=json.dumps(fake_plan(2)["plan_content"], ensure_ascii=False),
        created_at=utcnow() - timedelta(minutes=minutes_ago),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------- 生成 ----------

def test_generate_success(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)

    resp = client.post("/api/plans/generate", headers=headers, json=gen_payload())
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["title"] == "测试计划标题"
    assert body["data"]["used_guide"] is False

    content = body["data"]["plan_content"]
    assert len(content["daily"]) == 2
    assert content["daily"][0]["blocks"][0]["place"] == "景点A1"
    assert content["long_distance_transport"]["outbound"]["from"] == "上海"
    assert len(content["accommodations"]) == 1
    assert content["budget"]["total"] == 1800


def test_generate_does_not_persist(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)

    client.post("/api/plans/generate", headers=headers, json=gen_payload())

    count = db.scalar(select(func.count()).select_from(TravelRecord))
    assert count == 0  # 生成不落库


@pytest.mark.parametrize("field, value, message", [
    ("departure", "", "请输入出发地"),
    ("destination", "", "请输入目的地"),
    ("days", 0, "出行天数需为 1-15 天"),
    ("days", 16, "出行天数需为 1-15 天"),
    ("budget_per_person", 0, "请输入人均预算（正整数）"),
    ("people", 0, "人数需为 1-20 人"),
    ("people", 21, "人数需为 1-20 人"),
])
def test_generate_validation(client, db, headers, monkeypatch, field, value, message):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)

    body = client.post(
        "/api/plans/generate", headers=headers, json=gen_payload(**{field: value})
    ).json()

    assert body["code"] == 400
    assert body["message"] == message


def test_generate_too_many_guides(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)
    guides = [{"type": "link", "content": f"https://example.com/{i}"} for i in range(4)]

    body = client.post("/api/plans/generate", headers=headers, json=gen_payload(guides=guides)).json()

    assert body["code"] == 400
    assert body["message"] == "参考攻略最多 3 条，每条文本不超过 500 字"


def test_generate_guide_text_too_long(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)
    guides = [{"type": "text", "content": "攻略" * 300}]

    body = client.post("/api/plans/generate", headers=headers, json=gen_payload(guides=guides)).json()

    assert body["code"] == 400
    assert body["message"] == "参考攻略最多 3 条，每条文本不超过 500 字"


def test_generate_timeout_returns_504(client, db, headers, monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise LLMTimeout()

    monkeypatch.setattr("app.api.plans.chat_completion", raise_timeout)

    resp = client.post("/api/plans/generate", headers=headers, json=gen_payload())
    body = resp.json()

    assert resp.status_code == 504
    assert body["message"] == "生成超时，请重试"


def test_generate_llm_error_returns_500(client, db, headers, monkeypatch):
    def raise_error(*args, **kwargs):
        raise LLMError()

    monkeypatch.setattr("app.api.plans.chat_completion", raise_error)

    resp = client.post("/api/plans/generate", headers=headers, json=gen_payload())
    body = resp.json()

    assert resp.status_code == 500
    assert body["message"] == "生成失败，请重试"


def test_generate_invalid_json_returns_500(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", lambda *a, **k: "这不是 JSON")

    body = client.post("/api/plans/generate", headers=headers, json=gen_payload()).json()

    assert body["code"] == 500
    assert body["message"] == "生成失败，请重试"


def test_generate_uses_text_guide(client, db, headers, monkeypatch):
    calls = {}

    def capture(messages, **kwargs):
        calls["user"] = messages[-1]["content"]
        data = fake_plan(2)
        data["used_guide"] = True
        return json.dumps(data, ensure_ascii=False)

    monkeypatch.setattr("app.api.plans.chat_completion", capture)

    body = client.post(
        "/api/plans/generate",
        headers=headers,
        json=gen_payload(guides=[{"type": "text", "content": "翠湖旁边的文山荷鲜居米线很好吃，人均20。"}]),
    ).json()

    assert body["code"] == 0
    assert body["data"]["used_guide"] is True
    assert "文山荷鲜居" in calls["user"]  # 正文进入提示词
    assert body["data"]["plan_content"]["sources"]  # 补充了来源


def test_generate_filters_ad_guide(client, db, headers, monkeypatch):
    calls = {}
    data = fake_plan(2)
    data["used_guide"] = True  # 即使模型声称用了

    def capture(messages, **kwargs):
        calls["user"] = messages[-1]["content"]
        return json.dumps(data, ensure_ascii=False)

    monkeypatch.setattr("app.api.plans.chat_completion", capture)

    body = client.post(
        "/api/plans/generate",
        headers=headers,
        json=gen_payload(guides=[{"type": "text", "content": "加微信 abcdef 领优惠券，限时最低价"}]),
    ).json()

    assert body["code"] == 0
    assert body["data"]["used_guide"] is False  # 全部被过滤 → 静默降级


def test_generate_appends_link_sources(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)

    body = client.post(
        "/api/plans/generate",
        headers=headers,
        json=gen_payload(guides=[{"type": "link", "content": "https://example.com/post"}]),
    ).json()

    sources = body["data"]["plan_content"]["sources"]
    assert any(source["type"] == "link" and source["url"] == "https://example.com/post" for source in sources)


def test_generate_requires_login(client):
    resp = client.post("/api/plans/generate", json=gen_payload())

    assert resp.status_code == 401
    assert resp.json()["code"] == 401


# ---------- 保存 ----------

def test_save_success(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)

    resp = client.post("/api/plans", headers=headers, json=save_payload())
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["title"] == "AI生成标题"
    assert body["data"]["summary"] == "AI生成摘要"
    assert body["data"]["id"] > 0


def test_save_is_append_only(client, db, headers, monkeypatch):
    monkeypatch.setattr("app.api.plans.chat_completion", fake_llm)

    first = client.post("/api/plans", headers=headers, json=save_payload()).json()
    second = client.post("/api/plans", headers=headers, json=save_payload()).json()

    assert first["data"]["id"] != second["data"]["id"]
    count = db.query(TravelRecord).count()
    assert count == 2  # 只增不覆盖


def test_save_falls_back_when_title_llm_fails(client, db, headers, monkeypatch):
    def raise_error(*args, **kwargs):
        raise LLMError()

    monkeypatch.setattr("app.api.plans.chat_completion", raise_error)

    body = client.post("/api/plans", headers=headers, json=save_payload()).json()

    assert body["code"] == 0  # LLM 失败不阻塞保存
    assert body["data"]["title"] == "昆明 2 日游"  # 规则文案降级


def test_save_requires_departure(client, db, headers):
    body = client.post("/api/plans", headers=headers, json=save_payload(departure="")).json()

    assert body["code"] == 400
    assert body["message"] == "请输入出发地"


def test_save_requires_login(client):
    resp = client.post("/api/plans", json=save_payload())

    assert resp.status_code == 401


# ---------- 列表 ----------

def test_list_is_owned_and_sorted(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    other = create_user(db, username="other01", email="other01@example.com")

    add_record(db, user.id, title="较早", minutes_ago=10)
    add_record(db, user.id, title="最新", minutes_ago=0)
    add_record(db, other.id, title="他人计划")

    body = client.get("/api/plans", headers=headers).json()

    assert body["code"] == 0
    assert body["data"]["total"] == 2
    titles = [item["title"] for item in body["data"]["list"]]
    assert titles == ["最新", "较早"]  # 倒序且不含他人数据


def test_list_pagination(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    for index in range(12):
        add_record(db, user.id, title=f"计划{index:02d}", minutes_ago=index)

    page1 = client.get("/api/plans?page=1", headers=headers).json()["data"]
    page2 = client.get("/api/plans?page=2", headers=headers).json()["data"]

    assert page1["total"] == 12
    assert len(page1["list"]) == 10
    assert len(page2["list"]) == 2
    assert page1["page_size"] == 10


def test_list_search_by_title_and_destination(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    add_record(db, user.id, title="昆明五日游", destination="昆明")
    add_record(db, user.id, title="成都美食", destination="成都")

    by_title = client.get("/api/plans?keyword=五日", headers=headers).json()["data"]
    by_dest = client.get("/api/plans?keyword=成都", headers=headers).json()["data"]
    no_hit = client.get("/api/plans?keyword=西安", headers=headers).json()["data"]

    assert by_title["total"] == 1
    assert by_dest["total"] == 1
    assert no_hit["total"] == 0


# ---------- 详情 / 删除 ----------

def test_detail_success(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    record = add_record(db, user.id)

    body = client.get(f"/api/plans/{record.id}", headers=headers).json()

    assert body["code"] == 0
    assert body["data"]["id"] == record.id
    assert body["data"]["departure"] == "上海"
    assert body["data"]["plan_content"]["daily"]


def test_detail_forbidden_for_other_user(client, db, headers):
    other = create_user(db, username="other01", email="other01@example.com")
    record = add_record(db, other.id)

    resp = client.get(f"/api/plans/{record.id}", headers=headers)
    body = resp.json()

    assert resp.status_code == 403
    assert body["message"] == "无权访问"


def test_detail_not_found(client, db, headers):
    body = client.get("/api/plans/99999", headers=headers).json()

    assert body["code"] == 404
    assert body["message"] == "计划不存在"


def test_delete_success(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    record = add_record(db, user.id)
    record_id = record.id

    body = client.delete(f"/api/plans/{record_id}", headers=headers).json()
    assert body["code"] == 0

    db.expire_all()  # 清掉会话缓存后再查，确认物理删除
    assert db.get(TravelRecord, record_id) is None


def test_delete_forbidden_for_other_user(client, db, headers):
    other = create_user(db, username="other01", email="other01@example.com")
    record = add_record(db, other.id)

    body = client.delete(f"/api/plans/{record.id}", headers=headers).json()

    assert body["code"] == 403
    assert db.get(TravelRecord, record.id) is not None  # 未被删除


def test_requires_login(client):
    assert client.get("/api/plans").status_code == 401
    assert client.get("/api/plans/1").status_code == 401
    assert client.delete("/api/plans/1").status_code == 401
