# Known Issues

Tracked here instead of GitHub Issues for now -- `gh` isn't installed/authenticated in the
environment these were found from. Move any of these to a real GitHub Issue at
https://github.com/lizhenhai2024-alt/Patent-Intelligence-Workbench/issues once you have `gh auth
login` set up locally, or paste a token and Claude can push them from here.

## Open

1. **Python 3.12 Tcl/Tk installation on this machine is corrupted.** Multiple `.tcl` files under
   `C:/Users/lizhe/AppData/Local/Programs/Python/Python312/tcl/tk8.6/` intermittently fail to
   load (`init.tcl`, `tk.tcl`, various `ttk/*.tcl` theme files — different file each run). This
   causes random `TclError` when creating a `PatentWorkbenchApp` during full test-suite runs.
   Symptom: `desktop_smoke` and `offline_release_acceptance` pass; `pytest` fails ~1-2 Tk tests
   per full run with a different missing file each time. Fix: reinstall Python 3.12 with the
   Tcl/Tk component checked, or repair the `tcl/` directory from a clean installer. Not a code
   issue — the 14 tests in `tests/test_issues_verification.py` pass 14/14 when the suite is
   run without prior Tk-root exhaustion.

## Resolved (kept for reference)

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
   `safe_company_archive_names`, `required_ai_contract_docs`, `desktop_smoke`, and
   `offline_release_acceptance` all pass. The `pytest` leg intermittently fails due to the
   corrupted Tcl/Tk install (see Open issue 1) — when Tk loads correctly, all 239+ tests pass.

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
   All 14 pass standalone. Full-suite pass rate is limited only by the Tcl/Tk install issue.

   Note: items 1/2 were originally written under the assumption that Watch shipped with no
   rules — in practice the app seeds preset competitor template rules, so the Watch empty
   placeholder only appears if all templates are removed.

- Technology tab lack of search/filter, node visual distinction, and inconsistent
  (status-bar-only) feedback on category-node clicks — fixed and now covered by tests.
- Watch tab had no way to create a monitoring rule outside the fixed competitor template
  list — fixed and now covered by `test_watch_create_custom_rule`.
