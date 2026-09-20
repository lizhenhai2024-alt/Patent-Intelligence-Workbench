# V1 Quick Start

Patent Intelligence Workbench V1 is a lightweight Windows-first desktop tool for patent search, family analysis, PDF collection, competitor monitoring and local engineering organization.

## 1. Get the Windows build

Open the repository's **Actions** page and select the latest successful **Windows Desktop Build** run.

The artifact contains:

- `PatentIntelligenceWorkbench.exe`
- `BUILD_INFO.txt`
- `SHA256SUMS.txt`

Before first use, compare the executable SHA-256 hash with `SHA256SUMS.txt`.

## 2. First launch

The application keeps user data outside the executable.

Fresh installations use:

```text
%LOCALAPPDATA%\PatentIntelligenceWorkbench\
├─ workbench.db
├─ downloads\
└─ exports\
```

If an earlier build already contains `patent_library.db` or `patent_watch.db`, those legacy paths are kept rather than silently migrated.

## 3. Optional EPO OPS enhancement

Search does **not** require EPO OPS credentials. The default chain is:

1. Local Library;
2. zero-credential public search;
3. EPO OPS, only when credentials are configured.

DOCDB simple-family analysis also has a zero-credential public fallback. EPO OPS remains useful for richer EPO data and INPADOC extended-family analysis.

To enable the optional EPO provider:

1. Open **Settings**.
2. Enter your EPO OPS Consumer Key and Consumer Secret.
3. Choose **安全保存**.

On Windows, credentials are stored in Windows Credential Manager. They are not written to SQLite, JSON or the Git repository.

Environment variables remain available for development/CI:

```text
EPO_OPS_KEY
EPO_OPS_SECRET
```

## 4. Search

The Search tab accepts:

- patent/publication number;
- text/technology description;
- company;
- company + technology;
- jurisdiction filters.

The engineering dictionary expands common Chinese/Japanese suspension terms to provider-compatible concepts.

Company searches use the Entity Graph, so historical/IP entities can be included without treating financing/security-interest entities as technical owners.

## 5. Patent Family

Double-click a Search result or enter a publication number in **Family**.

V1 distinguishes:

- **DOCDB simple family** — default invention/family unit for monitoring;
- **INPADOC extended family** — broader priority-related analysis.

Use:

- **加入本地库** to archive the family;
- **下载全部专利 PDF** to download available family documents.

The Family tab shows per-member download progress, the current publication number and a final success/failure summary. Downloaded members are stored by jurisdiction and accompanied by a `family.json` manifest.

## 6. Patent Watch

Default competitor templates are created but disabled on first launch.

Recommended first use:

1. Open **Patent Watch**.
2. Enable only the companies/topics you want.
3. Select a rule, adjust **监控间隔(h)** as needed, then choose **应用到选中规则**.
4. Run due rules once to establish the baseline.
5. Subsequent runs distinguish:
   - new patent family;
   - new member of an existing family;
   - temporarily unresolved family.

New Watch events are automatically archived into Local Library.

## 7. Local Library

Local Library supports:

- family/publication metadata;
- favorites;
- notes;
- tags;
- projects;
- company groups;
- technology topics;
- local PDFs;
- Watch source;
- Search/Family/Download/Watch provenance;
- IPC/CPC/FI/F-term and other stored classification systems;
- CSV and native XLSX export.

## 8. Download-source policy

V1 deliberately avoids brittle robot scraping of official patent websites.

Current automated path:

1. EPO Publication Server for supported EP publication PDFs;
2. Google Patents as a general fallback where available.

When automation fails, the manifest/library can expose authoritative alternatives such as J-PlatPat, CNIPA or PATENTSCOPE according to their access mode.

See `docs/DOWNLOAD_SOURCES.md`.

## 9. Backup

Close the application before making a cold backup, then copy:

```text
workbench.db
downloads\
exports\   (optional)
```

For legacy installations, also back up `patent_library.db` and `patent_watch.db`.
