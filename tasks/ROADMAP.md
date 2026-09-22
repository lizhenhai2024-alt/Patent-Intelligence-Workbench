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

## Design stance: workflows, not autonomous agents

Every item above is implemented as a fixed, code-orchestrated task (Anthropic's "workflow" pattern), never as an autonomous agent loop that picks its own next query or revises its own conclusions — that would conflict directly with this product's no-fabrication/receipts boundary. Full reasoning and the task-by-task pattern mapping: `tasks/SPEC-agent-task-definitions.md`. That document also names one *not-yet-committed* forward-looking idea — exposing LocalLibrary read-only as agent-callable tools for external AI agents (Claude, LangChain, etc.), the way PatSnap/incoPat already do for their own data. It stays a "someday, needs its own SPEC" note until it's actually picked up.

## How to pick up an item

1. Read its SPEC (and plan/todo if they exist).
2. If only a SPEC exists (no plan/todo yet), write those first following the existing files' format — boundaries, verification strategy, capability map, build order.
3. Implement against the todo checklist, keep `python scripts/ai_self_audit.py --full` and `git diff --check` green, then check items off as they land — don't let the checklist drift out of sync with the code, the way `tasks/todo-product-readiness.md` did earlier.
