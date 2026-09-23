# 规格：本地库只读智能体工具（MCP）— 智能体路线 M1

## 目标

让外部 AI 智能体（Claude Desktop / Cowork，或任何支持 MCP 的客户端）基于用户自己的 LocalLibrary 回答工程专利问题，每个回答都能追溯到本地已存的公开号。这是 `tasks/ROADMAP.md` 中智能体路线的 M1，也是 `tasks/SPEC-agent-task-definitions.md` 里"把本地库开放为智能体可调用工具"设想的落地形式。

M1 只新增一个接入方式，不新增分析能力、不联网、没有任何写入路径。

## 本规格依赖的决定（2026-09-23，产品负责人确认）

1. 允许受控智能体：模型可以在白名单内的只读工具中自行选择下一步，但每条结论都必须带证据回执；判断（X/Y/A、风险、法律）由人做。记录在 `docs/AI_PRODUCT_SPEC.md` 第 11 节。
2. 模型：多个云端模型，由用户选择；不做本地部署。M1 中模型由 MCP 客户端决定；软件内的模型选择属于 M2。
3. 没有智慧芽/incoPat 账号：M1 到 M4 只使用本地库和现有数据源。

## 技术栈与命令

Python 3.12、现有 SQLite 本地库和 `AnalysisService`，以及官方 `mcp` Python SDK（stdio 传输），作为新的可选安装项 `agent`。运行 `python -m pytest tests/test_agent_tools.py -q`、`python scripts/ai_self_audit.py --full` 和 `git diff --check`。

## 项目结构

- `app/agent_tools/__init__.py`
- `app/agent_tools/tools.py`：基于 `SQLitePatentLibrary` + `AnalysisService` 的普通 Python 函数，返回下文统一格式的可 JSON 序列化字典；不引用 MCP，因此不装 SDK 也能测试。工具说明 `TOOL_DESCRIPTIONS` 也放在这里，供 MCP 和 M2 共用。
- `app/agent_tools/mcp_server.py`：薄适配层，把 `tools.py` 中的每个函数注册为 MCP 工具，只负责参数和 JSON 转换。
- `app/library/store.py`：只读打开模式。原构造函数总会执行 `_init_schema()`（写操作），所以 MCP 服务需要 `SQLitePatentLibrary(path, read_only=True)`，以 `file:<path>?mode=ro` 打开并跳过建表。
- `pyproject.toml`：可选安装项 `agent = ["mcp>=1.2,<2"]` 和启动命令 `patent-workbench-mcp = "app.agent_tools.mcp_server:main"`。
- `docs/AGENT_MCP.md`：Claude Desktop / Cowork 配置示例，以及哪些数据会离开本机。
- `tests/test_agent_tools.py`

## 工具清单（全部只读、全部本地）

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `library_status` | — | 数据库路径、公开件/专利族/证据数量、数据库最后修改时间 |
| `list_companies` | — | 已登记公司组：`group_id`、`display_name`、别名 |
| `list_technology_topics` | — | 可检索的本地技术主题，以及可对比的技术路线 |
| `search_library` | `text?`、`company?`、`technology?`、`jurisdictions?`、`from_date?`、`to_date?`、`limit≤100` | 公开件命中：公开号、标题、原始/当前申请人、日期、专利族键、技术主题、`has_pdf` |
| `get_publication` | `publication_number` | 已存著录信息、分类号、优先权、来源类型（不返回 `source_ref`：可能含监控规则或本地路径）、专利族键 |
| `read_publication_text` | `publication_number`、`section`（claims/description；本地库不存摘要）、`max_chars≤20000` | 仅从**本地** PDF 提取的文本；没有 PDF 时 `available=false` |
| `get_family` | `family_key` 或 `publication_number` | 专利族成员，按国家公开件分别列出 |
| `run_landscape` | `topic`、`jurisdictions?`、`from_date?`、`to_date?` | 序列化的 `AnalysisReport` |
| `run_company_profile` | `company` 加相同范围参数 | 序列化的 `AnalysisReport` |
| `run_comparison` | `companies[]` 或 `routes[]`，加相同范围参数 | 序列化的 `AnalysisReport` |

每个工具的统一返回格式：

```json
{
  "data": {},
  "receipts": ["US20240003400A1", "CN120100850A"],
  "source": "LocalLibrary",
  "as_of": "2026-09-23T10:00:00+08:00",
  "truncated": false,
  "notes": ["结果仅覆盖当前 LocalLibrary 已索引记录，不代表全部专利。"]
}
```

序列化后的 `AnalysisReport` 每一行都保留自己的 `publication_numbers`，智能体可以逐条引用。

## 边界

- 始终：每个工具都返回回执；公司通过 `CompanyRegistry` 精确解析（未知公司返回错误并列出 `list_companies` 的候选，绝不模糊匹配）；原始申请人与当前申请人分开；说明结果只覆盖本地库；标明是否截断。
- 始终：数据库只读打开；测试证明每个工具运行后数据库文件逐字节不变。
- M1 绝不向智能体暴露用户私有标注字段：`note`、`projects`、`tags`、`watch_rule_ids`。这些字段可能含内部项目名，而工具输出会发送到客户端的云端模型。文字检索也不能借笔记命中（只按公开号、标题、申请人、分类号过滤）。
- 绝不：联网、调用数据源回退、下载、写文件，或任何改动本地库/监控状态的工具。
- 绝不：输出新颖性/FTO/侵权结论或任何概率式评分的工具。
- 需要时再问：以后是否开放私有标注字段（需要显式开关）；增加 HTTP/SSE 传输（M1 只做 stdio）。

## 代码风格

沿用现有模式：内部用冻结 dataclass、确定性排序，只在工具边界转换为普通字典。日期用 ISO 字符串。错误信息用中文，与桌面程序一致。

## 测试策略

- 在 `tmp_path` 中构造本地库测试数据（SQLite，两家公司、三件公开件、一个 PDF）。
- 每个工具：返回格式正确；`data` 非空时 `receipts` 非空；每个回执都存在于测试数据库。
- 精确解析：`company="KYB"` 能解析；`company="KY"` 返回带候选的错误。
- 隐私：任何序列化输出都不包含测试数据中写入的 `note`、`projects`、`tags`、`watch_rule_ids` 的值。
- 只读：运行全部工具后数据库文件 SHA-256 不变；`SQLitePatentLibrary(read_only=True)` 拒绝写入。
- MCP 适配冒烟测试：服务恰好列出十个工具（未安装 `agent` 可选项时跳过，离线核心测试保持无依赖）。

## 验收标准

1. 安装 `agent` 可选项并在 Claude Desktop/Cowork 中配置服务后，用工具回答"KYB 近 5 年 CDC 阀的技术路线是什么？"，回答中引用的每个公开号都存在于本地库。
2. `tests/test_agent_tools.py` 全部通过；`python scripts/ai_self_audit.py --full` 和 `git diff --check` 保持通过。
3. 核心安装（不含 `agent` 可选项）不变：不新增必需依赖。
