# Roadmap

This file is the single place to look for "what's shipped, what's next, what's explicitly not planned." Each line links to its own SPEC/plan/todo set under `tasks/` rather than duplicating their content — read those before starting any item.

Known bugs/gaps not yet fixed (not roadmap items): [`tasks/ISSUES.md`](ISSUES.md).

## Shipped

- V1 core: search, family resolution, download center, Patent Watch, Local Library, desktop UI — see README "Current status" (phases P1-P7).
- Engineering-intelligence workflows, RC preview: patent landscape, company technology profile, competitive/route comparison, engineering-problem search planning, Watch brief — `tasks/SPEC-engineering-intelligence.md`.
- Guided intelligence workspace: per-task guidance, LocalLibrary readiness checks, consent-gated AI interpretation — `tasks/SPEC-guided-intelligence-workspace.md`, `tasks/todo-product-readiness.md`.
- Reader translation: generic HTTP (LibreTranslate-style) provider plus an optional DeepL provider for stronger JA/KO/DE translation — `app/core/translation_http.py`, configured in desktop Settings.
- Page content walkthrough (simulated first-time engineer usage) across all 9 desktop pages: fixed two real gaps found — Technology page had no search/filter box, no visual distinction between searchable (leaf) and category-only nodes, and silent status-bar-only feedback when a category node was searched (now a filter box, blue/gray node tags, and a `messagebox` dialog, consistent with the rest of the app); Watch page had no way to create a monitoring rule outside the fixed competitor template list in `app/watch/templates.py` (now a “新建监控规则” form — free-text company/applicant, technology keywords, cadence). Also fixed two async re-entrancy bugs (Intelligence tab run/AI-interpret buttons, Reader translation) and one stale-endpoint bug in the translation provider dropdown.

## In progress

- **Citation network** (forward/backward citations, EPO OPS primary source with Google Patents fallback, every edge source-attributed) — `tasks/SPEC-citation-network.md`, `tasks/plan-citation-network.md`, `tasks/todo-citation-network.md`. This is P0 item 1 of the backlog below and unblocks the technology-strength metric.

## 智能体路线（2026-09-23 决定）

Eureka 式任务智能体，按 `docs/AI_PRODUCT_SPEC.md` 第 11 节作为*受控*智能体构建。只用云端模型，可选多个；不做本地模型部署；没有智慧芽/incoPat 账号，所以 M1–M4 只使用本地库和现有数据源。

- **M1 — 本地库只读 MCP 工具**（已完成，2026-09-23 在真实本地库上验收通过）：`tasks/SPEC-agent-mcp.md`、`tasks/plan-agent-mcp.md`、`tasks/todo-agent-mcp.md`。
- **M2 — 软件内智能体运行框架**（代码和自动化测试已完成；待用两个真实模型配置人工验收）：每个智能体一个 Markdown 定义文件（`app/agents/definitions/*.md`，由代码校验）、多模型配置（OpenAI 兼容接口，用户可选，含小米 MiMo）、工具白名单、步数上限、标记无引用结论的证据校验、人工确认节点：`tasks/SPEC-agent-runtime.md`、`tasks/plan-agent-runtime.md`、`tasks/todo-agent-runtime.md`。开发文档划分：M3 的三个智能体合用一套 SPEC（每个一节）；M4 中查新/防侵权辅助检索和交底书各自单独一套 SPEC；TRIZ 在 M4 批次 SPEC 中占一节。
- **M3 — 首批三个智能体**：技术预研报告（即 `due_diligence_task`）、技术方案探索（专利 → 工程方案线索，五层解析）、对标分析（技术分支矩阵）。用 2–3 个真实课题盲测。
- **M4 — 第二批**：TRIZ（减振器领域矛盾矩阵）；交底书助手（云端模型，因此每次请求需确认，且不含本地库私有字段）；查新/防侵权*辅助检索*（候选清单 + 特征拆解 + 证据；X/Y/A 和风险判断由人做）。
- **M5 — 可选**：智慧芽开放平台 API/MCP 作为数据源适配器，仅在有账号和预算时做。
- 不计划：外观防侵权、标准提案查新、配方/材料智能体、审查意见答复（与减振器研发工程关联弱）。

## 市场对标 v2（2026-09-23，已批准）

`tasks/SPEC-market-benchmark-v2.md` 补充了悬架/减振器专属项目（减振器领域 CPC/FI/F-term 分类号映射、FI/F-term 提取、每件专利的五层工程记录、技术功效矩阵、法律状态事件、语义检索决策、Eureka 式智能体输入）。产品负责人于 2026-09-23 批准其开发顺序，取代下方"Queued next / Queued later"中的原顺序：

1. 完成 M2。
2. 本地专利全文索引（A0，2026-09-23 加入）：`tasks/SPEC-fulltext-index.md`、`tasks/plan-fulltext-index.md`、`tasks/todo-fulltext-index.md`；与分类号映射同期或之前完成。
3. 覆盖率检查与确认后补库（A0b，2026-09-23 加入；单次默认上限 200 件）：`tasks/SPEC-library-backfill.md`、`tasks/plan-library-backfill.md`、`tasks/todo-library-backfill.md`。
4. 分类号映射 + FI/F-term 提取。
5. 引证网络（已在开发中）。
6. 五层工程记录（吸收原 P0 第 4 项"权利要求特征拆解"）。
7. 技术功效矩阵。
8. M3 智能体。
9. 法律状态 + 剩余保护期视图；语义检索决策。
10. M4 智能体，之后视精力做 v2 中的 B8–B10、A5。

原 P0 第 2 项"技术强度指标"排在 M3 之后、与法律状态一起评估。

## Queued next (P0)

From `tasks/SPEC-market-benchmark-backlog.md`, ordered so later items can reuse earlier ones' data/provenance plumbing:

1. Citation network (in progress, above).
2. Transparent technology-strength metric — family size + citation count + remaining term + claim count, formula and inputs always shown; never framed as a probability or legal value judgment.
3. Remaining-term view — read-only expiry estimate from filing/grant date; no new data source needed, metadata-only.
4. Claim feature checklist — per-independent-claim technical-feature decomposition; explicitly a decomposition, never a comparison against another patent or product (stays clear of "claim chart"/infringement territory).

## Queued later (P1)

- Technology landscape clustering/map (offline CPC/IPC + keyword based, no external embedding API).
- User-editable technology taxonomy overlay on top of `technology_taxonomy.json`.
- LocalLibrary data-quality pass (near-duplicate assignee names, malformed dates; user-approved merges only).
- Per-publication AI Q&A, extending the existing consent-gated `app/intelligence/ai_interpreter.py` from whole-report interpretation to a single publication.

## Explicitly out of scope

FTO/infringement/novelty ("三性") conclusions or any risk/probability score implying a legal opinion; litigation analytics; SEP/standards-essential-patent analytics; docketing/annuity-fee management; multi-user collaboration workspace. Rationale for each: `tasks/SPEC-market-benchmark-backlog.md`.

## Design stance: workflows, plus bounded agents (revised 2026-09-23)

2026-09-23 修订：下方原立场对 P0/P1 待办项仍然有效；上方的智能体路线只在 `docs/AI_PRODUCT_SPEC.md` 第 11 节允许的范围内放宽（白名单只读工具、步数上限、必须带回执、X/Y/A 和风险由人判断）。

Every item above is implemented as a fixed, code-orchestrated task (Anthropic's "workflow" pattern), never as an autonomous agent loop that picks its own next query or revises its own conclusions — that would conflict directly with this product's no-fabrication/receipts boundary. Full reasoning and the task-by-task pattern mapping: `tasks/SPEC-agent-task-definitions.md`. That document also names one *not-yet-committed* forward-looking idea — exposing LocalLibrary read-only as agent-callable tools for external AI agents (Claude, LangChain, etc.), the way PatSnap/incoPat already do for their own data. It stays a "someday, needs its own SPEC" note until it's actually picked up.

## How to pick up an item

1. Read its SPEC (and plan/todo if they exist).
2. If only a SPEC exists (no plan/todo yet), write those first following the existing files' format — boundaries, verification strategy, capability map, build order.
3. Implement against the todo checklist, keep `python scripts/ai_self_audit.py --full` and `git diff --check` green, then check items off as they land — don't let the checklist drift out of sync with the code, the way `tasks/todo-product-readiness.md` did earlier.
