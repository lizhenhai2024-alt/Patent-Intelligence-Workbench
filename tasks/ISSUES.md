# Known Issues

Tracked here instead of GitHub Issues for now -- `gh` isn't installed/authenticated in the
environment these were found from. Move any of these to a real GitHub Issue at
https://github.com/lizhenhai2024-alt/Patent-Intelligence-Workbench/issues once you have `gh auth
login` set up locally, or paste a token and Claude can push them from here.

## Open

1. **Reader has no "open by patent number" entry point.** You can only reach the Reader tab by
   double-clicking a row in Search results or in Local Library. If you already know the
   publication number and just want to read it, you still have to run a search or a library
   filter first. `app/desktop/app.py`, `_build_reader_tab` / `_open_hit_in_reader`.

2. **No first-run onboarding or empty-state guidance on the core pages** (Search, Family, Watch,
   Local Library). A first-time user opening the app sees blank result trees with no hint of what
   to do first. The Intelligence tab's readiness system and the Evidence tab's empty-state message
   ("从 Search 页面使用"采集 URL / 文件"创建第一条 Evidence") are the only two places in the app
   that do this well; the rest of the app doesn't.

3. **`tasks/todo-product-readiness.md` item 4 status is unconfirmed.** Earlier in this project I
   left item 4 (full offline release-gate audit, `scripts/ai_self_audit.py --full`) unchecked with
   a note that it needed to actually be rerun. On a later read the file showed it checked off, but
   I did not make that edit myself, and it was never confirmed whether the full gate was actually
   run or the checkbox was toggled by hand. Needs the user to actually run
   `python scripts/ai_self_audit.py --full` on a Python 3.12 environment and confirm the result
   before trusting that checkbox.

4. **Recent fixes need manual verification on Windows / Python 3.12.** The bridge environment used
   to make these changes is Python 3.10 with no `tkinter`, so none of the following could be
   exercised end-to-end and only got `py_compile` + `ruff check` + code review:
   - Watch tab: new "新建监控规则" form (custom rule creation, `create_watch_rule`).
   - Technology tab: search/filter box, leaf/category node coloring, `messagebox` feedback on
     `_search_selected_technology`.
   - Three async re-entrancy fixes: Intelligence tab "运行任务" / "请求 AI 解读" buttons, Reader
     translation buttons (double-click / rapid re-trigger should now be a no-op while busy).
   - Translation provider dropdown: switching between two auto-filled providers should no longer
     leave a stale endpoint behind.

## Resolved (kept for reference)

- Technology tab lack of search/filter, node visual distinction, and inconsistent
  (status-bar-only) feedback on category-node clicks -- fixed, see item 4 above for the
  verification that's still outstanding.
- Watch tab had no way to create a monitoring rule outside the fixed competitor template list --
  fixed, see item 4 above for the verification that's still outstanding.
