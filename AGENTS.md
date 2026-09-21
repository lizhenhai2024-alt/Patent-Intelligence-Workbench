# AI Engineering Contract

This repository is an engineering patent-intelligence workbench, not a generic patent search UI.

Before changing code, read `docs/AI_PRODUCT_SPEC.md`. Treat it as the product contract.

## Mandatory agent workflow

1. Read the product spec and current git status.
2. Preserve unrelated local changes; never silently discard user work.
3. Run deterministic checks before guessing at bugs.
4. Rank findings: P0 data corruption/wrong attribution, P1 broken core workflow, P2 UX/maintainability.
5. Fix the smallest root cause, not the visible symptom.
6. Add or update a regression test for every behavioral fix.
7. Re-run lint, tests, desktop smoke, offline acceptance and `git diff --check`.
8. Commit only validated, scoped changes.

## Non-negotiable product invariants

- Primary engineering domain: suspension, dampers, valves, active/semi-active suspension and related structures.
- Search must distinguish patent number, text, company, company+technology and technology scope.
- Company identity uses exact entity-graph resolution; never use broad substring matching.
- `display_name` is UI text, `archive_name` is a filesystem folder name, and assignee names are legal metadata. Never substitute one for another.
- Patent family is a first-class analysis unit; keep national publications separately.
- LocalLibrary combines SQLite metadata with a user-selected filesystem PatentLibrary root.
- Folder names are weak evidence only. A folder match may assign a company group, but must not fabricate a legal assignee.
- Unknown company folders/documents go to `待归类`; do not guess ownership.
- Download naming follows the existing knowledge-base convention.
- Technology classifier scores are deterministic evidence scores, not probabilities.

## LocalLibrary and download rules

Canonical archive structure:

```text
<LocalLibrary root>/
  <archive company name>/
    Family_<family key>/
      <jurisdiction>/
        <year>-<publication>-<title>-<assignee>.pdf
```

Missing metadata degrades safely: omit unknown year/title/assignee rather than inventing values.

Single-patent Reader downloads and Family downloads must use the same filename builder.

The selected LocalLibrary root is the source of truth for file browsing, syncing and new downloads.
SQLite stores metadata/index/provenance; it must point to final archived PDF paths.

## Data/source rules

Provider order is replaceable. Local data should be used before unnecessary remote calls.
EPO credentials are optional enhancement, not a global requirement.
Do not scrape authentication/CAPTCHA-protected patent sites by bypassing controls.
Preserve provenance and original/current assignee distinctions.
Security-interest entities are not technical owners.
For acquired portfolios, scope the acquired technology rather than importing the owner's whole portfolio.

## Release gates

Required deterministic gate:
`python scripts/ai_self_audit.py --full`

A fix is not complete when only one unit test passes. The full offline workflow must remain valid:
Search -> Reader/Family -> Download -> Watch -> LocalLibrary -> Export.

Do not package or publish a formal release unless explicitly requested.
