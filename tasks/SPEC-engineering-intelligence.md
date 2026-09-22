# Spec: Engineering intelligence workflows

## Objective

A suspension or damper R&D engineer can use existing LocalLibrary and Watch data to answer a bounded technical question, inspect the publications behind each finding, and save a readable offline report. The five entry points are patent landscape, company technology profile, competitive/route comparison, engineering-problem search planning, and Watch brief.

## Tech stack and commands

Python 3.12, existing SQLite/Tkinter application, standard-library HTML. Run `python scripts/ai_self_audit.py --full`, `python -m pytest tests/test_intelligence_workflows.py -q`, and `git diff --check`.

## Project structure

Analysis lives in `app/intelligence/`; the UI adapter lives in `app/desktop/`; deterministic fixtures live in `tests/`; user guidance lives in `docs/` and `README.md`.

## Code style

Use immutable typed result objects and deterministic sorting. For example, `Metric(label="Known families", value=len(keys), publication_numbers=tuple(sorted(numbers)))` carries the evidence for its count.

## Testing strategy

Offline SQLite fixtures cover every workflow and invariants. HTML report assertions check escaped user text, evidence links, scope and date basis. Watch-review tests reopen the database. Desktop tests exercise widget construction without public services.

## Boundaries

- Always use exact `CompanyRegistry` resolution and stored `company_groups`, never legal assignee guesses.
- Count known family keys once; list publications with unresolved family separately.
- Treat `filing_date`, then earliest priority, then publication date as labeled time-axis fallbacks.
- Technical evidence comes from title, assigned technology topic and CPC/IPC, not applicant names.
- Report data source, as-of date, query/scope, coverage limits, formulas and contributing publications.
- Preview search expansion for explicit user choice; do not silently search with new terms.
- Keep existing Watch baseline and event detection intact; review state is separate.
- No automatic infringement, FTO, validity, novelty, product performance or market-share conclusion.

## Success criteria

1. Landscape report shows known-family count, unresolved-publication count, national-publication count, year trend, company and technology distributions, and source receipts.
2. Company profile rejects unknown names and includes only exact stored company-group membership within a defined technology scope.
3. Comparison shows family-backed shared/distinct route or company coverage and representative publications.
4. Problem search presents editable, provenance-labeled multilingual terms before the existing search runs.
5. Watch brief distinguishes event types and lets users mark items pending, important or ignored with a note; the state persists.
6. A desktop user can run and save reports without credentials or network access.

## Open questions resolved from prior discussion

Analysis uses the selected local collection and labels its coverage. External market and legal conclusions require additional sources and are outside this delivery. The first milestone is the offline patent landscape; later workflows reuse its family-aware data model.
