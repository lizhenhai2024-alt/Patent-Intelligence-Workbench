# Known Issues

Tracked here instead of GitHub Issues for now -- `gh` isn't installed/authenticated in the
environment these were found from. Move any of these to a real GitHub Issue at
https://github.com/lizhenhai2024-alt/Patent-Intelligence-Workbench/issues once you have `gh auth
login` set up locally, or paste a token and Claude can push them from here.

## Open

1. **真实本地库中大量公开件缺少申请日/公开日，按日期过滤会漏掉它们。** 2026-09-23 做 M1 人工验收（"KYB 近 5 年 CDC 阀的技术路线"）时发现：智能体引用的 15 件 KYB 公开件全部没有 `filing_date` 和 `publication_date`，`search_library` 的 `from_date` 过滤会把它们全部排除，`run_*` 报告的日期范围和申请趋势也受影响（这些记录落入"日期缺失"）。验收脚本改用公开号中的年份判断，但那只是估计，不能当作日期。处理方向：在本地库同步/补全时从 EPO OPS 等数据源补齐著录日期；不从公开号推断日期写入数据库。证据：`.tmp-acceptance/mcp_acceptance_report.json`。

## 2026-09-23 逐页 UI 逻辑审查

**2026-09-23 修复状态**：UI-01 至 UI-12、UI-14、UI-15 已修复并加回归测试（17bcc4）。UI-13（布局滚动）待单独处理。ENV-01 仍为已知环境问题。

本轮仅检查和记录，不修改应用行为；保留上方原有日期缺失问题及下方历史记录。新增 **15 项 UI 问题（1 项 P0、12 项 P1、2 项 P2）**，另有 **1 项 P1 环境问题重新打开**。P0 表示错误归属风险，P1 表示核心流程错误或不可操作，P2 表示展示/引导问题。

### 覆盖与证据

检查了当前 10 个主页面及相关子界面。使用临时 SQLite/数据目录、假响应和受控异步回调；未联网、未使用真实模型、未修改用户专利库或凭据。布局通过实际 Tk 窗口的控件映射状态检查，不以截图推测。外部服务可用性与真实下载吞吐不在本轮验证范围。

| 页面 | 检查范围 | 结果 |
| --- | --- | --- |
| 专利检索 | 条件路由、回车重入、结果入口、采集、批量补库确认 | UI-02、03、05、12、13、15 |
| 专利阅读 | 连续打开、正文回调、翻译、章节切换、附图工具栏 | UI-01、13；新阅读设置已有独立回归测试，未据此推定整页布局正常 |
| 专利族 | 解析期间状态、加入库、下载入口 | UI-04、05 |
| 专利监控 | 新建、周期输入、启停、运行互斥、跨页错误恢复 | UI-05；检查了其余输入校验和运行状态分支，未新增独立问题 |
| 本地专利库 | 根目录、筛选导出、全文补全、详情与操作区 | UI-06、07、11、12、13 |
| 技术分类 | 分类过滤、叶节点/分类节点、带入检索条件 | 已检查；本轮未确认新的独立问题。保留已有分类节点提示，不把它误记为缺陷 |
| 证据 | 查询、筛选、选择、长文预览 | UI-14 |
| 情报分析 | 工作流切换、检索计划、报告导出/AI 解读入口、事件复核可达性 | UI-08、13 |
| 智能体 | 新运行、失败结果、HTML/日志入口 | UI-09 |
| 设置 | 模型列表异步加载、预设切换、翻译配置、窗口布局 | UI-10、13 |

本地复现产物（`.tmp-acceptance/` 被 Git 忽略，便于本机复查，不作为唯一复现说明）：

- `ui_review_probes.py`：受控回调与布局探针。
- `ui-review-probes.json`：上述探针的实际输出。
- `ui-review-baseline.json`、`ui-review-final.json`：修改文档前后的完整离线自检；两次均为 pytest 因 Tcl/Tk 初始化失败，其余 8 项通过，见 ENV-01。

### UI-01 · P0 · Reader 迟到的正文/译文会显示在另一篇专利名下

- **复现**：先打开 A，未加载完即打开 B；让 B 正文先返回、A 后返回。翻译同样可在 A 请求期间切到 B 后返回。
- **实际**：页头为 `US20240003400A1`，`_reader_document.publication_number` 和正文却来自 `US20240003399A1`；翻译探针在 B 页头下显示 `A old translation`。即使不切专利，只换章节也未绑定译文所属章节。
- **期望/影响**：当前公开号、章节和内容必须一致；错误配对会误导工程判断与证据引用。
- **根因位置**：`app/desktop/app.py::_load_reader_document`、`_on_reader_document_loaded`（约 1013 行）、`_translate_reader_text`（约 1326 行）均未校验请求所属公开号/章节/代次。
- **修复验收**：为请求绑定身份，切换时失效旧回调；反序返回、同号重新加载、翻译期间换章节均不能覆盖新上下文。
- **2026-09-24 修复**：`_on_reader_document_loaded` 增加 `_gen` 参数校验；`_translate_reader_text` 回调增加 `publication_number` 校验；`_render_reader_section` 增加 `_expected_gen` 参数。回归测试：`test_reader_stale_document_load_does_not_replace_current`、`test_reader_stale_translation_does_not_replace_current`。

### UI-02 · P1 · 公司筛选残留时，精确公开号被检索界面丢弃

- **复现**：公司选 KYB，范围保留默认“悬架与减振器”，输入 `US20240003400A1` 并搜索。
- **实际**：传入搜索服务的 query 是空字符串、company 是 KYB，公开号没有传入。选择“公司全量”也有相同分支。
- **期望/影响**：产品契约规定精确公开号优先；不能执行完全不同的公司组合检索。
- **根因位置**：`app/desktop/app.py::run_search`（约 2726 行），有公司且不是“具体技术主题”时直接将 query 改为空。
- **修复验收**：公开号优先识别；覆盖三个范围和残留公司条件组合，界面明确展示实际生效范围。
- **2026-09-23 修复**：`b17bcc4` 中添加 `is_patent_number` 检测，专利号绕过公司筛选清空逻辑。回归测试：`test_search_patent_number_not_discarded_by_company_filter`、`test_search_patent_number_with_company_all_scope`。

### UI-03 · P1 · 搜索按钮禁用不能阻止回车重入，旧结果可覆盖新查询

- **复现**：搜索未完成时在检索输入框再次按 Enter（可先修改条件）。
- **实际**：连续调用入口派发了两个任务；输入框 Return 仍调用 `run_search`，该方法没有运行中检查。结果回调也没有请求身份校验。
- **期望/影响**：应阻止重复运行或只接受最后一次请求；否则结果与当前输入不一致，较早任务还可能提前解除按钮禁用。
- **根因位置**：`app/desktop/app.py::_build_search_tab` 的 Return 绑定、`run_search`、`_render_search_response`。
- **修复验收**：鼠标/回车统一执行运行策略；A/B 反序返回不得将 A 结果显示成 B 查询结果。
- **2026-09-23 修复**：`b17bcc4` 中 `run_search` 增加 `_search_running` 互斥锁。

### UI-04 · P1 · 解析新专利族期间，加入库/下载仍操作旧专利族

- **复现**：已加载 A 族，输入 B 并开始解析；B 返回前点击“加入本地库”或下载整族。
- **实际**：输入为 B，加入库传入的仍是 A；开始解析只禁用分析按钮，保留 `_current_family` 和相关操作入口。失败后也保留旧族。
- **期望/影响**：旧族若保留展示，须明确标注并阻止被误当成 B 进行入库/下载。
- **根因位置**：`app/desktop/app.py::run_family_analysis`、`add_current_family_to_library`、`download_current_family`。
- **修复验收**：新解析期间操作与显示结果身份一致；成功/失败/输入变化均有明确状态。
- **2026-09-23 修复**：`b17bcc4` 中 `run_family_analysis` 开始前清空 `_current_family`。

### UI-05 · P1 · 任一网络错误会解除其他页面的运行锁

- **复现**：监控或整族下载正在运行时，让检索/采集/元数据补全中的另一项报错。
- **实际**：通用错误函数将 `_watch_run_active` 设为 False，并启用监控、族解析、下载和搜索按钮，即使对应任务仍在运行。探针确认监控锁被清除、下载按钮被启用。
- **期望/影响**：错误只恢复所属任务状态；否则可重复启动监控/下载，混淆进度并并发写入本地库。
- **根因位置**：`app/desktop/app.py::_network_error`（约 3563 行）。
- **修复验收**：并行运行两个不同任务，单方失败不改变另一方按钮、锁或进度。
- **2026-09-23 修复**：`b17bcc4` 中拆分 `_network_error` 为 `_on_search_error` 和 `_on_family_error`，各自只恢复自己的按钮状态。

### UI-06 · P1 · 本地库导出忽略“仅收藏”和“仅有 PDF”筛选

- **复现**：勾选这两个条件后导出 CSV 或 Excel。
- **实际**：表格刷新使用两个条件，导出却构造 `favorite_only=False, has_pdf=None` 的查询；输出包含界面已排除的记录。
- **期望/影响**：默认导出与当前筛选一致；如支持导出全库须明确另设选项。
- **根因位置**：`app/desktop/app.py::refresh_library` 与 `export_library`（约 3542 行）。
- **修复验收**：文本、收藏、PDF 条件的组合在列表与两类导出中一致；超过显示上限时说明导出范围。
- **2026-09-23 修复**：`b17bcc4` 中 `export_library` 构造查询时读取 `library_favorite_only_var` 和 `library_has_pdf_var`。

### UI-07 · P1 · 可编辑的专利库目录与实际生效目录不同步

- **复现**：直接在“专利库目录”框输入另一个目录，点“扫描预览”，随后下载或打开库目录。
- **实际**：显示/扫描使用 `library_root_var`，有效下载根目录仍来自 `runtime.library_root`。探针确认输入变更后 effective root 未改变；没有明确的“应用路径”操作或未保存提示。
- **期望/影响**：避免用户以为下载进入新目录，实际写入旧位置。
- **根因位置**：`app/desktop/app.py::_build_library_tab`（约 1658 行）、`preview_library_root`、`choose_library_root`、`_download_family_to_library_root`。
- **修复验收**：目录改为只读并通过选择操作更新，或提供校验后的明确应用入口；展示、预览、打开、下载保持一致。
- **2026-09-23 修复**：`b17bcc4` 中 `library_root_var` Entry 设为 `state="readonly"`。

### UI-08 · P1 · 情报工作流切换后，旧报告仍可导出或发给 AI

- **复现**：先生成一份全景报告，再切到“工程问题检索”并生成新检索计划，然后保存 HTML、复制 AI 提示词或请求 AI 解读。
- **实际**：预览已是新检索计划，`_intelligence_report` 仍指向旧报告。探针确认 `old_report_retained=True`。输入校验失败/数据不就绪也在清理报告之前返回。
- **期望/影响**：结果操作只作用于当前明确展示的产物，不把旧范围报告冒充当前任务。
- **根因位置**：`app/desktop/intelligence_tab.py::refresh_task_workspace`、`run_task`（约 354 行）、`save_report`、`run_ai_interpretation`。
- **修复验收**：切任务/条件失效/规划任务成功时清理或明确锁定旧报告；导出和 AI 操作绑定当前产物。
- **2026-09-23 修复**：`b17bcc4` 中 `refresh_task_workspace` 切换时清空 `_intelligence_report`。

### UI-09 · P1 · 智能体本次失败后，“查看结果”仍打开上次 HTML

- **复现**：运行一次成功并生成 HTML，然后第二次失败或取消且没有可渲染的回答，再打开结果。
- **实际**：新状态显示失败，`_agent_last_html` 仍是上次路径；探针确认打开了旧文件。`show_result` 仅在有 check 的成功渲染分支更新路径。
- **期望/影响**：本次结果和历史结果须区分，失败时不能无提示打开上一轮产物。
- **根因位置**：`app/desktop/agent_tab.py::run_agent`、`show_result`（约 605 行）、`open_last_html`。
- **修复验收**：新运行开始重置当前结果入口；失败/取消后提示本次无结果，历史记录保留独立入口。
- **2026-09-23 修复**：`b17bcc4` 中 `run_agent` 开始时重置 `_agent_last_html`。

### UI-10 · P1 · 切换模型厂商后，旧请求的模型列表可覆盖新配置

- **复现**：对厂商 A 获取模型列表，返回前切换到厂商 B/另一已保存配置，再让 A 返回。
- **实际**：新接口地址仍为 B，模型选项及默认模型却被设置成 A 的结果；探针得到 `new-provider.example` 配 `old-provider-model`。
- **期望/影响**：避免保存不可用的跨厂商模型组合。
- **根因位置**：`app/desktop/agent_tab.py::fetch_model_list`、`_models_loaded`（约 217 行）；回调没有保存并核对接口/配置身份。
- **修复验收**：更换预设、接口或已保存配置后丢弃旧响应；失败回调也不得覆盖新请求状态。
- **2026-09-23 修复**：`b17bcc4` 中 `_models_loaded` 回调检查 `base_url` 身份。

### UI-11 · P1 · EPO 全文补全可手输绕过 1000 件硬上限

- **复现**：缺全文候选超过 1000 件时，确认框数字输入直接键入 1500 再确认。
- **实际**：Spinbox 的范围只限制箭头选择；确认分支仅做 `max(1, value)`。探针将 1500 个候选传入 `_run`，未限制到 1000。
- **期望/影响**：超过批准的单次联网上限，产生意外请求量。无效数字也应保留对话框并提示，不先关闭再抛 Tcl 错误。
- **根因位置**：`app/desktop/backfill_ui.py::_confirm_dialog`（约 47 行）、`_run`；输入错误处理也适用于搜索补库确认框。
- **修复验收**：程序层校验 1–1000 与候选数；覆盖手输超限、0、负数、空白、非数字，非法输入不启动任务。
- **2026-09-23 修复**：`b17bcc4` 中 `_confirm_dialog` 校验并钳制限制 1..HARD_LIMIT。

### UI-12 · P1 · 补库可打开多个确认框，确认后绕过运行互斥

- **复现**：重复点击批量补库或全文补全，打开两个确认框，再分别确认。
- **实际**：确认期间取消标记仍为空，主入口未锁定；对话框无模态抓取，`_run` 未再次检查已有任务。探针确认两个确认框同时存在、均未 grab。
- **期望/影响**：可能产生两个写库/下载任务，而取消按钮只持有最后一个任务的事件。
- **根因位置**：`app/desktop/search_backfill_ui.py::start_search_backfill/_confirm_dialog/_run` 与 `backfill_ui.py` 对应方法。
- **修复验收**：确认阶段也纳入单任务状态；多次点击只保留一个框，重复确认不启动第二任务，取消覆盖实际活动任务。
- **2026-09-23 修复**：`b17bcc4` 中确认对话框使用 `_confirm_open` 标志防止重复打开。

### UI-13 · P1 · 固定布局裁掉关键按钮，缺少整页滚动或换行

- **复现环境**：本机 Tk scaling 约 1.333；实际窗口分别设为默认 `1460×900` 和允许的最小 `1180×720`，逐页完成布局事件处理后检查控件。
- **实际**：默认窗口下，检索页的证据采集操作、库页“保存详情/补全元数据”等按钮未映射；情报页“运行任务/保存离线 HTML/请求 AI 解读/保存复核”等均不可见。最小窗口下还包括库页筛选/导出、设置页打开数据目录；Reader 的旧附图工具栏尾部也被裁掉。此项不是新字号/行距按钮不可用。
- **期望/影响**：窗口符合应用最小尺寸时仍应能够到达所有核心操作；不能要求用户猜测放大窗口或隐藏的键盘操作。
- **根因位置**：`app/desktop/app.py::_build_shell` 及各 `_build_*_tab`，`intelligence_tab.py::build_intelligence_tab`；单层 pack 固定高度与长横排控件没有页面级滚动/响应换行。
- **修复验收**：两个尺寸及常见缩放下逐页检查操作可见或可滚动到达；隐藏字段与被裁掉控件区分，不能仅检测控件已创建。

### UI-14 · P2 · 长证据正文被静默截断，页面无全文入口

- **复现**：保存超过 12000 字符的证据，在 Evidence Center 选择它；详情证据区阈值更低，为 8000。
- **实际**：12014 字符样例末尾 `IMPORTANT_TAIL` 未出现在预览中，无截断提示、加载更多或打开完整正文按钮。数据库原文仍在，不是存储丢失。
- **期望/影响**：用户应知道看到的只是片段，并有可操作的全文查看路径。
- **根因位置**：`app/desktop/app.py::_load_evidence_center_preview`（约 2248 行）、`_load_selected_evidence`。
- **修复验收**：显示总长度/截断提示并提供全文入口；正文末尾证据能从 UI 到达。
- **2026-09-23 修复**：`b17bcc4` 中证据预览显示截断指示器和总长度。

### UI-15 · P2 · 检索结果“双击”提示与实际跳转不一致

- **复现**：阅读检索结果上方“双击结果可直接进入 Patent Family”，双击结果行。
- **实际**：实际绑定 `_open_selected_in_reader`，进入 Reader；专利族有另一个显式按钮。
- **根因位置**：`app/desktop/app.py::_build_search_tab`（提示约 628 行，与 Double-1 绑定不一致）。
- **修复验收**：按已实现产品流程统一提示和动作，并验证显式 Reader/Family 两个入口。
- **2026-09-23 修复**：`b17bcc4` 中提示改为"双击结果可直接进入 Patent Reader"。

### ENV-01 · P1 · Tcl/Tk 初始化问题本轮再次出现（重新打开历史 Resolved 0）

- **实际证据**：本轮完整自检的 `test_search_results_show_technology_tags_and_evidence` 在创建 Tk 根窗口时失败：`_tkinter.TclError: invalid command name "tcl_findLibrary"`。代码编译、Ruff、桌面后端 smoke、离线验收等其余 8 项通过。
- **复验**：独立界面测试组在 `test_empty_placeholders_on_core_pages` 初始化时报 `init.tcl` 无法读取；最终完整自检又在 `test_agents_page_presets_and_profile_without_key_on_disk` 初始化时报 `tcl_findLibrary`。故障位置变化，不能将单次通过视为恢复。
- **范围**：属于本机 UI 运行/测试环境问题；失败发生在业务断言前，不据此判定技术分类逻辑有错。上轮全套通过和历史 MSI 修复记录保留，但不能继续标为持续稳定。
- **后续验收**：独立排查实际 Tcl/Tk 运行路径与加载失败原因；恢复连续可重复的全套检查。未在本次执行安装修复，也不将历史根因自动视为本轮根因。

### 修复顺序建议

~~先修 UI-01 错误归属~~（已修复 2026-09-24）；~~再处理 UI-02/04/05/06/07/08/09/10 的状态与数据范围~~（UI-02 已修复 2026-09-23）；UI-11/12 的受控任务边界以及 UI-13 的入口可达性；UI-03 和其他 P1 同批验证，最后处理 P2。环境 ENV-01 单独排查。每项修复应增加针对其复现条件的回归测试，不能以本轮已有测试通过代替缺陷验证。


## Resolved (kept for reference)

0. **Python 3.12 Tcl/Tk installation intermittently failed to load `.tcl` files** — 历史修复记录；2026-09-23 再现，当前按 ENV-01 重新打开。
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
