"""Agent definition files: TOML front matter + Markdown body (Agent track M2).

The file describes *how* an agent works. Permissions are enforced in code:
a definition can only narrow them (tool subset, step count), never widen them.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from app.agent_tools.tools import TOOL_NAMES

MAX_STEPS_CAP = 30
CHECKPOINTS = ("confirm_search_terms", "confirm_before_final")
OUTPUT_TYPES = ("report_with_receipts",)
REQUIRED_SECTIONS = ("## 目标", "## 步骤", "## 输出模板")
_KEYS = {"id", "name", "version", "description", "tools", "max_steps", "checkpoints", "output"}
_ID_RE = re.compile(r"^[a-z0-9_]+$")
_FRONT_MATTER_RE = re.compile(r"\A\+\+\+[ \t]*\r?\n(.*?)\r?\n\+\+\+[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)


class DefinitionError(ValueError):
    """A definition file was refused; the message names the file and field."""


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    agent_id: str
    name: str
    version: int
    description: str
    tools: tuple[str, ...]
    max_steps: int
    checkpoints: tuple[str, ...]
    output: str
    body: str
    source: str


def parse_definition(text: str, *, stem: str, source: str = "") -> AgentDefinition:
    label = source or stem
    match = _FRONT_MATTER_RE.match(text.lstrip("﻿"))
    if not match:
        raise DefinitionError(f"{label}：缺少以 +++ 包围的 TOML 头部")
    try:
        meta = tomllib.loads(match.group(1))
    except tomllib.TOMLDecodeError as exc:
        raise DefinitionError(f"{label}：TOML 头部格式错误：{exc}") from None
    body = match.group(2).strip()

    unknown = sorted(set(meta) - _KEYS)
    if unknown:
        raise DefinitionError(f"{label}：不认识的字段 {', '.join(unknown)}（拼写错误不会被忽略）")
    missing = sorted(_KEYS - set(meta))
    if missing:
        raise DefinitionError(f"{label}：缺少字段 {', '.join(missing)}")

    agent_id = meta["id"]
    if not isinstance(agent_id, str) or not _ID_RE.match(agent_id):
        raise DefinitionError(f"{label}：id 只能包含小写字母、数字和下划线")
    if agent_id != stem:
        raise DefinitionError(f"{label}：id “{agent_id}”必须与文件名“{stem}”一致")
    for key in ("name", "description"):
        if not isinstance(meta[key], str) or not meta[key].strip():
            raise DefinitionError(f"{label}：{key} 必须是非空文字")
    if not isinstance(meta["version"], int) or isinstance(meta["version"], bool):
        raise DefinitionError(f"{label}：version 必须是整数")

    tools = meta["tools"]
    if not isinstance(tools, list) or not tools or not all(isinstance(t, str) for t in tools):
        raise DefinitionError(f"{label}：tools 必须是非空的工具名列表")
    bad_tools = [t for t in tools if t not in TOOL_NAMES]
    if bad_tools:
        raise DefinitionError(
            f"{label}：tools 中有未开放的工具 {', '.join(bad_tools)}；"
            f"只允许只读工具：{', '.join(TOOL_NAMES)}"
        )

    steps = meta["max_steps"]
    if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= MAX_STEPS_CAP:
        raise DefinitionError(f"{label}：max_steps 必须是 1 到 {MAX_STEPS_CAP} 之间的整数")

    checkpoints = meta["checkpoints"]
    if not isinstance(checkpoints, list) or not all(c in CHECKPOINTS for c in checkpoints):
        raise DefinitionError(f"{label}：checkpoints 只能从 {', '.join(CHECKPOINTS)} 中选择")
    if meta["output"] not in OUTPUT_TYPES:
        raise DefinitionError(f"{label}：output 只能是 {', '.join(OUTPUT_TYPES)}")

    headings = {line.strip() for line in body.splitlines()}
    missing_sections = [s for s in REQUIRED_SECTIONS if s not in headings]
    if missing_sections:
        raise DefinitionError(f"{label}：正文缺少章节 {'、'.join(missing_sections)}")

    return AgentDefinition(
        agent_id=agent_id,
        name=meta["name"].strip(),
        version=meta["version"],
        description=meta["description"].strip(),
        tools=tuple(dict.fromkeys(tools)),
        max_steps=steps,
        checkpoints=tuple(dict.fromkeys(checkpoints)),
        output=meta["output"],
        body=body,
        source=source,
    )


def load_definition(path: str | Path) -> AgentDefinition:
    file = Path(path)
    return parse_definition(file.read_text(encoding="utf-8"), stem=file.stem, source=str(file))


def load_definitions(
    directories: tuple[Path, ...] = (),
) -> tuple[tuple[AgentDefinition, ...], tuple[str, ...]]:
    """Load the shipped definitions plus any user directories.

    Returns (definitions, errors); a refused file is reported, never half-loaded.
    """
    files: list[tuple[str, str, str]] = []
    shipped = resources.files("app.agents").joinpath("definitions")
    for item in sorted(shipped.iterdir(), key=lambda entry: entry.name):
        if item.name.endswith(".md"):
            files.append((item.read_text(encoding="utf-8"), item.name[:-3], f"内置/{item.name}"))
    for directory in directories:
        if directory.is_dir():
            for path in sorted(directory.glob("*.md")):
                files.append((path.read_text(encoding="utf-8"), path.stem, str(path)))

    definitions: dict[str, AgentDefinition] = {}
    errors: list[str] = []
    for text, stem, source in files:
        try:
            definition = parse_definition(text, stem=stem, source=source)
        except DefinitionError as exc:
            errors.append(str(exc))
            continue
        if definition.agent_id in definitions:
            errors.append(f"{source}：id “{definition.agent_id}”与已加载的定义重复，已忽略")
            continue
        definitions[definition.agent_id] = definition
    return tuple(definitions.values()), tuple(errors)
