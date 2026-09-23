"""Turn an agent answer into readable blocks (for Tk and offline HTML).

Rendering never drops or rewrites a line: flagged lines stay visible with their reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from importlib import resources
from urllib.parse import quote

from app.agents.receipts import LineCheck, ReceiptCheck

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.、)])\s+(.*)$")
_TABLE_RULE_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
CITATION_RE = re.compile(r"\[([A-Z]{2}\d[0-9A-Z]*(?:\s*[,，、;；]\s*[A-Z]{2}\d[0-9A-Z]*)*)\]")


@dataclass(slots=True)
class Block:
    kind: str  # heading | bullet | paragraph | table
    text: str = ""
    level: int = 0
    line: LineCheck | None = None
    header: list[str] = field(default_factory=list)
    rows: list[tuple[list[str], LineCheck]] = field(default_factory=list)


def split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def blocks(check: ReceiptCheck) -> list[Block]:
    result: list[Block] = []
    lines = list(check.lines)
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.text.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("|"):
            table = Block("table")
            while index < len(lines) and lines[index].text.strip().startswith("|"):
                row = lines[index]
                text = row.text.strip()
                if _TABLE_RULE_RE.match(text):
                    pass
                elif not table.header and not table.rows:
                    table.header = split_cells(text)
                else:
                    table.rows.append((split_cells(text), row))
                index += 1
            result.append(table)
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            result.append(Block("heading", heading.group(2), len(heading.group(1)), line))
        else:
            bullet = _BULLET_RE.match(stripped)
            if bullet:
                result.append(Block("bullet", bullet.group(1), line=line))
            else:
                result.append(Block("paragraph", stripped, line=line))
        index += 1
    return result


def text_parts(text: str) -> list[tuple[str, bool]]:
    """Split text into (fragment, is_citation) pairs."""
    parts: list[tuple[str, bool]] = []
    position = 0
    for match in CITATION_RE.finditer(text):
        if match.start() > position:
            parts.append((text[position : match.start()], False))
        parts.append((match.group(0), True))
        position = match.end()
    if position < len(text):
        parts.append((text[position:], False))
    return parts


# -- HTML ------------------------------------------------------------------------

_FOOTER = (
    "每条结论后的公开号均来自本次运行中工具返回的本地库记录；"
    "标红的行未通过证据校验，需要人工复核。"
    "本结果不构成新颖性、FTO、侵权或有效性结论。"
)


def _css() -> str:
    return resources.files("app.agents").joinpath("answer.css").read_text(encoding="utf-8")


def _cite_html(fragment: str) -> str:
    numbers = re.split(r"\s*[,，、;；]\s*", fragment.strip("[]"))
    links = []
    for number in numbers:
        url = "https://patents.google.com/patent/" + quote(number, safe="")
        links.append(
            f'<a class="cite" href="{escape(url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{escape(number)}</a>'
        )
    return "".join(links)


def _inline_html(text: str) -> str:
    return "".join(_cite_html(part) if cite else escape(part) for part, cite in text_parts(text))


def _why(line: LineCheck | None) -> str:
    return f"<span class='why'>⚠ {escape(line.detail)}</span>" if line and line.flagged else ""


def _flag(line: LineCheck | None) -> str:
    return " class='flagged'" if line and line.flagged else ""


def render_html(
    check: ReceiptCheck, *, title: str, question: str, meta: str, banner: str
) -> str:
    body: list[str] = []
    open_list = False
    in_section = False

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            body.append("</ul>")
            open_list = False

    for block in blocks(check):
        if block.kind != "bullet":
            close_list()
        if block.kind == "heading":
            if block.level <= 2:
                if in_section:
                    body.append("</section>")
                body.append("<section class='card'>")
                in_section = True
                body.append(f"<h2>{_inline_html(block.text)}</h2>")
            else:
                body.append(f"<h3>{_inline_html(block.text)}</h3>")
        elif block.kind == "bullet":
            if not open_list:
                body.append("<ul>")
                open_list = True
            body.append(f"<li{_flag(block.line)}>{_inline_html(block.text)}{_why(block.line)}</li>")
        elif block.kind == "paragraph":
            body.append(f"<p{_flag(block.line)}>{_inline_html(block.text)}{_why(block.line)}</p>")
        else:
            head = "".join(f"<th>{escape(cell)}</th>" for cell in block.header)
            has_flags = any(line.flagged for _, line in block.rows)
            if has_flags:
                head += "<th>复核</th>"
            rows = "".join(
                f"<tr{_flag(line)}>"
                + "".join(f"<td>{_inline_html(cell)}</td>" for cell in cells)
                + (f"<td>{_why(line)}</td>" if line.flagged else "")
                + ("<td></td>" if not line.flagged and has_flags else "")
                + "</tr>"
                for cells, line in block.rows
            )
            body.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
    close_list()
    if in_section:
        body.append("</section>")
    warn = " warn" if "需复核的行 0" not in banner else ""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>{_css()}</style></head><body><main>
<header><h1>{escape(title)}</h1>
<div class="meta">问题：{escape(question)}<br>{escape(meta)}</div>
<div class="banner{warn}">{escape(banner)}</div></header>
{''.join(body)}
<p class="exempt">{_FOOTER}</p>
</main></body></html>
"""
