"""Family-aware analysis over the verified LocalLibrary collection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.core.company_registry import CompanyRegistry
from app.core.technology_classifier import TechnologyClassifier
from app.core.technology_dictionary import TechnologyDictionary
from app.core.technology_taxonomy import TechnologyTaxonomy
from app.library.models import LibraryPatent, LibraryQuery
from app.library.store import SQLitePatentLibrary


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    topic: str = ""
    jurisdictions: tuple[str, ...] = ()
    from_date: date | None = None
    to_date: date | None = None

    def __post_init__(self) -> None:
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("开始日期不能晚于结束日期")


@dataclass(frozen=True, slots=True)
class Metric:
    label: str
    value: int
    formula: str
    publication_numbers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportRow:
    cells: tuple[str, ...]
    publication_numbers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    columns: tuple[str, ...]
    rows: tuple[ReportRow, ...]


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    title: str
    workflow: str
    scope: str
    generated_at: datetime
    metrics: tuple[Metric, ...]
    sections: tuple[ReportSection, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FamilyRecord:
    key: str
    members: tuple[LibraryPatent, ...]
    date: date | None
    date_basis: str
    company_groups: tuple[str, ...]
    topics: tuple[str, ...]

    @property
    def numbers(self) -> tuple[str, ...]:
        return tuple(sorted(p.publication_number for p in self.members))


class AnalysisService:
    def __init__(
        self,
        store: SQLitePatentLibrary,
        *,
        registry: CompanyRegistry | None = None,
        classifier: TechnologyClassifier | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or CompanyRegistry.default()
        self.classifier = classifier or TechnologyClassifier()
        self.dictionary = TechnologyDictionary.default()
        self.taxonomy = TechnologyTaxonomy.default()

    def landscape(self, scope: AnalysisScope) -> AnalysisReport:
        patents, families, unresolved = self._snapshot(scope)
        metrics = self._base_metrics(patents, families, unresolved)
        return self._report(
            "专利全景分析",
            "landscape",
            scope,
            metrics,
            self._standard_sections(families, unresolved),
        )

    def company_profile(self, scope: AnalysisScope, company: str) -> AnalysisReport:
        group = self.registry.get(company)
        patents, families, unresolved = self._snapshot(scope, company_ids=(group.group_id,))
        sections = self._standard_sections(families, unresolved)
        sections += (self._representatives(families),)
        return self._report(
            f"公司技术画像：{group.display_name}",
            "company-profile",
            scope,
            self._base_metrics(patents, families, unresolved),
            sections,
            extra_scope=f"公司组：{group.group_id}（精确解析）",
        )

    def competitive_landscape(
        self, scope: AnalysisScope, companies: tuple[str, ...]
    ) -> AnalysisReport:
        groups = self._resolve_companies(companies)
        patents, families, unresolved = self._snapshot(
            scope, company_ids=tuple(group.group_id for group in groups)
        )
        selected_ids = {group.group_id for group in groups}
        rows = []
        overlap_rows = []
        unique_rows = []
        for group in groups:
            related = tuple(f for f in families if group.group_id in f.company_groups)
            overlapping = tuple(
                f for f in related if len(set(f.company_groups).intersection(selected_ids)) > 1
            )
            exclusive = tuple(
                f
                for f in related
                if set(f.company_groups).intersection(selected_ids) == {group.group_id}
            )
            rows.append(
                ReportRow(
                    (
                        group.display_name,
                        str(len(related)),
                        str(len({t for f in related for t in f.topics})),
                    ),
                    _numbers(related),
                )
            )
            overlap_rows.append(
                ReportRow((group.display_name, str(len(overlapping))), _numbers(overlapping))
            )
            unique_rows.append(
                ReportRow((group.display_name, str(len(exclusive))), _numbers(exclusive))
            )
        sections = (
            ReportSection("公司对比", ("公司组", "已知家族", "技术节点"), tuple(rows)),
            ReportSection(
                "交叠家族（不代表合作或共同申请）",
                ("公司组", "与其他所选公司组交叠"),
                tuple(overlap_rows),
            ),
            ReportSection(
                "独有家族（仅相对所选公司组）",
                ("公司组", "仅该组"),
                tuple(unique_rows),
            ),
            *self._standard_sections(families, unresolved),
        )
        return self._report(
            "竞争格局分析",
            "competitive-landscape",
            scope,
            self._base_metrics(patents, families, unresolved),
            sections,
            extra_scope="公司组：" + "、".join(group.group_id for group in groups),
        )

    def route_comparison(self, scope: AnalysisScope, routes: tuple[str, ...]) -> AnalysisReport:
        route_ids = self._resolve_routes(routes)
        patents, families, unresolved = self._snapshot(scope)
        rows = []
        for route_id in route_ids:
            related = tuple(f for f in families if route_id in f.topics)
            rows.append(
                ReportRow(
                    (
                        self._route_name(route_id),
                        str(len(related)),
                        str(len({g for f in related for g in f.company_groups})),
                    ),
                    _numbers(related),
                )
            )
        shared = tuple(f for f in families if all(r in f.topics for r in route_ids))
        exclusive_rows = []
        for route_id in route_ids:
            others = set(route_ids) - {route_id}
            exclusive = tuple(
                f for f in families if route_id in f.topics and not others.intersection(f.topics)
            )
            exclusive_rows.append(
                ReportRow((self._route_name(route_id), str(len(exclusive))), _numbers(exclusive))
            )
        sections = (
            ReportSection("技术路线对比", ("路线", "已知家族", "公司组"), tuple(rows)),
            ReportSection(
                "共同覆盖的家族",
                ("家族键", "公开成员", "技术节点"),
                tuple(
                    ReportRow((f.key, "、".join(f.numbers), "、".join(f.topics)), f.numbers)
                    for f in shared
                ),
            ),
            ReportSection(
                "路线独有家族（仅相对所选路线）",
                ("路线", "已知家族"),
                tuple(exclusive_rows),
            ),
            self._representatives(families),
        )
        return self._report(
            "技术路线对比",
            "route-comparison",
            scope,
            self._base_metrics(patents, families, unresolved),
            sections,
            extra_scope="路线：" + "、".join(route_ids),
        )

    def _snapshot(
        self, scope: AnalysisScope, *, company_ids: tuple[str, ...] = ()
    ) -> tuple[tuple[LibraryPatent, ...], tuple[FamilyRecord, ...], tuple[LibraryPatent, ...]]:
        # The limit follows the current database count so no silent top-N truncation enters reports.
        all_patents = self.store.query(LibraryQuery(limit=max(1, self.store.count_patents())))
        selected = tuple(
            p
            for p in all_patents
            if self._within_scope(p, scope)
            and (not company_ids or set(p.company_groups).intersection(company_ids))
        )
        grouped: dict[str, list[LibraryPatent]] = defaultdict(list)
        unresolved = []
        for patent in selected:
            if patent.family_key:
                grouped[patent.family_key].append(patent)
            else:
                unresolved.append(patent)
        families = tuple(
            self._family(key, tuple(members)) for key, members in sorted(grouped.items())
        )
        return selected, families, tuple(sorted(unresolved, key=lambda p: p.publication_number))

    def _within_scope(self, patent: LibraryPatent, scope: AnalysisScope) -> bool:
        if scope.jurisdictions and patent.jurisdiction.upper() not in {
            value.upper() for value in scope.jurisdictions
        }:
            return False
        when = patent.filing_date or patent.earliest_priority_date or patent.publication_date
        if scope.from_date and (when is None or when < scope.from_date):
            return False
        if scope.to_date and (when is None or when > scope.to_date):
            return False
        if not scope.topic.strip():
            return True
        needle = scope.topic.strip().casefold()
        topics = self._patent_topics(patent)
        return (
            needle in (patent.title or "").casefold()
            or needle in {value.casefold() for value in topics}
            or any(needle == self._route_name(value).casefold() for value in topics)
        )

    def _patent_topics(self, patent: LibraryPatent) -> tuple[str, ...]:
        inferred = self.classifier.classify(
            text=patent.title or "",
            classifications=tuple(item.code for item in patent.classifications),
        )
        return tuple(sorted(set(patent.technology_topics) | {m.node_id for m in inferred}))

    def _family(self, key: str, members: tuple[LibraryPatent, ...]) -> FamilyRecord:
        for field, label in (
            ("filing_date", "申请日"),
            ("earliest_priority_date", "最早优先权日"),
            ("publication_date", "公开日"),
        ):
            dates = [value for patent in members if (value := getattr(patent, field))]
            if dates:
                when, basis = min(dates), label
                break
        else:
            when, basis = None, "日期缺失"
        return FamilyRecord(
            key,
            members,
            when,
            basis,
            tuple(sorted({g for p in members for g in p.company_groups})),
            tuple(sorted({t for p in members for t in self._patent_topics(p)})),
        )

    @staticmethod
    def _base_metrics(
        patents: tuple[LibraryPatent, ...],
        families: tuple[FamilyRecord, ...],
        unresolved: tuple[LibraryPatent, ...],
    ) -> tuple[Metric, ...]:
        return (
            Metric(
                "已知专利族",
                len(families),
                "按非空 family_key 去重；仅统计已解析家族",
                _numbers(families),
            ),
            Metric(
                "国家公开件",
                len(patents),
                "按 publication_number 计数，不进行家族去重",
                tuple(sorted(p.publication_number for p in patents)),
            ),
            Metric(
                "家族未解析公开件",
                len(unresolved),
                "family_key 缺失；不推定为单件家族",
                tuple(p.publication_number for p in unresolved),
            ),
        )

    def _standard_sections(
        self, families: tuple[FamilyRecord, ...], unresolved: tuple[LibraryPatent, ...]
    ) -> tuple[ReportSection, ...]:
        by_year: dict[str, list[FamilyRecord]] = defaultdict(list)
        by_company: dict[str, list[FamilyRecord]] = defaultdict(list)
        by_topic: dict[str, list[FamilyRecord]] = defaultdict(list)
        by_jurisdiction: dict[str, list[LibraryPatent]] = defaultdict(list)
        for family in families:
            by_year[str(family.date.year) if family.date else "日期缺失"].append(family)
            for company in family.company_groups:
                by_company[company].append(family)
            for topic in family.topics:
                by_topic[topic].append(family)
            for patent in family.members:
                by_jurisdiction[patent.jurisdiction].append(patent)
        return (
            ReportSection(
                "申请趋势（家族）",
                ("年份", "已知家族", "日期口径"),
                tuple(
                    ReportRow(
                        (year, str(len(items)), "；".join(sorted({f.date_basis for f in items}))),
                        _numbers(items),
                    )
                    for year, items in sorted(by_year.items())
                ),
            ),
            ReportSection(
                "公司布局（家族）",
                ("公司组", "已知家族"),
                tuple(
                    ReportRow((self._company_name(group), str(len(items))), _numbers(items))
                    for group, items in sorted(
                        by_company.items(), key=lambda entry: (-len(entry[1]), entry[0])
                    )
                ),
            ),
            ReportSection(
                "技术节点（家族）",
                ("技术节点", "已知家族"),
                tuple(
                    ReportRow((self._route_name(topic), str(len(items))), _numbers(items))
                    for topic, items in sorted(
                        by_topic.items(), key=lambda entry: (-len(entry[1]), entry[0])
                    )
                ),
            ),
            ReportSection(
                "地域覆盖（国家公开件）",
                ("国家/局", "公开件"),
                tuple(
                    ReportRow(
                        (country, str(len(items))),
                        tuple(sorted(p.publication_number for p in items)),
                    )
                    for country, items in sorted(by_jurisdiction.items())
                ),
            ),
            ReportSection(
                "家族未解析",
                ("公开号", "标题"),
                tuple(
                    ReportRow(
                        (p.publication_number, p.title or "（标题缺失）"), (p.publication_number,)
                    )
                    for p in unresolved
                ),
            ),
        )

    @staticmethod
    def _representatives(families: tuple[FamilyRecord, ...]) -> ReportSection:
        return ReportSection(
            "代表专利族",
            ("家族键", "公开成员", "最早日期"),
            tuple(
                ReportRow(
                    (f.key, "、".join(f.numbers), f.date.isoformat() if f.date else "日期缺失"),
                    f.numbers,
                )
                for f in sorted(
                    families, key=lambda value: (value.date or date.min, value.key), reverse=True
                )[:30]
            ),
        )

    def _company_name(self, group_id: str) -> str:
        try:
            return self.registry.get(group_id).display_name
        except KeyError:
            return group_id + "（未登记组）"

    def _route_name(self, route_id: str) -> str:
        try:
            return self.taxonomy.find(route_id).name
        except KeyError:
            for topic in self.dictionary.topics:
                if topic.topic_id == route_id:
                    return topic.display_name
        return route_id

    def _resolve_routes(self, routes: tuple[str, ...]) -> tuple[str, ...]:
        if len(routes) < 2:
            raise ValueError("至少选择两条技术路线")
        resolved = []
        for value in routes:
            needle = value.strip().casefold()
            matches = [
                topic.topic_id
                for topic in self.dictionary.topics
                if needle in {topic.topic_id.casefold(), topic.display_name.casefold()}
            ]
            matches += [
                node.node_id
                for node in self.classifier._iter_nodes(self.taxonomy.roots)
                if needle in {node.node_id.casefold(), node.name.casefold()}
            ]
            if not matches:
                raise ValueError(f"未知技术路线：{value}")
            resolved.append(matches[0])
        if len(set(resolved)) < 2:
            raise ValueError("请选择两条不同技术路线")
        return tuple(dict.fromkeys(resolved))

    def _resolve_companies(self, companies: tuple[str, ...]):
        if len(companies) < 2:
            raise ValueError("至少选择两家公司")
        groups = tuple(self.registry.get(value.strip()) for value in companies)
        if len({group.group_id for group in groups}) < 2:
            raise ValueError("请选择两家不同公司")
        return groups

    @staticmethod
    def _report(
        title: str,
        workflow: str,
        scope: AnalysisScope,
        metrics: tuple[Metric, ...],
        sections: tuple[ReportSection, ...],
        *,
        extra_scope: str = "",
    ) -> AnalysisReport:
        scope_parts = [f"主题：{scope.topic or '全部本地记录'}"]
        if scope.jurisdictions:
            scope_parts.append("国家/局：" + "、".join(scope.jurisdictions))
        if scope.from_date or scope.to_date:
            scope_parts.append(f"日期：{scope.from_date or '不限'} 至 {scope.to_date or '不限'}")
        if extra_scope:
            scope_parts.append(extra_scope)
        return AnalysisReport(
            title,
            workflow,
            "；".join(map(str, scope_parts)),
            datetime.now(UTC),
            metrics,
            sections,
            (
                "数据范围仅限当前 LocalLibrary 已索引记录；缺失数据不补猜。",
                "技术节点来自已存分类和标题/CPC/IPC 的确定性证据评分；公司组来自精确实体映射。",
                "公司和技术分布可一族多归属，各行不可直接求和。",
                "申请趋势优先使用申请日，缺失时依次回退到最早优先权日和公开日；各行注明日期口径。",
                "本报告用于工程情报，不构成新颖性、FTO、侵权、有效性或市场份额结论。",
            ),
        )


def _numbers(families: tuple[FamilyRecord, ...] | list[FamilyRecord]) -> tuple[str, ...]:
    return tuple(sorted({number for family in families for number in family.numbers}))
