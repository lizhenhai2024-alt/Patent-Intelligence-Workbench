# AI Product Specification

## 1. Machine-readable product intent

```yaml
product: Patent Intelligence Workbench
primary_user: suspension/damper R&D engineer
primary_domain:
  - passive damper
  - CDC / semi-active damper
  - active suspension
  - air suspension
  - active anti-roll
  - damper valve / seal / structure / NVH / manufacturing
product_purpose: turn patent sources and local PDFs into auditable engineering intelligence
primary_loop:
  - search
  - understand
  - family
  - download
  - organize
  - compare
  - monitor
truth_priority:
  - local_library_verified_metadata
  - authoritative_provider_metadata
  - public_provider_metadata
  - filename_or_folder_inference
forbidden_truth_source:
  - guessed_company_ownership
  - fabricated_metadata
```

## 2. Core user outcomes

The application must let an engineer:

1. Find patents by publication number, engineering text, company, portfolio scope or technology.
2. Read structured patent content: title, abstract, claims, description, figures and classifications.
3. Understand technical relevance through an explainable suspension-engineering taxonomy.
4. Resolve and inspect simple/extended patent families without losing national publications.
5. Download PDFs reliably and archive them into the user's existing PatentLibrary convention.
6. Reuse a local patent collection without re-downloading or duplicating files.
7. Monitor competitors and detect new families versus new members of existing families.
8. Preserve evidence, provenance and ownership history for later engineering analysis.

Formal legal FTO/novelty opinions remain outside the product's automatic conclusions.

## 3. Domain objects and semantic separation

`Publication`: one national publication/grant.

`PatentFamily`: normalized family relationship; simple and INPADOC/extended are distinct.

`CompanyGroup`: engineering ownership/search group.

`display_name`: human-facing label only.

`archive_name`: canonical filesystem company folder only.

`assignee`: patent metadata from a source; never derive it from a display label.

`TechnologyNode`: engineering taxonomy node with query terms and classification evidence.

`TechnologyMatch.score`: deterministic evidence score; never label it probability/confidence unless a calibrated model exists.

`LocalLibrary`: SQLite metadata/index + user-selected filesystem root.

`Evidence`: traceable source material linked to a publication/company/technology topic.

## 4. Search contract

Routing priority:

1. Exact patent/publication number.
2. Exact registered company/entity name.
3. Explicit company + technology.
4. Technology/topic query.
5. General text.

Company matching must be exact after normalization. Never resolve a company because one string merely contains another.

Company-wide search, suspension-portfolio search and specific-technology search are different scopes.

Search result tagging may use title + abstract + CPC/IPC. Applicant text is identity context, not technical evidence.

## 5. LocalLibrary contract

The user chooses the PatentLibrary root. The setting persists across launches.

Selecting/syncing a root must:

- scan company folders;
- index CSV/PDF records into SQLite;
- attach existing PDF paths without moving originals;
- map known folder names to company groups;
- leave unknown folders unmapped and report them;
- never invent assignee metadata from a folder name.

New downloads must be written under the selected root.

When no PDF is selected, "open library folder" must open the selected root, not an internal legacy download path.

## 6. Archive and filename contract

Knowledge-base canonical pattern:

```text
<year>-<publication number>-<title>-<assignee>.pdf
```

Unknown fields are omitted safely. No placeholder metadata is inserted.

Examples:

```text
2024-US20240003400A1-Pilot-main-failsafe-DRiV.pdf
2025-CN120100850A-一种浮动密封式电磁阀减振器-一汽东机工减振器有限公司.pdf
CN120100850A.pdf
```

Known companies use `archive_name`; unknown companies use a sanitized assignee folder or `待归类`.

Reader single-PDF downloads and Family downloads must call the same filename semantics.

## 7. Company/entity contract

Entity graph relations matter. Default technical search may include safe historical/technology relations but must exclude security-interest-only ownership.

Archive folder naming is independent from UI display.

Examples:

```yaml
tenneco:
  display_name: Tenneco / Monroe
  archive_name: Tenneco
zf:
  display_name: ZF / Sachs
  archive_name: ZF
ftl:
  display_name: 富奥东机工 / 一汽东机工
  archive_name: 富奥东机工
```

Acquired-company portfolios must be technology scoped when the acquirer has unrelated patents.

## 8. Reliability contract

No destructive automatic migration of user files.

No silent data loss on SQLite enrichment; preserve `first_seen_at` and provenance.

Background workers must not call Tk widgets directly.

Network-provider failure must not corrupt local state.

A partial family download must record member-level success/failure and allow retry without re-downloading successful members.

Offline deterministic tests must not require public network services or credentials.

## 9. AI autonomous repair policy

When an AI agent receives "next", "check", "fix", or equivalent:

1. Read this spec and `AGENTS.md`.
2. Inspect git status and protect unrelated changes.
3. Run `python scripts/ai_self_audit.py --full`.
4. Convert failures into a ranked plan:
   - P0: wrong ownership, data corruption, unsafe file operation, broken persistence.
   - P1: core workflow broken or inconsistent.
   - P2: UX, performance, maintainability or documentation drift.
5. Repair P0 first, then P1.
6. Add regression tests that assert the invariant, not a brittle implementation detail.
7. Re-run full audit.
8. Start the desktop app for a real smoke when Windows UI behavior changed.
9. Commit/push only validated scoped changes when repository access is available.

If a test conflicts with an intentional product extension, update the test contract rather than deleting the feature.

## 10. Definition of done

A change is done only when:

- implementation follows this product spec;
- Ruff passes;
- full pytest passes;
- Python compilation passes;
- desktop backend smoke passes;
- offline release acceptance passes;
- `git diff --check` passes;
- relevant regression tests exist;
- no unrelated user work was overwritten.

This specification overrides stale V1 wording when newer implemented product behavior is explicitly described here.
