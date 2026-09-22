"""User-facing contracts for bounded engineering-intelligence tasks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkflowGuide:
    workflow_id: str
    name: str
    purpose: str
    inputs: str
    output: str
    limit: str
    example: str
    needs_topic: bool = False
    needs_companies: int = 0
    needs_routes: int = 0
    uses_library: bool = True


_GUIDES = (
    WorkflowGuide(
        "landscape",
        "专利全景分析",
        "梳理一个技术主题在当前本地专利库中的家族、公司、地域和时间分布。",
        "可填写技术主题、国家/局和年份范围。",
        "可追溯到公开件的家族趋势、公司/技术节点与地域覆盖。",
        "只代表已索引的 LocalLibrary，不能代表完整市场或全球专利格局。",
        "例如：CDC 电磁阀减振器近五年的专利布局。",
    ),
    WorkflowGuide(
        "company-profile",
        "公司技术画像",
        "查看一家已登记公司组在指定技术范围内的本地专利布局。",
        "填写 1 家已登记公司组；可再填写技术主题和范围。",
        "公司组的家族、技术节点、时间趋势和代表公开件。",
        "公司组是精确实体搜索范围，不等同于法律权属或完整企业画像。",
        "例如：ASTEMO 在 pilot valve 方向的已收录专利。",
        needs_companies=1,
    ),
    WorkflowGuide(
        "competitive-landscape",
        "竞争格局分析",
        "对比多家已登记公司组在相同技术范围内的已收录专利。",
        "填写至少 2 家公司组；可再填写技术主题和范围。",
        "每组的家族和技术节点数量，以及交叠/相对独有家族的证据。",
        "家族交叠不表示合作、共同申请或市场竞争结论。",
        "例如：KYB、ASTEMO 在半主动减振器方向的本地布局。",
        needs_companies=2,
    ),
    WorkflowGuide(
        "route-comparison",
        "技术路线对比",
        "在同一数据范围内比较至少两条技术路线的家族覆盖与交叠。",
        "填写至少 2 个技术节点 ID 或精确名称；可再填写范围。",
        "路线的家族数、公司组、共同和相对独有的公开件证据。",
        "专利数量不证明路线成熟度、性能或商业优劣。",
        "例如：pilot_valve 与 semi_active 的家族覆盖。",
        needs_routes=2,
    ),
    WorkflowGuide(
        "problem-search",
        "工程问题检索",
        "把工程问题转换为可审阅、可编辑的多语言检索词。",
        "填写一个具体工程问题。",
        "词典来源标注的建议词组；确认后由你带入 Search。",
        "不会自动联网检索，也不会把词典匹配当作技术结论。",
        "例如：CDC 减振器低温响应变慢。",
        needs_topic=True,
        uses_library=False,
    ),
    WorkflowGuide(
        "watch-brief",
        "新专利监控简报",
        "汇总已归档 Watch 事件，并保留人工复核状态和备注。",
        "无需额外输入；先创建并运行 Watch 才会有事件。",
        "新家族、新成员和家族未解析公开件的事件清单。",
        "没有事件不代表没有新专利，只代表当前本地 Watch 未归档事件。",
        "例如：复核本周新增的半主动悬架专利。",
    ),
)

_BY_NAME = {guide.name: guide for guide in _GUIDES}
_BY_ID = {guide.workflow_id: guide for guide in _GUIDES}


def workflow_guides() -> tuple[WorkflowGuide, ...]:
    return _GUIDES


def workflow_guide(value: str) -> WorkflowGuide:
    try:
        return _BY_ID.get(value) or _BY_NAME[value]
    except KeyError as exc:
        raise ValueError(f"未知工程情报任务：{value}") from exc


def validate_task_inputs(
    guide: WorkflowGuide,
    *,
    topic: str,
    companies: tuple[str, ...],
    routes: tuple[str, ...],
) -> None:
    if guide.needs_topic and not topic.strip():
        raise ValueError(f"{guide.name}需要先描述一个具体工程问题")
    if len(companies) < guide.needs_companies:
        raise ValueError(f"{guide.name}需要填写至少 {guide.needs_companies} 家已登记公司组")
    if guide.needs_companies > 1 and len(set(companies)) < guide.needs_companies:
        raise ValueError(f"{guide.name}需要填写至少 {guide.needs_companies} 家不同公司组")
    if len(routes) < guide.needs_routes:
        raise ValueError(f"{guide.name}需要填写至少 {guide.needs_routes} 条不同技术路线")
    if guide.needs_routes > 1 and len(set(routes)) < guide.needs_routes:
        raise ValueError(f"{guide.name}需要填写至少 {guide.needs_routes} 条不同技术路线")
