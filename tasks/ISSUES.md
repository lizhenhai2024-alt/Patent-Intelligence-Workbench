# Known Issues

Tracked here instead of GitHub Issues for now -- `gh` isn't installed/authenticated in the
environment these were found from. Move any of these to a real GitHub Issue at
https://github.com/lizhenhai2024-alt/Patent-Intelligence-Workbench/issues once you have `gh auth
login` set up locally, or paste a token and Claude can push them from here.

## Open

1. **真实本地库中大量公开件缺少申请日/公开日，按日期过滤会漏掉它们。** 2026-09-23 做 M1 人工验收（"KYB 近 5 年 CDC 阀的技术路线"）时发现：智能体引用的 15 件 KYB 公开件全部没有 `filing_date` 和 `publication_date`，`search_library` 的 `from_date` 过滤会把它们全部排除，`run_*` 报告的日期范围和申请趋势也受影响（这些记录落入"日期缺失"）。验收脚本改用公开号中的年份判断，但那只是估计，不能当作日期。处理方向：在本地库同步/补全时从 EPO OPS 等数据源补齐著录日期；不从公开号推断日期写入数据库。证据：`.tmp-acceptance/mcp_acceptance_report.json`。

## Resolved (kept for reference)

0. ~~**Python 3.12 Tcl/Tk installation intermittently failed to load `.tcl` files**~~ — Fixed.
   Symptom: full-suite `pytest` randomly failed 1-2 Tk tests with `couldn't read file …` for a
   *different* file each run (`init.tcl`, `tk.tcl`, `ttk/sizegrip.tcl`, …), even though the
   files existed on disk and isolated runs passed. Diagnosis ruled out antivirus (Defender
   real-time protection off), file corruption (inventory matched a healthy install), and
   environment variables (setting `TCL_LIBRARY`/`TK_LIBRARY` made things worse and was
   reverted). Root cause was a damaged Tcl/Tk Support MSI component registration.
   Fix: `msiexec /fa {75485683-EF03-41E6-BF21-D1491694548C} /qn` (repair of the
   "Python 3.12.10 Tcl/Tk Support" product). Verified: full suite **6/6 green** and
   `python scripts/ai_self_audit.py --full` returns `ok: true` (all 9 checks pass).

1. ~~**Reader has no "open by patent number" entry point.**~~ — Fixed. Reader tab now has a
   "按公开号打开" input + button (`open_reader_by_number` in `app/desktop/app.py`); Enter key
   works too. Priority: search cache → LocalLibrary → minimal `SearchHit` fallback.
   Verified by `test_reader_open_by_patent_number` in `tests/test_issues_verification.py`.

2. ~~**No first-run onboarding or empty-state guidance on core pages**~~ — Fixed. Search,
   Family, Watch, and Local Library now show a non-selectable guidance row when the result
   tree is empty (`_insert_empty_placeholder`, iid `__empty__`). All selection/double-click
   handlers guard against the placeholder. Placeholders reappear when a refresh yields zero
   rows. Verified by `test_empty_placeholders_on_core_pages` and
   `test_placeholder_selection_is_ignored`.

3. ~~**`tasks/todo-product-readiness.md` item 4 status unconfirmed**~~ — Confirmed. Full
   `python scripts/ai_self_audit.py --full` was run on this Windows / Python 3.12 machine.
   Result: `compileall`, `ruff`, `git_diff_check`, `unique_company_group_ids`,
   `safe_company_archive_names`, `required_ai_contract_docs`, `pytest`, `desktop_smoke`, and
   `offline_release_acceptance` all pass (`ok: true`). Earlier intermittent `pytest` failures
   were caused by the Tcl/Tk install issue (see Resolved item 0), since repaired.

4. ~~**Recent fixes need manual verification on Windows / Python 3.12**~~ — Verified. Added
   `tests/test_issues_verification.py` (14 tests) covering:
   - Watch: `create_watch_rule` creates a rule with correct cadence/terms; validation on
     empty input.
   - Technology: filter box narrows the tree; leaf/category tags; category-click messagebox.
   - Async re-entrancy: Reader translation double-trigger is a no-op while in-flight;
     Intelligence `run_task` short-circuits when the button is disabled.
   - Translation dropdown: switching between auto-filled providers updates the endpoint;
     a user-typed custom endpoint is never overwritten.
   - Reader open-by-number (Issue 1) and empty placeholders (Issue 2).
   All 14 pass standalone, and the full suite is now stable after the Tcl/Tk repair
   (see Resolved item 0).

   Note: items 1/2 were originally written under the assumption that Watch shipped with no
   rules — in practice the app seeds preset competitor template rules, so the Watch empty
   placeholder only appears if all templates are removed.

- Technology tab lack of search/filter, node visual distinction, and inconsistent
  (status-bar-only) feedback on category-node clicks — fixed and now covered by tests.
- Watch tab had no way to create a monitoring rule outside the fixed competitor template
  list — fixed and now covered by `test_watch_create_custom_rule`.
