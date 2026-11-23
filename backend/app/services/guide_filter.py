"""参考攻略清洗：剔除广告、联系方式等无效内容。

依据：生成 PRD §3.8（规则层过滤 + 后续 LLM 分类）
MVP 只做规则层；全部无效时由上层静默降级。
"""

import re

# 广告/营销特征（命中整行剔除）
AD_LINE_PATTERN = re.compile(
    r"(微信号|微信|加微|加我|vx|VX|扫码|优惠券|限时|返现|代理|批发|最低价|包邮|私聊|带图咨询)"
)
# 手机号
PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
# 链接外链（攻略正文里夹带的营销外链）
URL_PATTERN = re.compile(r"https?://\S+")

MIN_VALID_LENGTH = 20


def clean_guide_text(text: str) -> str:
    """按行剔除广告、联系方式与营销外链，返回清洗后的正文。"""
    kept_lines = []
    for line in text.splitlines():
        if AD_LINE_PATTERN.search(line):
            continue
        if PHONE_PATTERN.search(line):
            continue
        line = URL_PATTERN.sub("", line).strip()
        if line:
            kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def has_valid_content(text: str) -> bool:
    """清洗后是否仍有足够内容参与生成。"""
    return len(text) >= MIN_VALID_LENGTH
