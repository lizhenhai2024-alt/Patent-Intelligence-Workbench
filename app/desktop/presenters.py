"""Pure presentation helpers kept separate from Tk widgets."""

from __future__ import annotations

from app.library.models import LibraryPatent
from app.watch.models import WatchRule
from app.watch.state import WatchRuleState, WatchRunHistory


def patent_row(patent: LibraryPatent) -> tuple[str, str, str, str, str, str, str]:
    assignees = patent.current_assignees or patent.original_assignees
    owner = ", ".join(assignees) or ", ".join(patent.company_groups)
    return (
        patent.publication_number,
        patent.jurisdiction,
        patent.title or "",
        owner,
        ", ".join(patent.technology_topics),
        "★" if patent.favorite else "",
        "PDF" if patent.pdf_paths else "",
    )


def watch_rule_row(
    rule: WatchRule,
    state: WatchRuleState,
) -> tuple[str, str, str, str, str]:
    return (
        rule.name,
        "启用" if rule.enabled else "关闭",
        f"{rule.cadence_hours}h",
        state.last_run_at.isoformat(timespec="minutes")
        if state.last_run_at
        else "从未运行",
        rule.company_group,
    )


def watch_history_row(history: WatchRunHistory) -> tuple[str, str, str, str, str]:
    return (
        history.rule_id,
        history.status,
        history.started_at.isoformat(timespec="minutes"),
        str(history.event_count),
        history.fatal_error or "",
    )
