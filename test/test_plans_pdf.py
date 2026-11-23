"""PDF 导出测试（纯数据渲染，不调用大模型）。"""

import json
from urllib.parse import quote

from app.core.security import utcnow
from app.models import TravelRecord, User
from app.services.pdf_render import build_filename

from helpers import auth_headers, create_user


def _content(days: int = 2) -> dict:
    return {
        "overview": {"theme": "测试主题"},
        "long_distance_transport": {
            "outbound": {
                "from": "上海", "to": "昆明",
                "options": [{"way": "飞机", "duration": "3 小时", "cost": "¥900"}],
                "recommendation": "推荐飞机", "marker": "fact",
            },
            "return": None,
            "intercity": [],
        },
        "daily": [
            {
                "day": index + 1,
                "date": None,
                "blocks": [
                    {
                        "period": "morning",
                        "place": f"景点{index + 1}",
                        "spot_tips": {
                            "reservation": "无需预约", "duration": "2 小时",
                            "best_time": "上午", "ticket": "免费", "gear": "运动鞋",
                        },
                        "transport": {
                            "options": [{"way": "地铁", "duration": "20 分钟", "cost": "¥3"}],
                            "recommendation": "推荐地铁", "marker": "fact",
                        },
                        "nearby_food": {
                            "marker": "fact",
                            "items": [{"name": "某米线店", "desc": "招牌米线", "price": "¥30"}],
                        },
                        "meal": "当地早餐", "cost": 50, "note": "", "pitfall": None,
                    }
                ],
                "alternatives": ["雨天改室内"],
            }
            for index in range(days)
        ],
        "accommodations": [
            {"rank": 1, "area": "市中心", "name": "某连锁", "level": "舒适型",
             "price": "¥300-400", "reason": "交通方便", "marker": "fact"}
        ],
        "budget": {"items": [{"name": "交通", "amount": 800}], "total": 800},
        "notices": [{"text": "注意防晒", "marker": None}],
        "alternatives": ["可替换为博物馆"],
        "sources": [],
    }


def add_record(db, user_id, destination="昆明", used_guide=False) -> TravelRecord:
    record = TravelRecord(
        user_id=user_id,
        title="测试计划",
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
        used_guide=used_guide,
        guide_sources=None,
        plan_content=json.dumps(_content(2), ensure_ascii=False),
        created_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_export_pdf_success(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    record = add_record(db, user.id)

    resp = client.get(f"/api/plans/{record.id}/pdf", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"  # 合法 PDF 头
    assert len(resp.content) > 1000  # 内容非空

    disposition = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert quote("昆明2日游") in disposition


def test_export_pdf_with_guide_disclaimer(client, db, headers):
    user = db.query(User).filter(User.username == "tester01").one()
    record = add_record(db, user.id, used_guide=True)

    resp = client.get(f"/api/plans/{record.id}/pdf", headers=headers)

    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"


def test_export_pdf_requires_login(client, db):
    user = create_user(db)
    record = add_record(db, user.id)

    resp = client.get(f"/api/plans/{record.id}/pdf")

    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_export_pdf_forbidden_for_other_user(client, db, headers):
    other = create_user(db, username="other01", email="other01@example.com")
    record = add_record(db, other.id)

    resp = client.get(f"/api/plans/{record.id}/pdf", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["message"] == "无权访问"


def test_export_pdf_not_found(client, db, headers):
    resp = client.get("/api/plans/999999/pdf", headers=headers)

    assert resp.status_code == 404
    assert resp.json()["message"] == "计划不存在"


def test_export_pdf_empty_content_still_works(client, db, headers):
    """内容字段缺失时应容错，不能 500。"""
    user = db.query(User).filter(User.username == "tester01").one()
    record = add_record(db, user.id)
    record.plan_content = json.dumps({}, ensure_ascii=False)
    db.commit()

    resp = client.get(f"/api/plans/{record.id}/pdf", headers=headers)

    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"


def test_build_filename_sanitizes_destination():
    class FakeRecord:
        destination = "昆明/大理?★"
        days = 3

    assert build_filename(FakeRecord()).startswith("昆明大理3日游_")
