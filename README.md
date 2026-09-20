# Patent Intelligence Workbench

面向工程师的全球专利搜索、专利族分析、批量下载与竞争对手新专利监控工具。

## V1.0 scope

- Patent Search: 文字、专利号、公司 + 技术
- Patent Family: priority、Simple/INPADOC family、CN/JP/EP/US/WO/KR family members
- Download Center: 单件、整族、批量 PDF 下载与失败重试
- Patent Watch: 公司、公司 + 技术、新公开、新增 family member
- Local Library: 收藏、标签、公司/技术分类、Excel/CSV 导出
- Company Entity Graph: 历史申请人、IP holding entity、并购/技术前身、专利权属关系

正式 Prior Art / 查新、X/Y/A、Claim Chart 和 FTO 不进入 V1.0。

## Core jurisdictions

CN / JP / EP / US / WO / KR

JP is a first-class jurisdiction. The data model reserves IPC, CPC, FI, F-term and Theme Code from the beginning.

## Default monitored damper / suspension companies

- Hitachi Astemo
- KYB
- Tenneco / Monroe
- ZF / Sachs
- BWI
- HL Mando
- thyssenkrupp BILSTEIN
- Multimatic
- Öhlins
- ClearMotion

JTEKT is not part of the default core damper watch list.

## Architecture principles

1. Normalize before search.
2. Treat a patent family as the primary analysis unit.
3. Separate original assignee, current assignee and non-technical security interests.
4. Model company history as an entity graph, not as a flat alias list.
5. Keep provider adapters replaceable; downloading must support source fallback.
6. All release builds must pass automated tests.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

## Current status

Core V1 implementation is now end-to-end:

- P1 Foundation: patent-number normalization, entity graph, CI
- P2 Family Providers: DOCDB simple / INPADOC extended family, EPO OPS, JPO validation client
- P3 Search: patent number, text, company, company + technology, multilingual terminology
- P4 Download Center: family PDF batch download, fallback policy, retry/cache/manifest
- P5 Patent Watch: baseline, new-family/new-member detection, SQLite state, scheduler
- P6 Local Library: family/publication persistence, favorites, tags, projects, PDFs, provenance, CSV/XLSX
- P7 Desktop: lightweight Windows UI, secure EPO credentials, editable library details, automatic EXE build

Fresh desktop installations use one local `workbench.db` for Patent Library and Patent Watch tables. Existing legacy database paths are preserved to avoid silent data loss.

Current phase: **P8 V1 Release Candidate hardening** — end-to-end acceptance, release documentation, packaging verification and optional credentialed provider smoke tests.

See `docs/ARCHITECTURE.md` and `docs/DOWNLOAD_SOURCES.md` for the frozen V1 architecture and source policy.

Release-candidate documentation:

- `docs/QUICKSTART.md`
- `docs/RELEASE_CHECKLIST.md`
- `CHANGELOG.md`


## License

MIT
