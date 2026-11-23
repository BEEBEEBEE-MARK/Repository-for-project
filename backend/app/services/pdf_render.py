"""旅行计划 PDF 渲染（纯数据，零 LLM）。

依据《旅行计划PDF导出-PRD.md》，并按项目要求调整：**不调用大模型**。
- 交通信息、住宿推荐直接复用生成时已落库的数据
- 行前准备清单按规则生成
- 景点速查表由每日安排中的景点提示重组
版式：A4 纵向，reportlab platypus。
"""

import io
import json
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/

FONT_NAME = "TravelCN"

# 项目自带字体优先，其次系统字体（Linux 部署需放置字体文件）
FONT_CANDIDATES = [
    (BASE_DIR / "app" / "assets" / "fonts" / "NotoSansSC-Regular.otf", None),
    (BASE_DIR / "app" / "assets" / "fonts" / "simhei.ttf", None),
    (Path("C:/Windows/Fonts/simhei.ttf"), None),
    (Path("C:/Windows/Fonts/msyh.ttc"), 0),
    (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), 0),
    (Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"), 0),
]

_font_ready = False

PERIOD_LABELS = {"morning": "上午", "afternoon": "下午", "evening": "晚间"}


def ensure_font() -> str:
    """注册中文字体，返回字体名。找不到时抛 RuntimeError。"""
    global _font_ready
    if _font_ready:
        return FONT_NAME

    for path, subfont_index in FONT_CANDIDATES:
        if not path.exists():
            continue
        try:
            if subfont_index is None:
                pdfmetrics.registerFont(TTFont(FONT_NAME, str(path)))
            else:
                pdfmetrics.registerFont(TTFont(FONT_NAME, str(path), subfontIndex=subfont_index))
            _font_ready = True
            return FONT_NAME
        except Exception:
            continue

    raise RuntimeError("未找到可用的中文字体，请将字体文件放入 backend/app/assets/fonts/")


def _styles() -> dict:
    ensure_font()
    getSampleStyleSheet()  # 保持 reportlab 默认样式可用

    def make(name, size, leading, **kwargs):
        return ParagraphStyle(name, fontName=FONT_NAME, fontSize=size, leading=leading, **kwargs)

    return {
        "cover_title": make("cover_title", 24, 34, alignment=TA_CENTER, textColor=colors.HexColor("#17806F")),
        "cover_sub": make("cover_sub", 12, 20, alignment=TA_CENTER, textColor=colors.HexColor("#556B67")),
        "h2": make("h2", 15, 22, spaceBefore=14, spaceAfter=8, textColor=colors.HexColor("#17806F")),
        "h3": make("h3", 12, 18, spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#20312E")),
        "body": make("body", 10, 16, textColor=colors.HexColor("#20312E"), wordWrap="CJK"),
        "meta": make("meta", 9, 14, textColor=colors.HexColor("#556B67"), wordWrap="CJK"),
        "small": make("small", 8.5, 12, textColor=colors.HexColor("#8AA09B")),
    }


def _p(text, style) -> Paragraph:
    raw = str(text if text is not None else "")
    # 中文字体（simhei/雅黑）不含半角 ¥（U+00A5），统一替换为全角 ￥（U+FFE5），避免渲染为空白
    raw = raw.replace("¥", "￥")
    return Paragraph(escape(raw), style)


def _cell(text, style) -> Paragraph:
    return _p(text, style)


def _table(rows, widths, styles, header=True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 13),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#20312E")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F4F1")) if header else ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2EBE8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_filename(record) -> str:
    """文件名：目的地+天数日游_导出日期.pdf，目的地仅保留中英文与数字。"""
    name = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", record.destination or "")
    name = name or "旅行计划"
    return f"{name}{record.days}日游_{date.today():%Y%m%d}.pdf"


# ---------- 各章节 ----------

def _cover(record, content, styles) -> list:
    theme = (content.get("overview") or {}).get("theme") or ""
    story = [Spacer(1, 50 * mm)]
    story.append(_p(record.title or "旅行计划", styles["cover_title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(_p(f"{record.departure or '—'} → {record.destination}", styles["cover_sub"]))
    story.append(Spacer(1, 8 * mm))

    meta = []
    if record.start_date:
        meta.append(f"出发日期：{record.start_date.isoformat()}")
    meta.extend([
        f"出行天数：{record.days} 天",
        f"出行人数：{record.people} 人",
        f"人均预算：{record.budget_per_person:,} 元",
    ])
    for line in meta:
        story.append(_p(line, styles["cover_sub"]))

    if theme:
        story.append(Spacer(1, 14 * mm))
        story.append(_p("主题建议", styles["h3"]))
        story.append(_p(theme, styles["body"]))

    story.append(Spacer(1, 24 * mm))
    story.append(_p(f"导出日期：{date.today().isoformat()}　·　旅梦规划助手", styles["small"]))
    story.append(PageBreak())
    return story


def _overview(record, content, styles) -> list:
    rows = [
        [_cell("项目", styles["body"]), _cell("内容", styles["body"])],
        [_cell("出发地", styles["body"]), _cell(record.departure or "—", styles["body"])],
        [_cell("目的地", styles["body"]), _cell(record.destination, styles["body"])],
        [_cell("天数 / 人数", styles["body"]), _cell(f"{record.days} 天 / {record.people} 人", styles["body"])],
        [_cell("人均预算", styles["body"]), _cell(f"{record.budget_per_person:,} 元", styles["body"])],
    ]
    if record.interest_tags:
        rows.append([_cell("兴趣偏好", styles["body"]), _cell(record.interest_tags.replace('"', "").strip("[]"), styles["body"])])

    story = [_p("一、行程总览", styles["h2"]), _table(rows, [35 * mm, 139 * mm], styles)]
    theme = (content.get("overview") or {}).get("theme")
    if theme:
        story.append(Spacer(1, 5 * mm))
        story.append(_p(f"主题：{theme}", styles["body"]))
    return story


def _transport(content, styles) -> list:
    data = content.get("long_distance_transport") or {}
    rows = [[
        _cell("段", styles["body"]), _cell("路线", styles["body"]),
        _cell("可选方式（时长 / 费用）", styles["body"]), _cell("推荐", styles["body"]),
    ]]

    def add(tag, segment):
        if not segment:
            return
        ways = "；".join(
            f"{o.get('way', '')}（{o.get('duration', '')} / {o.get('cost', '')}）"
            for o in (segment.get("options") or [])
        )
        rows.append([
            _cell(tag, styles["body"]),
            _cell(f"{segment.get('from', '')} → {segment.get('to', '')}", styles["body"]),
            _cell(ways, styles["body"]),
            _cell(segment.get("recommendation", ""), styles["body"]),
        ])

    add("去程", data.get("outbound"))
    add("返程", data.get("return"))
    for index, segment in enumerate(data.get("intercity") or [], start=1):
        add(f"城际{index}", segment)

    if len(rows) == 1:
        return []
    return [_p("二、交通信息", styles["h2"]), _table(rows, [18 * mm, 48 * mm, 72 * mm, 36 * mm], styles)]


def _accommodations(content, styles) -> list:
    items = content.get("accommodations") or []
    if not items:
        return []

    rows = [[
        _cell("序", styles["body"]), _cell("区域", styles["body"]),
        _cell("酒店 / 类型", styles["body"]), _cell("档次", styles["body"]),
        _cell("价格", styles["body"]), _cell("推荐理由", styles["body"]),
    ]]
    for item in items:
        rows.append([
            _cell(item.get("rank", ""), styles["body"]),
            _cell(item.get("area", ""), styles["body"]),
            _cell(item.get("name", ""), styles["body"]),
            _cell(item.get("level", ""), styles["body"]),
            _cell(item.get("price", ""), styles["body"]),
            _cell(item.get("reason", ""), styles["body"]),
        ])

    return [_p("三、住宿推荐", styles["h2"]), _table(rows, [10 * mm, 30 * mm, 38 * mm, 18 * mm, 25 * mm, 53 * mm], styles)]


def _daily(content, styles) -> list:
    story = [_p("四、每日安排", styles["h2"])]
    for day in content.get("daily") or []:
        header = f"第 {day.get('day', '')} 天"
        if day.get("date"):
            header += f"（{day['date']}）"
        story.append(_p(header, styles["h3"]))

        for block in day.get("blocks") or []:
            period = PERIOD_LABELS.get(block.get("period"), "")
            story.append(_p(f"{period}　{block.get('place', '')}", styles["body"]))

            tips = block.get("spot_tips") or {}
            tip_parts = []
            for label, key in [("预约", "reservation"), ("时长", "duration"),
                               ("最佳时段", "best_time"), ("门票", "ticket"), ("装备", "gear")]:
                if tips.get(key):
                    tip_parts.append(f"{label}：{tips[key]}")
            if tip_parts:
                story.append(_p("景点提示：" + "；".join(tip_parts), styles["meta"]))

            transport = block.get("transport")
            if transport:
                ways = "；".join(
                    f"{o.get('way', '')} {o.get('duration', '')}/{o.get('cost', '')}"
                    for o in (transport.get("options") or [])
                )
                rec = transport.get("recommendation") or ""
                story.append(_p(f"交通：{ways}。{rec}", styles["meta"]))

            food = block.get("nearby_food")
            if food and food.get("items"):
                names = "；".join(
                    f"{item.get('name', '')}（{item.get('price', '')}）"
                    for item in food["items"]
                )
                story.append(_p(f"附近美食：{names}", styles["meta"]))

            extras = []
            if block.get("meal"):
                extras.append(f"餐饮：{block['meal']}")
            if block.get("cost"):
                extras.append(f"预算：{block['cost']} 元")
            if extras:
                story.append(_p("　".join(extras), styles["meta"]))

            if block.get("note"):
                story.append(_p(f"备注：{block['note']}", styles["meta"]))
            if block.get("pitfall"):
                story.append(_p(f"提醒：{block['pitfall']}（来自旅行者反馈）", styles["meta"]))

            story.append(Spacer(1, 2 * mm))

        if day.get("alternatives"):
            story.append(_p("当日备选：" + "；".join(day["alternatives"]), styles["meta"]))
        story.append(Spacer(1, 3 * mm))

    return story


def _spot_table(content, styles) -> list:
    """景点速查表：从每日安排的景点提示重组，不调用模型。"""
    spots = {}
    for day in content.get("daily") or []:
        for block in day.get("blocks") or []:
            place = (block.get("place") or "").strip()
            if not place or place in spots:
                continue
            tips = block.get("spot_tips") or {}
            spots[place] = {
                "duration": tips.get("duration", ""),
                "ticket": tips.get("ticket", ""),
                "best_time": tips.get("best_time", ""),
                "reservation": tips.get("reservation", ""),
            }

    if not spots:
        return []

    rows = [[
        _cell("景点 / 活动", styles["body"]), _cell("建议时长", styles["body"]),
        _cell("门票", styles["body"]), _cell("最佳时段", styles["body"]),
        _cell("预约", styles["body"]),
    ]]
    for place, tip in spots.items():
        rows.append([
            _cell(place, styles["body"]), _cell(tip["duration"] or "—", styles["body"]),
            _cell(tip["ticket"] or "—", styles["body"]), _cell(tip["best_time"] or "—", styles["body"]),
            _cell(tip["reservation"] or "—", styles["body"]),
        ])

    return [
        _p("五、景点速查表", styles["h2"]),
        _p("信息标注为估算，出行前请核实。", styles["small"]),
        Spacer(1, 2 * mm),
        _table(rows, [55 * mm, 25 * mm, 38 * mm, 30 * mm, 26 * mm], styles),
    ]


def _budget(content, styles) -> list:
    budget = content.get("budget") or {}
    items = budget.get("items") or []
    if not items:
        return []

    rows = [[_cell("费用项", styles["body"]), _cell("金额（人均）", styles["body"])]]
    for item in items:
        rows.append([
            _cell(item.get("name", ""), styles["body"]),
            _cell(f"{item.get('amount', 0):,} 元", styles["body"]),
        ])
    rows.append([_cell("合计", styles["body"]), _cell(f"{budget.get('total', 0):,} 元", styles["body"])])

    return [_p("六、费用参考", styles["h2"]), _table(rows, [87 * mm, 87 * mm], styles)]


def _bullets(title, items, styles) -> list:
    if not items:
        return []
    story = [_p(title, styles["h2"])]
    for index, text in enumerate(items, start=1):
        if isinstance(text, dict):
            text = text.get("text", "")
        story.append(_p(f"{index}. {text}", styles["body"]))
    return story


def _packing_list(record, styles) -> list:
    """行前准备清单：规则生成，不调用模型。"""
    days = max(1, record.days)
    clothes = max(2, (days + 1) // 2)
    extra = ""
    month = record.start_date.month if record.start_date else None
    if month in (6, 7, 8):
        extra = "；夏季注意防晒、遮阳与补水"
    elif month in (12, 1, 2):
        extra = "；冬季注意保暖衣物与防滑鞋"

    sections = [
        ("证件与财务", "身份证、银行卡、少量现金、行程单与酒店预订单"),
        ("衣物装备", f"换洗衣物约 {clothes} 套、舒适步行鞋、薄外套、雨具{extra}"),
        ("洗护药品", "常用药（感冒 / 肠胃 / 创可贴）、防晒霜、洗漱用品"),
        ("电子设备", "手机、充电器、充电宝、耳机、相机（如需要）"),
    ]

    story = [_p("七、行前准备清单", styles["h2"])]
    for title, text in sections:
        story.append(_p(f"{title}：{text}", styles["body"]))
    return story


def _disclaimer(used_guide, styles) -> list:
    text = "行程与价格均为 AI 估算，信息非实时，出行前请自行核实。"
    if used_guide:
        text += "参考内容来自公开分享，可能过时或夸大，仅供灵感参考。"
    return [Spacer(1, 6 * mm), _p("免责声明", styles["h2"]), _p(text, styles["small"])]


def _on_page(canvas, doc, styles):
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#8AA09B"))
    canvas.drawCentredString(A4[0] / 2, 12 * mm, f"第 {doc.page} 页 · 旅梦规划助手")
    canvas.restoreState()


def render_plan_pdf(record) -> bytes:
    """把一条已保存计划渲染为 PDF 字节流。"""
    styles = _styles()
    content = json.loads(record.plan_content or "{}")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=record.title or "旅行计划",
        author="旅梦规划助手",
    )

    story = []
    story += _cover(record, content, styles)
    story += _overview(record, content, styles)
    story += _transport(content, styles)
    story += _accommodations(content, styles)
    story += _daily(content, styles)
    story += _spot_table(content, styles)
    story += _budget(content, styles)
    story += _bullets("八、注意事项", content.get("notices") or [], styles)
    story += _bullets("九、备选建议", content.get("alternatives") or [], styles)
    story += _packing_list(record, styles)
    story += _disclaimer(record.used_guide, styles)

    doc.build(
        story,
        onFirstPage=lambda canvas, doc_: _on_page(canvas, doc_, styles),
        onLaterPages=lambda canvas, doc_: _on_page(canvas, doc_, styles),
    )
    return buffer.getvalue()
