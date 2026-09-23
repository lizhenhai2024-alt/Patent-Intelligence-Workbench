"""Bounded tool-calling loop for in-app agents (Agent track M2).

Code, not the model or the definition file, enforces the tool whitelist, the
step limit, human checkpoints and the evidence check.
"""

from __future__ import annotations

import inspect
import json
import threading
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx

from app.agent_tools.tools import TOOL_DESCRIPTIONS, LibraryTools, ToolError
from app.agents.definition import AgentDefinition
from app.agents.model_profiles import ModelProfile
from app.agents.receipts import EXEMPT_HEADING, ReceiptCheck, check_answer
from app.core.openai_compat import http_hint

GUARD_PROMPT = "\n".join(
    (
        "你是悬架/减振器研发工程师的专利情报助手，只能使用提供的只读工具查询用户的本地专利库。",
        "必须遵守（由程序检查，违反的行会被标红）：",
        "1. 每一条事实或结论所在的行，都要用方括号引用本次工具返回过的公开号，"
        "例如 [CN120100850A]；多个公开号用逗号分隔。",
        "2. 只引用工具返回过的公开号，不要凭记忆写公开号或专利事实。",
        "3. 不给出新颖性、创造性、侵权、FTO 或任何概率性结论；这些判断属于人工。",
        f"4. 结果只覆盖本地库。覆盖不足、未读全文、需要复核的内容，写在“## {EXEMPT_HEADING}”一节。",
        "5. 用中文回答。",
    )
)
SEARCH_TERMS_TOOL = "propose_search_terms"
STEP_LIMIT_PROMPT = (
    "已达到步数上限。请不要再调用工具，只基于已获得的工具结果给出最终回答，"
    f"并在“{EXEMPT_HEADING}”中说明结果不完整。"
)


class AgentRunError(RuntimeError):
    """The model service failed; a partial run log is still written."""


@dataclass(frozen=True, slots=True)
class CheckpointDecision:
    approved: bool
    payload: str = ""


@dataclass(slots=True)
class AgentResult:
    status: str  # completed | step_limit | cancelled | error
    final_text: str
    check: ReceiptCheck | None
    steps: int
    receipts: tuple[str, ...]
    log_path: Path | None
    error: str = ""
    log: dict = field(default_factory=dict)


CheckpointHandler = Callable[[str, str], CheckpointDecision]


def _approve_unchanged(kind: str, payload: str) -> CheckpointDecision:
    return CheckpointDecision(True, payload)


class AgentRunner:
    def __init__(
        self,
        definition: AgentDefinition,
        profile: ModelProfile,
        api_key: str,
        tools: LibraryTools,
        *,
        log_dir: Path | None = None,
        on_checkpoint: CheckpointHandler = _approve_unchanged,
        on_progress: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.definition = definition
        self.profile = profile
        self._headers = profile.auth_headers(api_key)
        self._secret = api_key.strip()
        self.tools = tools
        self.log_dir = log_dir
        self.on_checkpoint = on_checkpoint
        self.on_progress = on_progress or (lambda message: None)
        self.cancel_event = cancel_event or threading.Event()
        self.http = http_client or httpx.Client(timeout=timeout)
        self._receipts: set[str] = set()
        self._steps = 0
        self._terms_approved = True
        self._log: dict = {}

    # -- public -------------------------------------------------------------

    def run(self, question: str) -> AgentResult:
        if not question.strip():
            raise ValueError("请填写问题")
        self._receipts = set()
        self._steps = 0
        self._terms_approved = "confirm_search_terms" not in self.definition.checkpoints
        self._log = {
            "started_at": _now(),
            "definition": {
                "id": self.definition.agent_id,
                "version": self.definition.version,
                "sha256": sha256(self.definition.body.encode("utf-8")).hexdigest(),
                "source": self.definition.source,
            },
            "model": {
                "profile": self.profile.name,
                "host": self.profile.host,
                "model": self.profile.model,
            },
            "question": question,
            "turns": [],
            "checkpoints": [],
        }
        messages: list[dict] = [
            {"role": "system", "content": GUARD_PROMPT + "\n\n" + self.definition.body},
            {"role": "user", "content": question.strip()},
        ]
        try:
            return self._loop(messages)
        except AgentRunError as exc:
            return self._finish("error", "", error=str(exc))

    # -- loop ----------------------------------------------------------------

    def _loop(self, messages: list[dict]) -> AgentResult:
        tool_specs = self._tool_specs()
        while True:
            if self.cancel_event.is_set():
                return self._finish("cancelled", "")
            if self._steps >= self.definition.max_steps:
                messages.append({"role": "user", "content": STEP_LIMIT_PROMPT})
                message = self._call_model(messages, tools=None)
                return self._final(message, status="step_limit")
            self.on_progress(f"第 {self._steps + 1} 步：等待模型回复…")
            message = self._call_model(messages, tools=tool_specs)
            # Keep the assistant turn verbatim (incl. reasoning_content): some providers
            # require it to be sent back for multi-turn tool calling.
            messages.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                return self._final(message, status="completed")
            for call in calls:
                if self.cancel_event.is_set():
                    return self._finish("cancelled", "")
                self._steps += 1
                content = self._run_tool_call(call)
                if content is None:  # the user cancelled at a checkpoint
                    return self._finish("cancelled", "")
                messages.append(
                    {"role": "tool", "tool_call_id": call.get("id", ""), "content": content}
                )

    def _final(self, message: dict, *, status: str) -> AgentResult:
        text = _text(message.get("content"))
        if "confirm_before_final" in self.definition.checkpoints:
            decision = self.on_checkpoint("final", text)
            self._log["checkpoints"].append(
                {
                    "kind": "final",
                    "approved": decision.approved,
                    "edited": decision.approved and decision.payload != text,
                }
            )
            if not decision.approved:
                return self._finish("cancelled", text)
            text = decision.payload
        return self._finish(status, text)

    def _finish(self, status: str, text: str, *, error: str = "") -> AgentResult:
        check = check_answer(text, self._receipts) if text else None
        self._log.update(
            {
                "finished_at": _now(),
                "status": status,
                "steps": self._steps,
                "error": error,
                "final_text": text,
                "receipts": sorted(self._receipts),
                "flagged_lines": [
                    {"line": line.text, "status": line.status, "detail": line.detail}
                    for line in (check.lines if check else ())
                    if line.flagged
                ],
            }
        )
        return AgentResult(
            status=status,
            final_text=text,
            check=check,
            steps=self._steps,
            receipts=tuple(sorted(self._receipts)),
            log_path=self._write_log(),
            error=error,
            log=self._log,
        )

    # -- tools ---------------------------------------------------------------

    def _run_tool_call(self, call: dict) -> str | None:
        function = call.get("function") or {}
        name = str(function.get("name", ""))
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            arguments = None
        if not isinstance(arguments, dict):
            return self._tool_log(name, {}, error="参数不是合法的 JSON 对象")

        if name == SEARCH_TERMS_TOOL and "confirm_search_terms" in self.definition.checkpoints:
            return self._confirm_search_terms(arguments)
        if name not in self.definition.tools:
            return self._tool_log(name, arguments, error=f"工具 {name} 不在本智能体的白名单内")
        if name == "search_library" and not self._terms_approved:
            return self._tool_log(
                name, arguments, error=f"请先调用 {SEARCH_TERMS_TOOL} 让用户确认检索词"
            )
        self.on_progress(f"第 {self._steps} 步：调用 {name}")
        try:
            result = getattr(self.tools, name)(**arguments)
        except ToolError as exc:
            return self._tool_log(name, arguments, error=str(exc))
        except TypeError as exc:
            return self._tool_log(name, arguments, error=f"参数错误：{exc}")
        self._receipts.update(result.get("receipts", ()))
        return self._tool_log(name, arguments, result=result)

    def _confirm_search_terms(self, arguments: dict) -> str | None:
        terms = arguments.get("terms") or []
        proposal = "\n".join(str(term) for term in terms if str(term).strip())
        decision = self.on_checkpoint("search_terms", proposal)
        self._log["checkpoints"].append(
            {
                "kind": "search_terms",
                "proposed": proposal,
                "approved": decision.approved,
                "approved_terms": decision.payload if decision.approved else "",
            }
        )
        if not decision.approved:
            return None
        self._terms_approved = True
        approved = [line.strip() for line in decision.payload.splitlines() if line.strip()]
        return self._tool_log(SEARCH_TERMS_TOOL, arguments, result={"approved_terms": approved})

    def _tool_log(
        self, name: str, arguments: dict, *, result: dict | None = None, error: str = ""
    ) -> str:
        self._log["turns"].append(
            {
                "step": self._steps,
                "tool": name,
                "arguments": arguments,
                "receipts": list((result or {}).get("receipts", ())),
                "error": error,
            }
        )
        return json.dumps({"error": error} if error else result, ensure_ascii=False)

    def _tool_specs(self) -> list[dict]:
        specs = [_function_spec(name, getattr(self.tools, name)) for name in self.definition.tools]
        if "confirm_search_terms" in self.definition.checkpoints:
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": SEARCH_TERMS_TOOL,
                        "description": (
                            "检索前把拟用的检索词交给用户确认；返回用户确认（可能已修改）的检索词。"
                            "在调用 search_library 之前必须先调用本工具。"
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "terms": {"type": "array", "items": {"type": "string"}},
                                "rationale": {"type": "string"},
                            },
                            "required": ["terms"],
                        },
                    },
                }
            )
        return specs

    # -- model ---------------------------------------------------------------

    def _call_model(self, messages: list[dict], *, tools: list[dict] | None) -> dict:
        payload: dict = {
            "model": self.profile.model,
            "messages": messages,
            "temperature": self.profile.temperature,
        }
        if tools:
            payload["tools"] = tools
        try:
            response = self.http.post(self.profile.chat_url, headers=self._headers, json=payload)
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
        except httpx.HTTPStatusError as exc:
            detail = self._redact(exc.response.text[:300])
            status = exc.response.status_code
            raise AgentRunError(
                f"{http_hint(status)}（{self.profile.name} · {self.profile.host}，HTTP {status}）"
                f"\n原始信息：{detail}"
            ) from None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AgentRunError(f"模型服务调用失败：{self._redact(str(exc))}") from None
        if not isinstance(message, dict):
            raise AgentRunError("模型服务返回的 message 格式无法识别")
        turn: dict = {
            "step": self._steps,
            "model_turn": True,
            "tool_calls": len(message.get("tool_calls") or []),
        }
        if message.get("reasoning_content"):
            turn["reasoning_content"] = message["reasoning_content"]
        self._log["turns"].append(turn)
        return message

    def _redact(self, text: str) -> str:
        return text.replace(self._secret, "***") if self._secret else text

    def _write_log(self) -> Path | None:
        if self.log_dir is None:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.log_dir / f"{stamp}-{self.definition.agent_id}.json"
        path.write_text(
            self._redact(json.dumps(self._log, ensure_ascii=False, indent=2)), encoding="utf-8"
        )
        return path


def _function_spec(name: str, method: Callable) -> dict:
    hints = typing.get_type_hints(method)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for parameter in inspect.signature(method).parameters.values():
        properties[parameter.name] = _json_type(hints[parameter.name])
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _json_type(hint) -> dict:
    origin = typing.get_origin(hint)
    if origin in (types.UnionType, typing.Union):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if all(typing.get_origin(a) in (list, tuple) for a in args):
            return {"type": "array", "items": {"type": "string"}}
        return _json_type(args[0])
    if origin in (list, tuple):
        return {"type": "array", "items": {"type": "string"}}
    if hint is str:
        return {"type": "string"}
    if hint is int:
        return {"type": "integer"}
    raise TypeError(f"不支持的工具参数类型：{hint}")


def _text(content) -> str:
    if isinstance(content, list):
        content = "\n".join(item.get("text", "") for item in content if isinstance(item, dict))
    return content.strip() if isinstance(content, str) else ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
