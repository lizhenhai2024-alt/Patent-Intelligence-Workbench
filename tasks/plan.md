# Engineering intelligence delivery plan

## Objective

Turn the existing suspension and damper patent workflow into five task-oriented outputs: patent landscape, company technology profile, competitive and route comparison, engineering-problem search planning, and watch brief. All analytical counts must be traceable to stored publications and must not infer legal assignees or family relationships.

## Stack and commands

- Python 3.12, SQLite, Tkinter, standard-library HTML rendering; no new runtime dependency.
- Full gate: `python scripts/ai_self_audit.py --full`.
- Focused tests: `python -m pytest tests/test_intelligence_workflows.py -q`.
- Lint: `python -m ruff check app tests`.
- Whitespace: `git diff --check`.

## Structure and style

- `app/intelligence/`: domain calculations, search planning, watch review, and offline report output.
- `app/desktop/`: a thin task entry point that delegates to the domain layer.
- `tests/`: deterministic offline fixtures using temporary SQLite databases.
- Keep functions typed and small; use frozen dataclasses for report data. Example: `Metric(label="Known families", value=len(keys), publication_numbers=receipts)`.

## Verification strategy

Test family deduplication, unresolved-family handling, exact company resolution, date basis, topic evidence, HTML escaping and receipts, editable search plans, watch-event review persistence, and desktop wiring. Then run the full offline release gate and inspect the final diff.

## Boundaries

- Always: preserve national publications, provenance, selected library root and existing user changes.
- Ask only if needed: new external services or a materially different legal-analysis scope.
- Never: infer an assignee from a folder, use substring company matching, label deterministic scores as probabilities, or generate legal opinions.

## Delivery sequence

1. Snapshot and analyze LocalLibrary records with explicit completeness caveats.
2. Render offline landscape, company-profile, and comparison reports with drill-down receipts.
3. Add search-strategy preview and Watch review state.
4. Wire the five workflows into the desktop UI and update the user guide.
5. Run focused and full gates; commit only validated scoped files.

## Baseline limitation

Before implementation, the full audit passes compilation and offline acceptance but fails Ruff on an unrelated untracked benchmark file, and test collection/desktop smoke because the available Python environment lacks `fitz` (PyMuPDF). Preserve these user files and distinguish baseline failures from new failures.
