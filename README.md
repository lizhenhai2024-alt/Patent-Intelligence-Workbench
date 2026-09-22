# Patent Intelligence Workbench

面向悬架与减振器研发工程师的专利情报工作台：从技术问题出发，形成可追溯到专利族、原始文献和工程证据的分析结果。

## V1.0 scope

- Patent Search: 文字、专利号、公司 + 技术
- Patent Family: priority、Simple/INPADOC family、CN/JP/EP/US/WO/KR family members
- Download Center: 单件、整族、批量 PDF 下载与失败重试
- Patent Watch: 公司、公司 + 技术、新公开、新增 family member（预置模板规则以外，可在 Watch 页面直接新建任意公司/技术关键词的自定义监控规则）
- Local Library: 收藏、标签、公司/技术分类、Excel/CSV 导出
- Company Entity Graph: 历史申请人、IP holding entity、并购/技术前身、专利权属关系

正式 Prior Art / 查新、X/Y/A、Claim Chart 和 FTO 不进入 V1.0。

## Engineering-intelligence workflows (RC preview)

The desktop RC includes LocalLibrary-backed entry points for the workflows below. They extend the Search → Reader/Family → Download → Watch → LocalLibrary → Export loop. They are a guided engineering-analysis preview, not a replacement for professional patent, legal or market research.

| Priority | Workflow | Current output |
| --- | --- | --- |
| 1 | 专利全景分析 | Family-level filing trends, companies, jurisdictions, technology branches, representative publications, and traceable counts. |
| 2 | 公司技术画像 | One exactly resolved company group's suspension-technology routes, key families, changes over time, and evidence. |
| 3 | 竞争格局与技术路线对比 | Shared and distinct technical approaches across defined companies or routes, with source records and open questions. |
| 4 | 工程问题检索 | Editable multilingual terms and search scope derived from an engineering problem, followed by patent-backed solution leads. |
| 5 | 监控简报 | New-family and new-member events grouped into a reviewable, annotatable action list. |

Each task now states what it needs, what it will output and its limits before it runs. The workspace also checks the current LocalLibrary and directs an empty or weak collection to Search or Local Library instead of presenting a misleading zero-result report. **专利全景分析** accepts a topic, jurisdictions and time window and generates an offline-readable HTML report with publication receipts, data source, date and counting method. Known-family and national-publication counts remain distinct; missing family keys are shown separately.

AI interpretation is optional: a user must provide an OpenAI-compatible Chat Completions endpoint, a model and a key, then explicitly confirm that the current report's evidence packet may be sent. Keys are not persisted by this feature. No local patent data is sent to an AI service by default.

Each workflow should state its purpose, suitable use, required inputs, outputs, data sources and as-of date, method, example questions, and review limits. Materials and engineering knowledge may help explain mechanisms or frame a search, but a patent-data view alone cannot establish product performance, supply capacity, or market share.

Product-feature-to-claim evidence mapping, DFMEA, validation planning, and R&D initiation are later extensions that require additional product, design, or test evidence. Automated infringement, FTO, validity, novelty, or other formal legal conclusions remain outside the workbench.

See [Engineering Intelligence guide](docs/ENGINEERING_INTELLIGENCE.md) for task inputs, data-readiness limits and the optional AI handoff.

Reader also has optional machine translation for non-English full text (JA/KO/DE and others): a generic LibreTranslate-style HTTP endpoint, DeepL for stronger JA/KO/DE quality, or an OpenAI-compatible Chat Completions endpoint you configure yourself. Configure it in desktop Settings; nothing is sent anywhere until you do.

## Core jurisdictions

CN / JP / EP / US / WO / KR

JP is a first-class jurisdiction. The classification schema is an open system/code model reserved for IPC, CPC, FI, F-term and Theme Code; dedicated JPO FI/F-term/Theme Code parsers are not yet first-class (CPC/IPC are extracted by the current providers).

## Default monitored damper / suspension companies

- Hitachi Astemo
- KYB
- Tenneco / Monroe
- ZF / Sachs
- BWI
- HL Mando
- thyssenkrupp BILSTEIN
- Multimatic
- Öhlins
- ClearMotion
- Hyundai MOBIS
- AISIN
- Schaeffler
- 富奥东机工 / 一汽东机工

JTEKT is not part of the default core damper watch list.

## Architecture principles

1. Normalize before search.
2. Treat a patent family as the primary analysis unit.
3. Separate original assignee, current assignee and non-technical security interests.
4. Model company history as an entity graph, not as a flat alias list.
5. Keep provider adapters replaceable; downloading must support source fallback.
6. All release builds must pass automated tests.

## AI maintenance contract

AI-assisted development must follow `AGENTS.md` and `docs/AI_PRODUCT_SPEC.md`.
Run the deterministic full audit before treating a repair as complete:

```bash
python scripts/ai_self_audit.py --full
```

The AI contract separates UI display names, filesystem archive names and legal assignee metadata,
and defines LocalLibrary, company/entity, filename and autonomous-repair invariants.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

### Optional acquisition engine

For public web pages and local files:

```bash
python -m pip install -e ".[dev,acquisition]"
python -m playwright install chromium
```

Routing is intentionally explicit: local files use MarkItDown, normal public web pages use
Crawl4AI, and Browser Use is an optional separate enhancement for interactive pages. Browser
automation is not intended to bypass authentication, CAPTCHA, robots policies, or other access
controls.

## Current status

Core V1 implementation is now end-to-end:

- P1 Foundation: patent-number normalization, entity graph, CI
- P2 Family Providers: DOCDB simple / INPADOC extended family, EPO OPS, JPO validation client
- P3 Search: patent number, text, company, company + technology, multilingual terminology
- P4 Download Center: family PDF batch download, fallback policy, retry/cache/manifest
- P5 Patent Watch: baseline, new-family/new-member detection, SQLite state, scheduler
- P6 Local Library: family/publication persistence, favorites, tags, company/technology classification, watch-rule links, PDFs, provenance, CSV/XLSX
- P7 Desktop: lightweight Windows UI, secure EPO credentials, editable library details, automatic EXE build

Fresh desktop installations use one local `workbench.db` for Patent Library and Patent Watch tables. Existing legacy database paths are preserved to avoid silent data loss.

Current phase: **P8 V1 Release Candidate hardening** — end-to-end acceptance, release documentation, packaging verification and optional credentialed provider smoke tests.

See `docs/ARCHITECTURE.md` and `docs/DOWNLOAD_SOURCES.md` for the frozen V1 architecture and source policy.

Release-candidate documentation:

- `docs/QUICKSTART.md`
- `docs/RELEASE_CHECKLIST.md`
- `CHANGELOG.md`

## Roadmap

What's shipped, what's next, and what's explicitly not planned lives in one place: [`tasks/ROADMAP.md`](tasks/ROADMAP.md). It links out to each feature's own SPEC/plan/todo set rather than duplicating them here.


## License

MIT
