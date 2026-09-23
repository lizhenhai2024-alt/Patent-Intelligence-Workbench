# LocalLibrary 智能体工具（MCP，只读）

让 Claude Desktop / Cowork 或其他支持 MCP 的智能体，直接查询你本机的 LocalLibrary。设计依据：`tasks/SPEC-agent-mcp.md`。

## 安装

```powershell
cd D:\MCP\Patent-Intelligence-Workbench
.venv\Scripts\python -m pip install -e ".[agent]"
```

不装 `agent` 这个可选依赖时，桌面程序和核心功能完全不受影响。

## 在 Claude Desktop 中配置

编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "patent-workbench": {
      "command": "D:\\MCP\\Patent-Intelligence-Workbench\\.venv\\Scripts\\patent-workbench-mcp.exe",
      "args": []
    }
  }
}
```

默认读取桌面程序的数据库（`%LOCALAPPDATA%\PatentIntelligenceWorkbench\workbench.db`）。要指定别的数据库，就在 `args` 里写 `["--db", "D:\\路径\\workbench.db"]`。保存后重启 Claude Desktop。

## 提供的 10 个工具

`library_status`、`list_companies`、`list_technology_topics`、`search_library`、`get_publication`、`read_publication_text`、`get_family`、`run_landscape`、`run_company_profile`、`run_comparison`。

每个结果都带 `receipts`（公开号回执）、`as_of`、`truncated` 和 `notes`。

## 哪些数据会离开本机

MCP 服务本身只在本机运行，但**工具返回的内容会被客户端发送到它所用的云端模型**。因此：

- **会发送：** 专利著录信息（公开号、标题、申请人、日期、分类号、专利族），以及本地 PDF 中的权利要求/说明书文本。这些都是已公开的专利资料。
- **不会发送：** 你的笔记、项目、标签、监控规则，来源记录里的 `source_ref`（可能含监控规则或本地路径），以及 PDF 文件路径。

## 边界

- 数据库以只读方式打开（SQLite `mode=ro`），测试会验证工具运行前后数据库文件逐字节不变。
- 不联网、不下载、不写文件。
- 公司名按精确匹配解析，不做模糊猜测。
- 结果只覆盖本地库。工具不输出新颖性、FTO、侵权结论或概率评分。
