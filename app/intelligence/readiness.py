"""Explain local evidence coverage before an engineering task is run."""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.guidance import WorkflowGuide
from app.library.models import LibraryQuery
from app.library.store import SQLitePatentLibrary


@dataclass(frozen=True, slots=True)
class LibraryReadiness:
    level: str
    summary: str
    detail: str
    next_action: str
    can_run: bool
    publications: int
    known_families: int
    company_mapped_publications: int
    topic_tagged_publications: int
    pdf_backed_publications: int


def assess_library_readiness(store: SQLitePatentLibrary, guide: WorkflowGuide) -> LibraryReadiness:
    count = store.count_patents()
    if not guide.uses_library:
        return LibraryReadiness(
            "not-required",
            "这个任务可在没有本地专利的情况下开始。",
            "生成词组后，请在 Search 确认范围并运行检索。",
            "search",
            True,
            0,
            0,
            0,
            0,
            0,
        )
    if count == 0:
        return LibraryReadiness(
            "empty",
            "本地库尚无已索引公开件，不能生成有意义的分析。",
            "先在 Search 检索并保存专利，或在 Local Library 选择并同步已有 PatentLibrary 根目录。",
            "search",
            False,
            0,
            0,
            0,
            0,
            0,
        )
    patents = store.query(LibraryQuery(limit=count))
    families = {patent.family_key for patent in patents if patent.family_key}
    company_mapped = sum(bool(patent.company_groups) for patent in patents)
    topic_tagged = sum(bool(patent.technology_topics) for patent in patents)
    pdf_backed = sum(bool(patent.pdf_paths) for patent in patents)
    gaps = []
    if not families:
        gaps.append("尚无已解析家族")
    if guide.needs_companies and not company_mapped:
        gaps.append("尚无已映射公司组")
    if guide.needs_routes and not topic_tagged:
        gaps.append("尚无已标注技术节点")
    if guide.workflow_id == "watch-brief" and not any(patent.watch_rule_ids for patent in patents):
        gaps.append("尚无已归档 Watch 事件")
    if gaps:
        return LibraryReadiness(
            "limited",
            f"已索引 {len(patents)} 件公开件，但当前任务的数据覆盖有限。",
            "；".join(gaps) + "。可继续查看，但请先补充或复核这些元数据。",
            "library",
            True,
            len(patents),
            len(families),
            company_mapped,
            topic_tagged,
            pdf_backed,
        )
    return LibraryReadiness(
        "ready",
        f"当前本地库可用于初步分析：{len(patents)} 件公开件、{len(families)} 个已知家族。",
        (
            f"已映射公司组 {company_mapped} 件，已标注技术节点 {topic_tagged} 件，"
            f"已有 PDF {pdf_backed} 件。"
        ),
        "run",
        True,
        len(patents),
        len(families),
        company_mapped,
        topic_tagged,
        pdf_backed,
    )
