# 智能体 MCP（M1）实施计划

1. 给 `SQLitePatentLibrary` 增加只读模式（`read_only=True` → `file:...?mode=ro`，不执行 `_init_schema`）。
   - 检查点：测试证明可读、写入抛出 `sqlite3.OperationalError`；现有存储测试不变。
2. 实现 `app/agent_tools/tools.py`：状态、公司/主题列表、`search_library`、`get_publication`、`get_family`。
   - 检查点：返回格式、回执、隐私、精确解析测试在测试数据库上通过。
3. 增加 `read_publication_text`（通过现有 `app/services/pdf_reader.py` 读本地 PDF，不联网）和三个 `run_*` 报告工具（序列化 `AnalysisReport`，每行带回执）。
   - 检查点：报告序列化测试保留每行公开号；全部工具运行后数据库哈希不变。
4. 增加 `app/agent_tools/mcp_server.py`、`agent` 可选项和 `patent-workbench-mcp` 启动命令。
   - 检查点：MCP 冒烟测试列出十个工具；未安装 `mcp` 时核心测试照常通过。
5. 编写 `docs/AGENT_MCP.md`（客户端配置 + 数据外发说明），从 README 链接，然后在 Claude Desktop/Cowork 中用规格里的验收问题做人工验收。
   - 检查点：完整自检、`git diff --check`，并逐个核对验收回答中的回执。

## 边界

- 始终：只做新增；现有桌面、检索、下载、监控和本地库行为不变。
- 需要时再问：改变 `SQLitePatentLibrary` 的默认（读写）行为；任何新的必需依赖。
- 绝不：M1 中出现写入工具、联网工具，或暴露私有标注字段。
