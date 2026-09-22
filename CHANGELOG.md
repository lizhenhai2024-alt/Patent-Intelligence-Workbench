# Changelog

## 1.0.0rc6 — Chinese engineering evidence workspace

### Desktop experience

- Localize user-facing desktop navigation, page titles, status messages, controls and configuration labels into Chinese while preserving standard patent and provider identifiers.
- Refine the layout around a stable engineering-evidence workflow: one primary action per page and grouped secondary actions.
- Split Local Library controls into directory sync and search/export rows, make Evidence filters self-describing, and correct the Local Library note/PDF detail layout.

### Documentation and validation

- Rewrite README in Chinese with the RC.6 installation path, evidence boundaries and optional-AI data policy.
- Add a page-layout audit and Chinese UI regression coverage.
- Full deterministic audit, real Tk UI regression, GitHub CI and Windows build passed.

## 1.0.0rc5 — Guided engineering intelligence workspace

### Product readiness

- Add guided task cards that state each workflow's purpose, required inputs, evidence-backed outputs and explicit boundaries.
- Evaluate Local Library readiness before analysis; an empty or weak library now directs the user to Search/Library instead of presenting a misleading empty analysis.
- Make workflow inputs task-specific and validate company, topic and route-comparison requests before running.

### Optional AI interpretation

- Add an explicit, opt-in OpenAI-compatible interpretation request for completed local evidence reports.
- Endpoint, model, API key and consent are required for each session; credentials are not persisted and raw evidence output remains visible.

### Validation

- Full deterministic audit, real Tk desktop smoke and GitHub Windows build passed for the guided intelligence workflow.

## 1.0.0rc4 — Reader/Watch restoration, LocalLibrary workbench and engineering intelligence

### Search and portfolio quality

- Prefer Chinese title/applicant metadata for CN patents where available.
- Allow free-form company/applicant searches instead of limiting input to preset companies.
- Tighten suspension-domain filtering to reduce unrelated company-portfolio contamination.

### Patent Reader and Patent Watch

- Restore Reader claims, description and figures through layered public/PDF/EPO fallbacks.
- Add explicit source visibility and family full-text fallback.
- Restore automatic Patent Watch execution with failure backoff and run-selected-now control.

### Local Library

- Turn LocalLibrary into an interactive patent workbench with direct Reader, Family, PDF, folder and source actions.
- Add right-click/keyboard navigation, quick filters, richer metadata and local-family reconstruction.

### Engineering intelligence

- Add evidence-backed engineering-intelligence workflows for patent analysis and technical research.

### Validation

- Windows one-file packaged executable smoke test is required before release.
- Release artifact includes BUILD_INFO.txt and SHA256SUMS.txt and is published only after a successful main-branch Windows build.

## 1.0.0rc3 — Desktop thread safety, download feedback and Watch cadence

### Desktop thread safety

- SQLite-backed Local Library and Patent Watch now use one connection per thread.
- Background Search and Watch workers no longer reuse the Tk/main-thread SQLite connection.
- Worker completion and progress callbacks are marshalled through a thread-safe callback queue; worker threads no longer call Tk directly.

### Patent Family download

- “下载全部专利 PDF” now disables immediately while a download is active.
- Added determinate family-download progress with current publication number and completed/total count.
- Completion always shows an explicit success/partial-failure summary and output folder.
- Added per-member progress callbacks in FamilyDownloader.

### Patent Watch

- The desktop Watch tab now exposes editable monitoring cadence in hours for the selected rule.
- Cadence changes persist to SQLite and are respected by the due-rule scheduler.

### Validation

- Added cross-thread SQLite regression tests for Local Library and Patent Watch.
- Added Tk callback-queue regression coverage.
- Added family-download progress regression coverage.
- Local GUI end-to-end validation passed with US20240003399A1: patent-number search, 4-member family resolution, and 4/4 PDF download.

## 1.0.0rc2 — Zero-configuration search fallback

### Search

- Search remains enabled when EPO OPS credentials are absent.
- Patent-number detection now has highest routing priority, even when a stale company filter remains selected.
- Added Local Library as the first search layer.
- Added zero-credential Google Patents structured search/publication lookup fallback.
- EPO OPS is now an optional enhancement provider rather than the global search gate.
- Provider fallback distinguishes authentication, rate-limit, unavailable and response failures.
- Google public search automatically retries transient throttling/network failures with bounded backoff.
- A failed provider no longer aborts the whole search when another provider can succeed.
- Company/entity queries stop once enough public results are collected, reducing unnecessary requests.

### Patent Family

- DOCDB simple-family analysis can fall back to structured Google Patents family metadata without EPO credentials.
- INPADOC extended family remains an EPO-enhanced capability.

### Desktop

- Search button is always available.
- Network status now reports public search separately from optional EPO OPS configuration.
- Search completion shows the source that supplied the result.

### Validation

- Added regression coverage for zero-EPO runtime, patent-number routing, provider fallback, rate limiting and Google structured metadata parsing.
- Added `scripts/rc2_zero_config_smoke.py` for live zero-credential validation.

## 1.0.0rc1 — V1 Release Candidate

### Search and company intelligence

- CN / JP / EP / US / WO / KR publication-number normalization.
- Patent-number, text, company and company + technology search flows.
- Multilingual suspension terminology expansion.
- Company Entity Graph with historical/IP relationships and security-interest exclusion.

### Patent Family

- DOCDB simple-family and INPADOC extended-family domain models.
- EPO OPS family integration.
- JPO domestic patent-information client for JP validation workflows.
- Priority/member normalization and family de-duplication.

### Download Center

- Complete-family PDF batch download.
- Official EPO Publication Server support for EP documents.
- General fallback provider architecture.
- atomic writes, PDF validation, cache reuse and failed-member retry.
- `family.json` manifest and structured official fallback hints.

### Patent Watch

- first-run baseline behavior;
- new-family and new-family-member detection;
- unresolved-family retry;
- persistent SQLite state;
- cadence scheduler and run history;
- core competitor templates;
- automatic archival of new Watch events into Local Library.

### Local Library

- unified fresh-install `workbench.db` for Library + Watch tables;
- patent family and national-publication records remain separate;
- priority and classification storage;
- company/topic/project/tag organization;
- favorites and notes;
- local PDF metadata;
- Search/Family/Download/Watch provenance;
- CSV and native XLSX export;
- legacy database paths preserved for existing installations.

### Windows desktop

- lightweight Tkinter/ttk desktop shell;
- Search, Family, Patent Watch, Local Library and Settings tabs;
- Windows Credential Manager storage for EPO OPS credentials;
- editable favorites/notes/tags/projects;
- automatic one-file Windows build;
- packaged EXE smoke test;
- SHA-256 checksum and build information.

### Release validation

- Windows + Linux offline CI.
- Full unit/regression suite.
- Desktop backend smoke.
- Offline end-to-end V1 release acceptance.
- Manual credentialed EPO provider smoke workflow.

### Known V1 boundaries

- Formal novelty/prior-art opinion, X/Y/A assessment, Claim Chart and FTO are deferred.
- True patent-drawing visual-similarity search is deferred.
- J-PlatPat/CNIPA/PATENTSCOPE web pages are not robot-scraped when no stable public automation API is documented.
- Live EPO verification requires user/repository credentials and is intentionally separate from deterministic CI.
