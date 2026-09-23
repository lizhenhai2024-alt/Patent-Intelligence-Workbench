"""Shared helpers for OpenAI-compatible Chat Completions endpoints."""

from __future__ import annotations

from urllib.parse import urlparse

HTTP_HINTS = {
    400: "请求被拒绝：请检查模型名称是否正确、该模型是否支持工具调用",
    401: "API Key 无效或已失效：请确认填的是这家厂商的 Key",
    402: "账户余额不足：请到该厂商控制台充值",
    403: "没有权限：该 Key 无权使用此模型或接口",
    404: "找不到接口或模型：请检查接口地址和模型名称",
    429: "请求太频繁或额度已用完：请稍后再试",
}


def http_hint(status: int) -> str:
    if status in HTTP_HINTS:
        return HTTP_HINTS[status]
    if status >= 500:
        return "模型服务商内部错误：请稍后再试"
    return "模型服务拒绝了请求"


def chat_completions_url(endpoint: str) -> str:
    """Accept either a base URL (…/v1) or the full …/chat/completions URL."""
    url = endpoint.strip().rstrip("/")
    if urlparse(url).path.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"
