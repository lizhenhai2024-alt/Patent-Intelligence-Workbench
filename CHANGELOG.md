# Changelog

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
