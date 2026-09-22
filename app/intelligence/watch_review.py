"""Persist human review of archived Watch events without changing Watch baselines."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.intelligence.analysis import AnalysisReport, Metric, ReportRow, ReportSection

_STATUSES = frozenset({"pending", "important", "ignored"})


@dataclass(frozen=True, slots=True)
class ReviewItem:
    rule_id: str
    publication_number: str
    event_type: str
    detected_at: str
    title: str | None
    family_key: str | None
    status: str
    note: str


class WatchReviewStore:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS intelligence_watch_review (
                rule_id TEXT NOT NULL,
                publication_number TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','important','ignored')),
                note TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL,
                PRIMARY KEY(rule_id, publication_number, event_type)
            )"""
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def list_items(self, *, rule_id: str | None = None) -> tuple[ReviewItem, ...]:
        where = "WHERE w.rule_id = ?" if rule_id else ""
        params = (rule_id,) if rule_id else ()
        rows = self.connection.execute(
            f"""SELECT w.rule_id, w.publication_number,
                       COALESCE(w.event_type,'UNKNOWN') AS event_type,
                       w.detected_at, p.title, p.family_key,
                       COALESCE(r.status,'pending') AS status,
                       COALESCE(r.note,'') AS note
                FROM library_watch_source w
                JOIN library_publication p ON p.publication_number = w.publication_number
                LEFT JOIN intelligence_watch_review r
                  ON r.rule_id=w.rule_id AND r.publication_number=w.publication_number
                  AND r.event_type=COALESCE(w.event_type,'UNKNOWN')
                {where}
                ORDER BY w.detected_at DESC, w.rule_id, w.publication_number""",
            params,
        ).fetchall()
        return tuple(ReviewItem(**dict(row)) for row in rows)

    def set_review(self, item: ReviewItem, *, status: str, note: str = "") -> None:
        if status not in _STATUSES:
            raise ValueError("未知复核状态")
        self.connection.execute(
            """INSERT INTO intelligence_watch_review
               (rule_id,publication_number,event_type,status,note,reviewed_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(rule_id,publication_number,event_type) DO UPDATE SET
                 status=excluded.status,note=excluded.note,reviewed_at=excluded.reviewed_at""",
            (
                item.rule_id,
                item.publication_number,
                item.event_type,
                status,
                note.strip(),
                datetime.now(UTC).isoformat(),
            ),
        )
        self.connection.commit()

    def brief(self, *, rule_id: str | None = None) -> AnalysisReport:
        items = self.list_items(rule_id=rule_id)
        metrics = tuple(
            Metric(
                label,
                sum(item.event_type == event for item in items),
                f"按 Watch 事件类型 {event} 计数；同一公开号可由不同规则触发",
                tuple(
                    sorted({item.publication_number for item in items if item.event_type == event})
                ),
            )
            for label, event in (
                ("新专利族", "NEW_FAMILY"),
                ("家族新增成员", "NEW_FAMILY_MEMBER"),
                ("家族未解析新公开", "NEW_PUBLICATION_UNRESOLVED_FAMILY"),
            )
        )
        section = ReportSection(
            "待复核事件",
            ("发现时间", "规则", "类型", "公开号", "家族键", "状态", "备注"),
            tuple(
                ReportRow(
                    (
                        item.detected_at,
                        item.rule_id,
                        item.event_type,
                        item.publication_number,
                        item.family_key or "未解析",
                        item.status,
                        item.note,
                    ),
                    (item.publication_number,),
                )
                for item in items
            ),
        )
        return AnalysisReport(
            "新专利监控简报",
            "watch-brief",
            f"规则：{rule_id or '全部'}；数据：当前 LocalLibrary 已归档 Watch 事件",
            datetime.now(UTC),
            metrics,
            (section,),
            (
                "仅含已归档到 LocalLibrary 的 Watch 事件；没有事件不代表没有新专利。",
                "复核状态与备注为本地工作流数据，不改变 Watch 基线或事件类型。",
            ),
        )
