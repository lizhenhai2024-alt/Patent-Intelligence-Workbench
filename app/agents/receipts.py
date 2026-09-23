"""Evidence check for agent answers (Agent track M2).

A line passes only when it cites publication numbers that tools actually
returned during this run. Failing lines are flagged, never deleted or rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EXEMPT_HEADING = "局限与待确认"
_BRACKET_RE = re.compile(r"\[([^\[\]\n]+)\]")
_NUMBER_RE = re.compile(r"^[A-Z]{2}\d[0-9A-Z]*$")
_SPLIT_RE = re.compile(r"[\s,，、;；]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_RULE_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")

# A safety net, not a guarantee: phrases that state legal or probabilistic conclusions.
FORBIDDEN_PHRASES = (
    "具备新颖性",
    "不具备新颖性",
    "具备创造性",
    "不具备创造性",
    "构成侵权",
    "不构成侵权",
    "侵权风险低",
    "侵权风险高",
    "侵权风险较低",
    "侵权风险较高",
    "无侵权风险",
    "可以自由实施",
    "freedom to operate",
    "does not infringe",
    "is novel",
)
_PROBABILITY_RE = re.compile(
    r"(概率|可能性|置信度|probability|likelihood)[^。\n]{0,12}?\d+(\.\d+)?\s*%"
    r"|\d+(\.\d+)?\s*%[^。\n]{0,8}?(概率|可能性|probability|likelihood)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class LineCheck:
    text: str
    status: str  # ok | exempt | uncited | unknown_receipt | forbidden
    detail: str = ""

    @property
    def flagged(self) -> bool:
        return self.status in {"uncited", "unknown_receipt", "forbidden"}


@dataclass(frozen=True, slots=True)
class ReceiptCheck:
    lines: tuple[LineCheck, ...]
    cited: tuple[str, ...]

    @property
    def flagged_count(self) -> int:
        return sum(line.flagged for line in self.lines)


def citations(line: str) -> tuple[str, ...]:
    found: list[str] = []
    for group in _BRACKET_RE.findall(line):
        for token in _SPLIT_RE.split(group.strip()):
            token = token.strip().upper()
            if _NUMBER_RE.match(token):
                found.append(token)
    return tuple(dict.fromkeys(found))


def forbidden_reason(line: str) -> str:
    lowered = line.casefold()
    for phrase in FORBIDDEN_PHRASES:
        if phrase.casefold() in lowered:
            return f"含“{phrase}”"
    if _PROBABILITY_RE.search(line):
        return "含概率/可能性百分比"
    return ""


def check_answer(text: str, valid_receipts: set[str] | frozenset[str]) -> ReceiptCheck:
    valid = {number.upper() for number in valid_receipts}
    raw_lines = text.splitlines()
    results: list[LineCheck] = []
    cited: list[str] = []
    exempt_level = 0  # >0 while inside the exempt section, holds its heading level
    for index, line in enumerate(raw_lines):
        stripped = line.strip()
        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            if exempt_level and level <= exempt_level:
                exempt_level = 0
            if EXEMPT_HEADING in heading.group(2):
                exempt_level = level
            results.append(LineCheck(line, "exempt", "标题"))
            continue
        if not stripped or _TABLE_RULE_RE.match(stripped) or _is_table_header(raw_lines, index):
            results.append(LineCheck(line, "exempt"))
            continue
        if exempt_level:
            results.append(LineCheck(line, "exempt", EXEMPT_HEADING))
            continue
        reason = forbidden_reason(stripped)
        if reason:
            results.append(LineCheck(line, "forbidden", f"超出工具边界的结论（{reason}）"))
            continue
        numbers = citations(stripped)
        cited.extend(numbers)
        unknown = [n for n in numbers if n not in valid]
        if unknown:
            detail = "引用了本次未由工具返回的公开号：" + "、".join(unknown)
            results.append(LineCheck(line, "unknown_receipt", detail))
        elif not numbers:
            results.append(LineCheck(line, "uncited", "无证据支撑"))
        else:
            results.append(LineCheck(line, "ok"))
    return ReceiptCheck(tuple(results), tuple(dict.fromkeys(cited)))


def _is_table_header(lines: list[str], index: int) -> bool:
    if not lines[index].strip().startswith("|") or index + 1 >= len(lines):
        return False
    return bool(_TABLE_RULE_RE.match(lines[index + 1].strip()))
