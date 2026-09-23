# 智能体 MCP（M1）任务清单

- [x] `SQLitePatentLibrary` 只读模式。
  - 验收：`read_only=True` 正常读取、拒绝写入、跳过建表。
  - 验证：存储相关测试。
- [x] 核心工具：`library_status`、`list_companies`、`list_technology_topics`、`search_library`、`get_publication`、`get_family`。
  - 验收：统一返回格式，非空结果都带回执，公司精确解析，不含私有字段。
  - 验证：`tests/test_agent_tools.py`。
- [x] 文本与报告工具：`read_publication_text`、`run_landscape`、`run_company_profile`、`run_comparison`。
  - 验收：只读本地 PDF；报告每行保留回执；全部工具运行后数据库哈希不变。
  - 验证：`tests/test_agent_tools.py`。
- [x] MCP 适配层、`agent` 可选项和 `patent-workbench-mcp` 启动命令。
  - 验收：通过 stdio 列出十个工具；核心安装仍不依赖 `mcp`。
  - 验证：MCP 冒烟测试（未装可选项时跳过）和完整离线测试。
- [x] `docs/AGENT_MCP.md` 和人工验收问题。
  - 验收：智能体引用的每个公开号都存在于本地库。
  - 验证：2026-09-23 在真实 Windows 本地库上验收（`.tmp-acceptance/mcp_acceptance_report.json`）：引用 15 个公开号，全部存在，数据库哈希不变。
  - 验收发现的问题：真实库中这 15 件 KYB 命中全部缺少申请日和公开日，`from_date` 过滤会把它们全部排除，"近 5 年"这类问题目前按日期过滤不可用。已记入 `tasks/ISSUES.md`。
