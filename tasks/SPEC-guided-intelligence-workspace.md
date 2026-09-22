# Spec: Guided engineering intelligence workspace

## Objective

A suspension or damper R&D engineer can select a recognizable task, understand its evidence boundary, see whether the local collection is adequate, complete only relevant inputs, receive an explainable result and choose a next action. Optional AI interpretation must be deliberately enabled by the user and grounded in the generated report's publication receipts.

## Commands

- Focused: `python -m pytest tests/test_intelligence_workflows.py tests/test_intelligence_desktop.py -q`
- Full gate: `python scripts/ai_self_audit.py --full`
- Lint: `python -m ruff check app tests`
- Diff: `git diff --check`

## Project structure

- `app/intelligence/guidance.py`: task guidance and input contract.
- `app/intelligence/readiness.py`: deterministic LocalLibrary readiness summary.
- `app/intelligence/ai_interpreter.py`: opt-in OpenAI-compatible request boundary.
- `app/desktop/intelligence_tab.py`: task workspace presentation only.
- `tests/test_intelligence_workflows.py` and `tests/test_intelligence_desktop.py`: offline regression coverage.

## Code style

Use immutable typed results and clear source labels. For example:

```python
Readiness(level="empty", summary="本地库尚无已索引公开件", next_action="search")
```

## Testing strategy

Test guidance lookup, readiness from empty and tagged libraries, task-specific validation, evidence-packet-only AI input and network response parsing with mocked HTTP. Desktop tests assert the selected task changes instructions and that a local report can be generated without network access.

## Boundaries

- Always: retain exact company resolution, family/publication separation, provenance and LocalLibrary-first behavior.
- Ask first: adding a default AI provider, persistent secret storage, legal-analysis features, or a new external patent data source.
- Never: silently transmit local content, invent missing evidence, or present AI text as a legal conclusion.

## Success criteria

1. Each of the six workflows shows its purpose, required input, output and boundary before a user runs it.
2. An empty or weak LocalLibrary shows a specific next action rather than a misleading zero-result report.
3. Workflow validation names the missing task-specific condition instead of exposing a generic form error.
4. A completed report gives a clear continuation action and preserves its receipts.
5. AI analysis is impossible without an affirmative consent flag and a user-supplied endpoint/model; its request is limited to the bounded report evidence packet.
6. Existing offline workflows and release gates stay valid.
