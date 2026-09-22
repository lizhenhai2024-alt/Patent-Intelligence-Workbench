"""Self-contained HTML reports with drill-down publication receipts."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote

from app.intelligence.analysis import AnalysisReport, Metric, ReportRow, ReportSection


def _receipts(numbers: tuple[str, ...]) -> str:
    if not numbers:
        return "<span class='muted'>无对应公开件</span>"
    links = []
    for number in numbers:
        url = "https://patents.google.com/patent/" + quote(number, safe="")
        links.append(
            f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
            f"{escape(number)}</a>"
        )
    return "、".join(links)


def _metric(metric: Metric) -> str:
    return (
        "<article class='metric'>"
        f"<div class='value'>{metric.value}</div><strong>{escape(metric.label)}</strong>"
        f"<details><summary>计算口径与来源</summary><p>{escape(metric.formula)}</p>"
        f"<p>{_receipts(metric.publication_numbers)}</p></details></article>"
    )


def _row(row: ReportRow) -> str:
    cells = "".join(f"<td>{escape(value)}</td>" for value in row.cells)
    return (
        f"<tr>{cells}<td><details><summary>查看来源</summary>"
        f"{_receipts(row.publication_numbers)}</details></td></tr>"
    )


def _section(section: ReportSection) -> str:
    headers = "".join(f"<th>{escape(name)}</th>" for name in (*section.columns, "证据"))
    rows = "".join(_row(row) for row in section.rows)
    if not rows:
        rows = (
            f"<tr><td colspan='{len(section.columns) + 1}' class='muted'>当前范围没有记录</td></tr>"
        )
    return (
        f"<section><h2>{escape(section.title)}</h2><div class='table-wrap'><table>"
        f"<thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div></section>"
    )


def render_html(report: AnalysisReport) -> str:
    """Render an offline document; external links are optional evidence exits only."""
    metrics = "".join(_metric(item) for item in report.metrics)
    sections = "".join(_section(item) for item in report.sections)
    notes = "".join(f"<li>{escape(item)}</li>" for item in report.notes)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(report.title)}</title>
<style>
:root {{ color-scheme: light; font-family: 'Segoe UI','Microsoft YaHei',sans-serif;
color:#14233b; background:#f5f8fc; }}
body {{ max-width:1200px; margin:0 auto; padding:32px 24px 72px; }}
header,section,.metric {{ background:white; border:1px solid #dbe5f2;
border-radius:14px; box-shadow:0 2px 10px #15375e0a; }}
header,section {{ padding:20px 24px; margin-bottom:18px; }}
h1 {{ margin:0 0 8px; }} h2 {{ margin:0 0 14px; font-size:19px; }}
.muted,small {{ color:#5f6f85; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
gap:14px; margin:18px 0; }}
.metric {{ padding:18px; }} .value {{ color:#1261d6; font-size:30px; font-weight:700; }}
details {{ margin-top:8px; }} summary {{ cursor:pointer; color:#1261d6; }} a {{ color:#1261d6; }}
.table-wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; }}
th,td {{ border-bottom:1px solid #e9eef5; padding:9px; text-align:left;
vertical-align:top; }}
th {{ background:#f4f7fb; }} td:last-child {{ min-width:120px; }} li {{ margin:6px 0; }}
</style></head><body>
<header><h1>{escape(report.title)}</h1><div>{escape(report.scope)}</div>
<p class="muted">来源：当前 LocalLibrary · 生成时间（UTC）：
{escape(report.generated_at.isoformat())} · 工作流：{escape(report.workflow)}</p></header>
<div class="metrics">{metrics}</div>{sections}
<section><h2>方法与限制</h2><ul>{notes}</ul></section>
</body></html>"""


def save_html(report: AnalysisReport, destination: str | Path) -> Path:
    path = Path(destination)
    if path.suffix.casefold() != ".html":
        raise ValueError("报告文件须以 .html 结尾")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path
