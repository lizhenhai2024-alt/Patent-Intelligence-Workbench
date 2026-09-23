# Agent-task definitions benchmarked against mainstream practice

> **2026-09-23 决策更新：** 产品负责人批准了受控智能体（见 `docs/AI_PRODUCT_SPEC.md` 第 11 节和 `tasks/ROADMAP.md` 中的智能体路线）。下文对"自主智能体循环"的否定仍适用于不受限的循环；文末的 MCP 设想已作为 M1 实现（`tasks/SPEC-agent-mcp.md`）。

> **2026-09-23 规划复核：** 本文保留为历史模式对标。当前允许白名单、步数上限内的本地只读动态工具循环；禁止的是不受控权限和自动法律结论。文中将所有任务固定为 workflow、将 MCP 描述为未来想法的段落不再作为开发要求。M1 已实现，M2 待真实模型验收；当前状态、执行顺序与发送说明以 [ROADMAP](ROADMAP.md) 和产品契约第 11 节为准。

## Objective

Define what "Agent task" means for the Patent Intelligence Workbench, grounded in (1) Anthropic's own workflow-vs-agent vocabulary and (2) how mainstream patent platforms (PatSnap, incoPat) expose their data to AI agents. Produce a task taxonomy this product can adopt without breaking its existing boundaries (offline-first, LocalLibrary-scoped, consent-gated AI, no fabricated legal conclusions).

## Reference definitions

### Anthropic — "Building Effective Agents" (https://www.anthropic.com/engineering/building-effective-agents)

- **Workflow**: LLMs and tools orchestrated through *predefined code paths*. Control flow is fixed; the LLM (if used at all) fills in a step, it does not decide the next step.
- **Agent**: the LLM *dynamically directs its own process and tool use*, keeping control over how a task is accomplished, evaluated against environment feedback each turn, with checkpoints and termination conditions.
- Anthropic's explicit guidance: start with the simplest solution, add agentic complexity only when it demonstrably improves outcomes, and prefer workflows when the path is predictable — which is exactly this product's situation (deterministic, receipt-carrying, no-fabrication requirements).
- Named patterns, in increasing autonomy: prompt chaining, routing, parallelization (sectioning / voting), orchestrator-workers, evaluator-optimizer, and — highest autonomy — the autonomous agent loop (tool call → environment feedback → next decision, with checkpoints).

### PatSnap — "Patent API for AI Agents" (https://www.patsnap.com/resources/blog/articles/patent-api-for-ai-agents-add-live-patent-search-to-your-agent-workflows/) and the `patsnap/skills` GitHub repo

PatSnap ships its patent database as a set of **agent-callable tools**, not as a chat UI: natural-language semantic search, abstract retrieval, active-patent filtering, normalized-company filing tracking. Design rules they state: accept natural language directly (no special query syntax the agent must learn), return structured data ready to hand back to the model, and answer from live database calls rather than model memory (to avoid hallucinated citations). They also publish `patsnap/skills` — packaged "procedural knowledge" skill files third-party agents (LangChain, Claude, etc.) load to know how to use the data correctly.

### incoPat — AI Agents product (https://agent.incopat.com/)

Exposes simple/semantic/advanced/image search, result statistics, record detail view and download as agent-usable actions. Public page does not show autonomous monitoring/report-generation agent tasks yet, so it is a narrower "search-as-a-tool" surface than PatSnap's.

## What this means for this product

This product's own boundaries (`docs/AI_PRODUCT_SPEC.md`: never infer assignees, never fabricate metadata, no automatic legal conclusions; `tasks/plan.md`: deterministic scores, receipts, provenance) put it firmly in Anthropic's **workflow** category by design, not the autonomous-agent category — and that is the right call for this domain: an autonomous agent that decides its own next patent-database query and writes its own conclusions is exactly the "black-box legal/technical judgment" this product has deliberately ruled out. So "Agent task" here should mean **a named, bounded workflow task**, not an LLM given free rein over tool selection.

## Proposed Agent Task taxonomy for this product

Each task below is defined the way Anthropic's guide defines a workflow step: fixed goal, fixed allowed actions, explicit human checkpoint, explicit termination/output. The "pattern" column names which Anthropic pattern the implementation should follow — all code-orchestrated, none are a free autonomous loop.

| Task id | Goal | Pattern | Allowed actions (existing or backlog) | Human checkpoint | Output |
| --- | --- | --- | --- | --- | --- |
| `landscape_task` | Patent-landscape snapshot for a topic/date range | Prompt chaining (scope → query → aggregate → render) | `analysis.py` landscape | none required, already offline | HTML report + receipts |
| `company_profile_task` | One company's technology routes | Prompt chaining | `analysis.py` company profile | none | HTML report + receipts |
| `comparison_task` | Compare N companies/routes | Parallelization (sectioning: each company/route resolved independently, then merged) | `analysis.py` comparison | none | HTML report + receipts |
| `search_planning_task` | Turn an engineering problem into search terms | Prompt chaining, with an explicit gate | `search_plan.py` | **required**: user must approve terms before they reach Search (already implemented) | editable term list |
| `watch_review_task` | Triage new-family/new-member Watch events | Routing (classify event type → route to pending/important/ignored) | `watch_review.py` | required: user assigns the label | reviewed Watch state |
| `due_diligence_task` (new, P1 candidate) | One-shot "tell me what we know about company X in technology Y" combining landscape + company profile + comparison + citation network (backlog P0 item) into a single consolidated report | **Orchestrator-workers**, but the orchestrator is fixed code, not an LLM: it always calls the same four sub-tasks in the same order and concatenates their receipts — never lets a model choose which sub-task to skip or which company to add | the four tasks above, plus the new citation-network view | none beyond the underlying tasks' own gates | one combined HTML report, each section still carrying its own receipts |
| `evidence_qa_task` (already exists as `ai_interpreter.py`, extend per prior backlog item) | Answer a question about one report's findings | Evaluator-optimizer shape *without* the optimizer loop — a single grounded generation, not iterative self-critique, to avoid the model quietly revising its own "evidence" | opt-in AI interpretation, evidence-packet only | **required**: explicit per-request consent (already implemented) | labeled interpretation text, never treated as a new fact |

Two patterns from Anthropic's list are deliberately **not** adopted: **evaluator-optimizer loops** (an LLM iteratively revising another LLM's output over multiple turns would drift from the original evidence — this product's `Boundaries` sections already forbid treating iterative scores as calibrated probabilities) and the **autonomous agent loop** (letting a model choose its own next database query or conclusion is precisely the "legal opinion" / "inferred assignee" risk the product's specs rule out). This should be stated as a deliberate design decision, not an oversight, if this taxonomy goes into the product spec.

## Optional forward-looking idea: expose LocalLibrary as agent-callable tools

Separate from the internal task taxonomy above: PatSnap and incoPat both now ship their patent data as tools *external* agents (LangChain, Claude, ChatGPT) can call directly, rather than only a UI. This product could do the same for a *single user's own LocalLibrary* — e.g. a small local MCP server exposing `landscape`, `company_profile`, `citation_network` etc. as callable tools, so the user could drive their own local patent research from Claude or another agent instead of only from the Tkinter UI. This is a meaningfully different feature (a new integration surface, not a new analysis capability) and would need its own SPEC/plan/todo set and an explicit boundary conversation (e.g., does an external agent get read-only access, does it inherit the same consent/evidence rules) before any code is written — flagging it here only because it directly answers "what do mainstream players call an Agent task," not as a committed plan.

## Sources

- Building Effective Agents (Anthropic): https://www.anthropic.com/engineering/building-effective-agents
- Patent API for AI Agents (PatSnap): https://www.patsnap.com/resources/blog/articles/patent-api-for-ai-agents-add-live-patent-search-to-your-agent-workflows/
- Best Patent API for LangChain & Claude Agents comparison (PatSnap): https://www.patsnap.com/resources/blog/articles/best-patent-api-for-langchain-claude-agents-2026-comparison/
- patsnap/skills (GitHub): https://github.com/patsnap/skills
- incoPat AI Agents: https://agent.incopat.com/

## Next step

If `due_diligence_task` looks worth building, it needs its own SPEC/plan/todo (per this repo's existing pattern) before code — in particular a decision on how its combined report presents four separate receipts sets without implying they were cross-validated against each other (they weren't; each sub-task's evidence stays scoped to itself).
