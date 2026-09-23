"""Read-only LocalLibrary tools for external AI agents (Agent track M1).

Every tool returns the same JSON-serialisable envelope with publication-number
receipts. User-private annotation fields (note, projects, tags, watch rules)
are never returned, because tool output is forwarded to the client's model.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from app.core.company_registry import CompanyGroup, CompanyRegistry
from app.intelligence.analysis import AnalysisReport, AnalysisScope, AnalysisService
from app.library import fulltext as ft_index
from app.library.models import LibraryPatent, LibraryQuery
from app.library.store import SQLitePatentLibrary
from app.library.workbench import preferred_library_pdf

TOOL_NAMES = (
    "library_status",
    "list_companies",
    "list_technology_topics",
    "search_library",
    "get_publication",
    "read_publication_text",
    "get_family",
    "run_landscape",
    "run_company_profile",
    "run_comparison",
)
TOOL_DESCRIPTIONS = {
    "library_status": (
        "本地库概况：数据库位置、公开件/专利族/证据数量、最后修改时间，"
        "以及全文索引覆盖（已索引、需要 OCR、未索引件数）。"
    ),
    "list_companies": "已登记公司组（group_id、显示名、别名）。公司参数只接受这里的精确名称。",
    "list_technology_topics": (
        "本地库已有的技术主题（search_library 用）和可对比的技术路线（run_comparison 用）。"
    ),
    "search_library": (
        "检索本地库公开件。fulltext 为全文检索词列表（在权利要求和说明书正文中查找，"
        "返回命中片段和位置；match=all 需全部命中，any 任一命中；3 个字以上最准）；"
        "text 只匹配公开号/标题/申请人/分类号；company 为精确公司名；"
        "technology 为 list_technology_topics 的 topic 原值；日期 YYYY-MM-DD；limit 1-100。"
    ),
    "get_publication": "单个公开件的著录信息、分类号、优先权和来源类型。",
    "read_publication_text": (
        "读取已索引的权利要求(claims)或说明书(description)，按段返回页码；"
        "claims 可指定权利要求编号列表只读其中几条；from_ordinal 从第几段开始；"
        "max_chars 1-20000。未建索引时临时解析本地 PDF；没有 PDF 返回 available=false，不联网。"
    ),
    "get_family": (
        "按 family_key 或 publication_number（二选一）列出专利族成员，成员按国家公开件分列。"
    ),
    "run_landscape": "专利全景报告：申请趋势、公司、国家/局、技术分支，每行带公开号回执。",
    "run_company_profile": "单个公司组的技术画像报告（公司名精确匹配）。",
    "run_comparison": "对比至少两家公司（companies）或至少两条技术路线（routes），二选一。",
}
MAX_SEARCH_LIMIT = 100
MAX_TEXT_CHARS = 20_000
ROW_RECEIPT_LIMIT = 50
SCOPE_NOTE = "结果仅覆盖当前 LocalLibrary 已索引记录，不代表全部专利。"
DATE_BASIS_NOTE = "日期过滤口径：申请日，缺失时依次回退到最早优先权日、公开日。"


class ToolError(ValueError):
    """A tool call was rejected; the message is shown to the agent."""


class LibraryTools:
    def __init__(
        self,
        store: SQLitePatentLibrary,
        *,
        registry: CompanyRegistry | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or CompanyRegistry.default()
        self.analysis = AnalysisService(store, registry=self.registry)

    # -- orientation -------------------------------------------------------

    def library_status(self) -> dict:
        modified = datetime.fromtimestamp(self.store.path.stat().st_mtime, UTC)
        data = {
            "database": str(self.store.path),
            "database_modified_at": modified.isoformat(timespec="seconds"),
            "publications": self.store.count_patents(),
            "families": self.store.count_families(),
            "evidence_records": self.store.count_evidence(),
            "fulltext_index": (
                ft_index.coverage(self.store.connection)
                if ft_index.tables_exist(self.store.connection)
                else {"indexed": 0, "note": "尚未建立全文索引"}
            ),
        }
        return _envelope(data, ())

    def list_companies(self) -> dict:
        data = [
            {
                "group_id": group.group_id,
                "display_name": group.display_name,
                "aliases": list(group.aliases),
            }
            for group in self.registry.groups
        ]
        note = "公司参数必须使用这里的 group_id 或 display_name，按精确匹配解析。"
        return _envelope(data, (), notes=(note,))

    def list_technology_topics(self) -> dict:
        rows = self.store.connection.execute(
            """
            SELECT topic, COUNT(DISTINCT publication_number) AS count
            FROM library_technology_topic
            GROUP BY topic
            ORDER BY count DESC, topic
            """
        ).fetchall()
        library_topics = [{"topic": row["topic"], "publications": row["count"]} for row in rows]
        routes = [
            {"route_id": node.node_id, "name": node.name}
            for node in self.analysis.classifier._iter_nodes(self.analysis.taxonomy.roots)
        ]
        routes += [
            {"route_id": topic.topic_id, "name": topic.display_name}
            for topic in self.analysis.dictionary.topics
        ]
        return _envelope(
            {"library_topics": library_topics, "comparison_routes": routes},
            (),
            notes=(
                "search_library 的 technology 参数使用 library_topics 中的 topic 原值。",
                "run_comparison 的 routes 参数使用 comparison_routes 的 route_id 或 name。",
            ),
        )

    # -- publications ------------------------------------------------------

    def search_library(
        self,
        text: str | None = None,
        company: str | None = None,
        technology: str | None = None,
        jurisdictions: list[str] | tuple[str, ...] = (),
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 20,
        fulltext: list[str] | tuple[str, ...] = (),
        match: str = "all",
    ) -> dict:
        if not 1 <= int(limit) <= MAX_SEARCH_LIMIT:
            raise ToolError(f"limit 必须在 1 到 {MAX_SEARCH_LIMIT} 之间")
        if match not in {"all", "any"}:
            raise ToolError("match 只能是 all 或 any")
        notes: list[str] = []
        fulltext_hits: dict[str, ft_index.Hit] | None = None
        if fulltext_terms := [term for term in fulltext if str(term).strip()]:
            if not ft_index.tables_exist(self.store.connection):
                raise ToolError("尚未建立全文索引：请在“本地专利库”页点“更新全文索引”")
            found, search_notes = ft_index.search(
                self.store.connection, fulltext_terms, match=match
            )
            fulltext_hits = {hit.publication_number: hit for hit in found}
            notes.extend(search_notes)
            coverage = ft_index.coverage(self.store.connection)
            if coverage["not_indexed"] or coverage["statuses"].get(ft_index.STATUS_NEEDS_OCR):
                notes.append(
                    f"全文检索只覆盖已索引的 {coverage['indexed']} 件"
                    f"（未索引 {coverage['not_indexed']} 件，"
                    f"需要 OCR {coverage['statuses'].get(ft_index.STATUS_NEEDS_OCR, 0)} 件）。"
                )
        start, end = _parse_date(from_date, "from_date"), _parse_date(to_date, "to_date")
        company_groups = (self._company(company).group_id,) if company else ()
        query = LibraryQuery(
            text=text,
            jurisdictions=tuple(value.upper() for value in jurisdictions),
            company_groups=company_groups,
            technology_topics=(technology,) if technology else (),
            limit=max(1, self.store.count_patents()),
        )
        needle = (text or "").strip().casefold()
        hits = [
            patent
            for patent in self.store.query(query)
            # The store's text filter also matches private notes; re-check public fields only.
            if (not needle or _public_text_match(patent, needle))
            and _within_dates(patent, start, end)
            and (fulltext_hits is None or patent.publication_number in fulltext_hits)
        ]
        if fulltext_hits is not None:
            order = {number: i for i, number in enumerate(fulltext_hits)}
            hits.sort(key=lambda patent: order[patent.publication_number])
        kept = hits[: int(limit)]
        results = []
        for patent in kept:
            item = _publication(patent)
            if fulltext_hits is not None:
                hit = fulltext_hits[patent.publication_number]
                item["matched_segments"] = hit.matched_segments
                item["snippets"] = list(hit.snippets)
            results.append(item)
        if start or end:
            notes.append(DATE_BASIS_NOTE)
        return _envelope(
            {"total_matches": len(hits), "results": results},
            (p.publication_number for p in kept),
            truncated=len(hits) > len(kept),
            notes=tuple(notes),
        )

    def get_publication(self, publication_number: str) -> dict:
        patent = self._patent(publication_number)
        data = _publication(patent)
        data["priorities"] = [
            {
                "number": item.number,
                "country": item.country,
                "date": _iso(item.priority_date),
                "type": item.priority_type,
            }
            for item in patent.priorities
        ]
        # source_ref is withheld: it can hold watch-rule ids or local file paths.
        data["provenance"] = [
            {
                "source_type": item.source_type,
                "first_seen_at": item.first_seen_at.isoformat(timespec="seconds"),
            }
            for item in patent.provenance
        ]
        return _envelope(data, (patent.publication_number,))

    def read_publication_text(
        self,
        publication_number: str,
        section: str = "claims",
        max_chars: int = 8000,
        claims: list[int] | tuple[int, ...] = (),
        from_ordinal: int = 1,
    ) -> dict:
        if section not in {"claims", "description"}:
            raise ToolError("section 只能是 claims 或 description（本地库不存摘要）")
        if not 1 <= int(max_chars) <= MAX_TEXT_CHARS:
            raise ToolError(f"max_chars 必须在 1 到 {MAX_TEXT_CHARS} 之间")
        if int(from_ordinal) < 1:
            raise ToolError("from_ordinal 从 1 开始")
        patent = self._patent(publication_number)
        number = patent.publication_number
        connection = self.store.connection
        source = (
            ft_index.text_source(connection, number)
            if ft_index.tables_exist(connection)
            else None
        )
        if source is not None and source["status"] != ft_index.STATUS_FAILED:
            segments = ft_index.read_segments(connection, number, section)
            notes = [f"文本来源：{source['source_type']}（{source['status']}）"]
            if source["detail"]:
                notes.append(source["detail"])
        else:
            pdf = preferred_library_pdf(patent)
            if pdf is None:
                data = {"publication_number": number, "available": False}
                return _envelope(data, (), notes=("本地库没有该公开件的 PDF；本工具不联网获取。",))
            parsed = ft_index.parse_pdf(pdf)
            segments = [
                {
                    "ordinal": s.ordinal, "claim_number": s.claim_number,
                    "page_start": s.page_start, "page_end": s.page_end, "text": s.text,
                }
                for s in parsed.segments
                if s.section == section
            ]
            source = {"source_type": "PDF", "status": parsed.status}
            notes = ["该件尚未建全文索引，本次临时解析本地 PDF。"]
            if parsed.detail:
                notes.append(parsed.detail)
        wanted = {int(n) for n in claims}
        selected = [
            s
            for s in segments
            if s["ordinal"] >= int(from_ordinal)
            and (not wanted or section != "claims" or s["claim_number"] in wanted)
        ]
        out, used, truncated = [], 0, False
        for segment in selected:
            remaining = int(max_chars) - used
            if remaining <= 0:
                truncated = True
                break
            text = segment["text"]
            if len(text) > remaining:
                text, truncated = text[:remaining], True
            out.append({**segment, "text": text})
            used += len(text)
        if not segments:
            notes.append("未识别出该章节，可能是扫描件或版式未识别。")
        data = {
            "publication_number": number,
            "available": True,
            "section": section,
            "source_type": source["source_type"],
            "status": source["status"],
            "segments": out,
            "total_segments": len(segments),
        }
        return _envelope(
            data, (number,) if out else (), truncated=truncated, notes=tuple(notes)
        )

    def get_family(
        self,
        family_key: str | None = None,
        publication_number: str | None = None,
    ) -> dict:
        if bool(family_key) == bool(publication_number):
            raise ToolError("family_key 和 publication_number 必须且只能提供一个")
        if publication_number:
            patent = self._patent(publication_number)
            if not patent.family_key:
                return _envelope(
                    {"family_key": None, "members": [_publication(patent)]},
                    (patent.publication_number,),
                    notes=("该公开件在本地库中尚未解析专利族。",),
                )
            family_key = patent.family_key
        members = self.store.get_family_members(family_key)
        if not members:
            raise ToolError(f"本地库中没有专利族：{family_key}")
        data = {
            "family_key": family_key,
            "family_type": members[0].family_type,
            "members": [_publication(p) for p in members],
        }
        return _envelope(
            data,
            (p.publication_number for p in members),
            notes=("族成员按国家公开件分别列出，不合并计数。",),
        )

    # -- reports -----------------------------------------------------------

    def run_landscape(
        self,
        topic: str = "",
        jurisdictions: list[str] | tuple[str, ...] = (),
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        scope = _scope(topic, jurisdictions, from_date, to_date)
        return _report(self.analysis.landscape(scope))

    def run_company_profile(
        self,
        company: str,
        topic: str = "",
        jurisdictions: list[str] | tuple[str, ...] = (),
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        group = self._company(company)
        scope = _scope(topic, jurisdictions, from_date, to_date)
        return _report(self.analysis.company_profile(scope, group.group_id))

    def run_comparison(
        self,
        companies: list[str] | tuple[str, ...] = (),
        routes: list[str] | tuple[str, ...] = (),
        topic: str = "",
        jurisdictions: list[str] | tuple[str, ...] = (),
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        if bool(companies) == bool(routes):
            raise ToolError("companies 和 routes 必须且只能提供一个，且至少两项")
        scope = _scope(topic, jurisdictions, from_date, to_date)
        try:
            if companies:
                ids = tuple(self._company(value).group_id for value in companies)
                report = self.analysis.competitive_landscape(scope, ids)
            else:
                report = self.analysis.route_comparison(scope, tuple(routes))
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return _report(report)

    # -- helpers -----------------------------------------------------------

    def _company(self, value: str) -> CompanyGroup:
        try:
            return self.registry.get(value.strip())
        except KeyError:
            known = "、".join(group.group_id for group in self.registry.groups)
            raise ToolError(
                f"未登记的公司：{value}。公司按精确匹配解析，可用 group_id：{known}"
            ) from None

    def _patent(self, publication_number: str) -> LibraryPatent:
        number = publication_number.strip().upper()
        patent = self.store.get_patent(number)
        if patent is None:
            raise ToolError(f"本地库中没有公开件：{publication_number}")
        return patent


def _envelope(data, receipts, *, truncated: bool = False, notes=()) -> dict:
    return {
        "data": data,
        "receipts": sorted(set(receipts)),
        "source": "LocalLibrary",
        "as_of": datetime.now(UTC).isoformat(timespec="seconds"),
        "truncated": truncated,
        "notes": [SCOPE_NOTE, *notes],
    }


def _publication(patent: LibraryPatent) -> dict:
    # Public bibliographic fields only: never note/projects/tags/watch_rule_ids.
    return {
        "publication_number": patent.publication_number,
        "jurisdiction": patent.jurisdiction,
        "kind_code": patent.kind_code,
        "title": patent.title,
        "family_key": patent.family_key,
        "application_number": patent.application_number,
        "grant_number": patent.grant_number,
        "filing_date": _iso(patent.filing_date),
        "publication_date": _iso(patent.publication_date),
        "grant_date": _iso(patent.grant_date),
        "earliest_priority_number": patent.earliest_priority_number,
        "earliest_priority_date": _iso(patent.earliest_priority_date),
        "original_assignees": list(patent.original_assignees),
        "current_assignees": list(patent.current_assignees),
        "company_groups": list(patent.company_groups),
        "technology_topics": list(patent.technology_topics),
        "classifications": [
            {"system": item.system, "code": item.code, "is_main": item.is_main}
            for item in patent.classifications
        ],
        "has_pdf": preferred_library_pdf(patent) is not None,
    }


def _report(report: AnalysisReport) -> dict:
    receipts: set[str] = set()
    truncated = False

    def cap(numbers: tuple[str, ...]) -> dict:
        nonlocal truncated
        kept = numbers[:ROW_RECEIPT_LIMIT]
        truncated = truncated or len(numbers) > len(kept)
        receipts.update(kept)
        return {"publication_numbers": list(kept), "publication_count": len(numbers)}

    data = {
        "title": report.title,
        "workflow": report.workflow,
        "scope": report.scope,
        "generated_at": report.generated_at.isoformat(timespec="seconds"),
        "metrics": [
            {"label": m.label, "value": m.value, "formula": m.formula, **cap(m.publication_numbers)}
            for m in report.metrics
        ],
        "sections": [
            {
                "title": section.title,
                "columns": list(section.columns),
                "rows": [
                    {"cells": list(row.cells), **cap(row.publication_numbers)}
                    for row in section.rows
                ],
            }
            for section in report.sections
        ],
    }
    notes = list(report.notes)
    if truncated:
        notes.append(f"每行最多列出 {ROW_RECEIPT_LIMIT} 个公开号，publication_count 为完整数量。")
    return _envelope(data, receipts, truncated=truncated, notes=notes)


def _scope(topic, jurisdictions, from_date, to_date) -> AnalysisScope:
    try:
        return AnalysisScope(
            topic=topic or "",
            jurisdictions=tuple(value.upper() for value in jurisdictions),
            from_date=_parse_date(from_date, "from_date"),
            to_date=_parse_date(to_date, "to_date"),
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def _parse_date(value: str | None, name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{name} 必须是 YYYY-MM-DD 格式：{value}") from None


def _within_dates(patent: LibraryPatent, start: date | None, end: date | None) -> bool:
    if not start and not end:
        return True
    when = patent.filing_date or patent.earliest_priority_date or patent.publication_date
    if when is None:
        return False
    return (not start or when >= start) and (not end or when <= end)


def _public_text_match(patent: LibraryPatent, needle: str) -> bool:
    fields = [patent.publication_number, patent.title or ""]
    fields += patent.original_assignees + patent.current_assignees
    fields += tuple(item.code for item in patent.classifications)
    return any(needle in value.casefold() for value in fields)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def open_read_only(db_path: str | Path) -> LibraryTools:
    return LibraryTools(SQLitePatentLibrary(db_path, read_only=True))
