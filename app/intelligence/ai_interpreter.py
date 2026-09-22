"""Explicit, user-controlled OpenAI-compatible report interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.intelligence.ai_packet import build_ai_prompt
from app.intelligence.analysis import AnalysisReport


class AIInterpretationError(RuntimeError):
    """A configured interpretation service could not produce usable text."""


@dataclass(frozen=True, slots=True)
class AIInterpretationSettings:
    endpoint: str
    model: str
    api_key: str
    consent: bool = False

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        local_http = parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or (parsed.scheme == "http" and not local_http)
        ):
            raise ValueError("AI Endpoint 必须使用 HTTPS；本机 localhost 可使用 HTTP")
        if not self.model.strip():
            raise ValueError("请填写 AI 模型名称")
        if not self.api_key.strip():
            raise ValueError("请填写 API Key；该密钥仅保留在当前窗口内")
        if not self.consent:
            raise ValueError("请确认后再发送当前报告的证据包给 AI 服务")


class OpenAICompatibleInterpreter:
    """A minimal boundary: only an already-rendered report may leave the app."""

    def __init__(self, settings: AIInterpretationSettings) -> None:
        self.settings = settings

    def interpret(self, report: AnalysisReport) -> str:
        payload = {
            "model": self.settings.model.strip(),
            "messages": [{"role": "user", "content": build_ai_prompt(report)}],
            "temperature": 0.2,
        }
        try:
            response = httpx.post(
                self.settings.endpoint,
                headers={"Authorization": f"Bearer {self.settings.api_key.strip()}"},
                json=payload,
                timeout=45.0,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIInterpretationError(f"AI 解读失败：{exc}") from exc
        if isinstance(content, list):
            content = "\n".join(item.get("text", "") for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise AIInterpretationError("AI 服务未返回可显示的解读文本")
        return content.strip()
