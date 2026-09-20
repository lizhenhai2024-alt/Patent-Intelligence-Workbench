# V1 Release Checklist

This checklist defines the release gates for V1.

## Gate A — deterministic offline CI

Required on both Ubuntu and Windows:

- [ ] package installation succeeds;
- [ ] Ruff passes;
- [ ] full pytest suite passes;
- [ ] desktop backend smoke passes;
- [ ] offline V1 end-to-end acceptance passes.

The offline acceptance must exercise:

```text
Search
  -> Family
  -> PDF Download
  -> Patent Watch
  -> Local Library
  -> CSV/XLSX export
```

No public network service is allowed to be required for this gate.

## Gate B — packaged Windows executable

Required:

- [ ] PyInstaller one-file/windowed build succeeds;
- [ ] packaged EXE passes `--smoke`;
- [ ] `BUILD_INFO.txt` contains version + commit + UTC build time;
- [ ] `SHA256SUMS.txt` is produced;
- [ ] EXE + build info + checksum are uploaded as one Actions artifact.

## Gate C — live provider verification

Before a stable `v1.0.0` tag:

- [ ] repository secrets `EPO_OPS_KEY` and `EPO_OPS_SECRET` are configured in a trusted environment;
- [ ] **EPO Provider Smoke** workflow completes successfully;
- [ ] direct publication lookup succeeds;
- [ ] DOCDB simple-family lookup succeeds.

This gate is intentionally manual. External availability, credentials and quota must not make normal CI flaky.

An RC may be produced without Gate C only when it is clearly treated as **not live-provider-verified**.

## Gate D — data compatibility

- [ ] fresh installation creates one `workbench.db`;
- [ ] Library and Patent Watch tables coexist;
- [ ] existing legacy database paths remain usable;
- [ ] no automatic destructive migration is performed;
- [ ] `first_seen_at` is preserved during enrichment;
- [ ] Search/Family/Download/Watch provenance is retained.

## Gate E — manual desktop acceptance

On a Windows desktop:

- [ ] Settings opens and EPO credentials can be saved/deleted;
- [ ] Search results render;
- [ ] selected result opens Family analysis;
- [ ] family can be added to Local Library;
- [ ] complete-family download starts and reports partial failures;
- [ ] Watch rules can be enabled/disabled;
- [ ] Watch events appear in Local Library;
- [ ] favorite/note/tag/project editing persists;
- [ ] local PDF can be opened;
- [ ] CSV export opens correctly;
- [ ] XLSX export opens correctly.

## Gate F — release

RC:

- [ ] version is `1.0.0rc2`;
- [ ] changelog is current;
- [ ] Quick Start is current;
- [ ] zero-credential patent-number and keyword search are validated;
- [ ] CI and Windows Build are green;
- [ ] artifact checksum is available;
- [ ] tag convention: `v1.0.0-rc.2`;
- [ ] successful main-branch Windows build triggers the idempotent RC publisher;
- [ ] prerelease contains EXE, `BUILD_INFO.txt` and `SHA256SUMS.txt`.

Stable:

- [ ] all RC gates are green;
- [ ] Gate C live-provider verification is green;
- [ ] blocking RC defects are closed;
- [ ] version is changed to `1.0.0`;
- [ ] tag `v1.0.0` is created from the verified commit.
