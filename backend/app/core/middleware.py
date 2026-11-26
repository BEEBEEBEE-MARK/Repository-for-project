"""安全中间件：请求体上限、接口限流、安全响应头。

均为纯 ASGI 实现，避免 BaseHTTPMiddleware 缓冲整个响应体带来的额外内存开销。
"""

import json

from . import limits

# 与前端现状兼容：页面使用内联脚本与内联 style 属性，故 script/style 需 'unsafe-inline'
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
    (b"content-security-policy", CSP.encode("utf-8")),
]

# 需要从响应中移除的头（避免暴露技术栈版本）
_HIDDEN_HEADERS = {b"server", b"x-powered-by"}

BODY_TOO_LARGE_MESSAGE = "请求内容过大，请减小提交内容"
RATE_LIMIT_MESSAGE = "操作过于频繁，请稍后再试"


def _json_body(code: int, message: str) -> bytes:
    return json.dumps(
        {"code": code, "message": message, "data": None}, ensure_ascii=False
    ).encode("utf-8")


async def _send_json(send, status: int, message: str, extra_headers=None) -> None:
    body = _json_body(status, message)
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    """读请求体时超限（用于覆盖不带 Content-Length 的分块请求）。"""


class BodySizeLimitMiddleware:
    """限制请求体大小：先看 Content-Length，再兜底按实际读取量累计。"""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {key.lower(): value for key, value in scope["headers"]}
        raw_length = headers.get(b"content-length")
        if raw_length and raw_length.isdigit() and int(raw_length) > self.max_bytes:
            return await _send_json(send, 413, BODY_TOO_LARGE_MESSAGE)

        received = 0
        response_started = False

        async def watched_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, watched_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_json(send, 413, BODY_TOO_LARGE_MESSAGE)


class RateLimitMiddleware:
    """按客户端 IP + 接口路径限流（防高频请求 / 热点攻击）。"""

    def __init__(self, app, registry: limits.RateLimiterRegistry):
        self.app = app
        self.registry = registry

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        path = scope.get("path", "")
        allowed, retry_after = self.registry.check(path, scope.get("method", "GET"), client_ip)
        if not allowed:
            return await _send_json(
                send, 429, RATE_LIMIT_MESSAGE,
                extra_headers=[(b"retry-after", str(retry_after).encode("ascii"))],
            )

        return await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """为所有响应追加安全头，并移除暴露技术栈的 Server 头。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in _HIDDEN_HEADERS
                ]
                existing = {key.lower() for key, _ in headers}
                for key, value in SECURITY_HEADERS:
                    if key not in existing:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        return await self.app(scope, receive, send_with_headers)
