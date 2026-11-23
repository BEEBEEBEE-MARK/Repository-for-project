"""DeepSeek 调用封装（Anthropic 兼容端点）。

- 端点：{DEEPSEEK_BASE_URL}/v1/messages（默认 https://api.deepseek.com/anthropic）
- 模型：deepseek-flash（推理模型，响应含 thinking 块，只提取 text 块）
- system 需独立字段，不能放在 messages 中
- Anthropic 端点没有 response_format，JSON 结构由提示词约束 + 上层解析兜底
"""

import httpx

from ..core.config import settings


class LLMError(Exception):
    """LLM 调用失败（网络、非 200、响应格式异常）。"""


class LLMTimeout(LLMError):
    """LLM 调用超时。"""


def chat_completion(
    messages: list[dict],
    *,
    timeout: float = 110.0,
    max_tokens: int = 16000,
    temperature: float = 0.7,
    json_mode: bool = True,  # 兼容旧调用方；Anthropic 端点无此参数，靠提示词约束
) -> str:
    """同步调用 LLM，返回模型输出的纯文本。"""
    if not settings.deepseek_api_key:
        raise LLMError("未配置 DEEPSEEK_API_KEY")

    system_parts: list[str] = []
    chat_messages: list[dict] = []
    for message in messages:
        if message.get("role") == "system":
            system_parts.append(str(message.get("content") or ""))
        else:
            chat_messages.append({
                "role": message.get("role", "user"),
                "content": message.get("content", ""),
            })

    payload = {
        "model": settings.deepseek_model,
        "max_tokens": max_tokens,
        "messages": chat_messages,
        "temperature": temperature,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    # 推理模型默认关闭思考：输出为结构化 JSON，无需推理链，且能显著降低耗时
    if settings.deepseek_disable_thinking:
        payload["thinking"] = {"type": "disabled"}

    url = settings.deepseek_base_url.rstrip("/") + "/v1/messages"

    try:
        response = httpx.post(
            url,
            headers={
                "x-api-key": settings.deepseek_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise LLMTimeout("LLM 调用超时") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM 请求失败: {exc}") from exc

    if response.status_code != 200:
        raise LLMError(f"LLM 返回状态码 {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError("LLM 响应格式异常") from exc

    blocks = data.get("content") or []
    texts = [
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    content = "".join(texts).strip()

    if not content:
        raise LLMError("LLM 未返回文本内容")

    return content
