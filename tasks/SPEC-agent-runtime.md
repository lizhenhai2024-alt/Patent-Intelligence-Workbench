# 规格：软件内受控智能体运行框架 — 智能体路线 M2

## 目标

在 `docs/AI_PRODUCT_SPEC.md` 第 11 节的约束下，在桌面程序内运行 Eureka 式任务智能体。每个智能体是一个用户可编辑的 Markdown 定义文件；无论文件怎么写，工具白名单、步数上限、人工确认节点和证据回执都由代码强制执行。M2 交付运行框架和一个演示智能体，正式智能体在 M3/M4。

依赖 M1（`tasks/SPEC-agent-mcp.md`）：智能体工具就是 `app/agent_tools/tools.py` 中的同一批函数，在进程内直接调用（不经过 MCP）。

## 决定

1. 模型：多个云端配置，由用户选择；不做本地部署。
2. 协议：只支持 OpenAI 兼容的 Chat Completions 工具调用，使用现有 `httpx` 依赖。模型下拉框提供下文"模型预设"中的主流厂商，包括小米 MiMo。原生 Anthropic Messages 适配属于"需要时再问"。
3. 定义文件头部用 **TOML**（`+++` 包围，由标准库 `tomllib` 解析）而不是 YAML，因此不新增依赖。
4. 证据校验不通过时只标记输出中的行，不触发模型重试，避免模型悄悄改写自己的证据。

## 项目结构

- `app/agents/definition.py`：解析并校验定义文件，得到冻结的 `AgentDefinition`。
- `app/agents/definitions/*.md`：内置定义（M2 只有演示用的 `library_qa.md`）。
- `app/resources/model_presets.json`：模型下拉框的厂商预设（数据而非代码，厂商换地址不用改代码）。
- `app/agents/model_profiles.py`：`ModelProfile`（名称、预设 id、接口地址、认证方式、模型、temperature），以不含密钥的 JSON 保存；密钥存放在 Windows 凭据管理器 `PatentIntelligenceWorkbench/AI/<配置名>` 下，复用 `app/desktop/credentials.py` 的 Win32 写法。
- `app/agents/runtime.py`：工具调用循环、确认节点、步数上限、运行日志。
- `app/agents/receipts.py`：引用解析、回执校验、越界结论扫描。
- `app/desktop/agent_tab.py`：智能体选择、模型选择、问题输入、同意对话框、确认对话框、带标记的结果视图。
- `tests/test_agents.py`。

## 模型预设

厂商下拉框列出以下预设，外加"自定义"（自填接口地址）。选中预设后自动填好接口地址和认证方式；用户填写密钥，模型名**只能从下拉框选择，不手填**（产品负责人 2026-09-23 决定）。下拉选项来自两处：预设中核实过的 `suggested_models`，以及点"获取模型列表"时从厂商 OpenAI 兼容接口 `GET /models` 实时取回的清单。这样厂商改名时不用改代码。小米 MiMo 的按量付费 Key（`sk-`）和 Token Plan Key（`tp-`）互不通用、地址不同，保存时检查 Key 前缀，不匹配就拒绝并提示改选预设。

| 预设 | 接口地址（自动追加 `/chat/completions`） | 认证方式 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | Bearer |
| Anthropic Claude | `https://api.anthropic.com/v1`（OpenAI SDK 兼容接口） | Bearer |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | Bearer |
| DeepSeek 深度求索 | `https://api.deepseek.com/v1` | Bearer |
| 通义千问 Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Bearer |
| Kimi 月之暗面 | `https://api.moonshot.cn/v1` | Bearer |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | Bearer |
| 豆包 Doubao（火山方舟） | `https://ark.cn-beijing.volces.com/api/v3` | Bearer |
| **小米 MiMo（按量付费，sk- Key）** | `https://api.xiaomimimo.com/v1` | `api-key` 请求头 |
| **小米 MiMo Token Plan（tp- Key）** | `https://token-plan-cn.xiaomimimo.com/v1`（只保留中国区） | `api-key` 请求头 |
| 自定义 | 用户填写 | 用户选择 |

小米 MiMo 已于 2026-09-23 对照其 OpenAI 兼容文档确认：支持函数调用；文档写明的请求头是 `api-key: <key>`；文档列出的模型为 `mimo-v2.6-flash`、`mimo-v2.6-pro`、`mimo-v2.6-pro-ultraspeed`、`mimo-v2.5-pro`、`mimo-v2.5`（即其 `suggested_models`）。其他厂商的接口地址是各自公开的 OpenAI 兼容地址，需要在人工验收时对每家做一次真实的工具调用确认，确认后再补充 `suggested_models`。

运行框架必须处理这些厂商的两个协议细节：

- **认证方式：** `bearer` 发送 `Authorization: Bearer <key>`；`api-key` 发送 `api-key: <key>`。按配置分别保存。
- **思考模式字段：** 部分模型（MiMo 思考模式、DeepSeek 推理模型）在 `tool_calls` 旁返回 `reasoning_content`。发送下一轮时，运行框架原样保留每条助手消息（包括额外字段），保证多轮工具调用不中断。`reasoning_content` 写入运行日志，但不作为答案显示，也不算证据。

## 定义文件格式

```markdown
+++
id = "tech_solution_explore"          # 必须与文件名一致
name = "技术方案探索"
version = 1
description = "从工程问题出发找专利中的解决方案线索"
tools = ["search_library", "get_publication", "read_publication_text", "get_family"]
max_steps = 12                        # 1..30；代码中硬上限 30
checkpoints = ["confirm_search_terms"]
output = "report_with_receipts"
+++

## 目标
...
## 步骤
...
## 输出模板
...
```

校验规则（任何一条不满足，文件即被拒绝加载，并给出指明字段的中文错误）：

| 字段 | 规则 |
| --- | --- |
| `id` | `[a-z0-9_]+`，与文件名一致，所有已加载定义中唯一 |
| `tools` | 非空；每个名称都是 M1 的只读工具 |
| `max_steps` | 1–30 的整数 |
| `checkpoints` | 只能取 `{"confirm_search_terms", "confirm_before_final"}` 中的值 |
| `output` | `report_with_receipts`（M2 唯一类型） |
| 未知字段 | 拒绝（不静默忽略，避免 `max_step` 这类拼写错误让限制失效） |
| 正文 | 必须包含 `## 目标`、`## 步骤`、`## 输出模板` 三个标题 |

有意**不**提供开启法律结论、私有字段访问、写入工具或联网工具的字段。这些只能通过以后的 SPEC 加代码来增加。

系统提示词的组成：代码中固定的约束提示词（引用格式、禁止的结论、只限本地库；不可编辑）+ 定义文件正文 + 用户问题。

## 运行流程

1. 用户选择智能体和模型配置，填写问题。
2. **发送说明**：运行按钮旁常驻显示接口主机和模型，并说明问题和工具返回的公开专利数据会被发送；不再逐次弹窗（产品负责人 2026-09-23 决定）。私有字段永不发送（M1 工具本身不返回）。模型配置统一在“设置 → AI 模型配置”中管理，与大模型翻译共用。
3. 循环：调用模型 → 对每个工具调用：在定义的 `tools` 中就执行并附上结果，否则向模型返回拒绝信息。每次工具调用计一步。
4. 确认节点：
   - `confirm_search_terms`：模型必须先调用伪工具 `propose_search_terms`，程序暂停运行并在可编辑对话框中显示检索词；用户修改后的版本返回给模型。在确认之前调用 `search_library` 会被拒绝。
   - `confirm_before_final`：模型给出最终回答后、结果显示前，由程序暂停，让用户审阅（可修改）。
   - 任一节点取消即结束运行。
5. 运行在以下情况结束：给出最终回答；达到 `max_steps`（程序再请求一次不带工具的最终回答，并说明结果不完整）；取消；模型或网络错误（保留部分日志）。
6. 对最终回答做证据校验（见下），然后显示。

## 证据校验

- 引用格式：`[US20240003400A1]`；一行可引用多个公开号。
- **有效回执** = 本次运行中工具结果里出现过的公开号。仅仅存在于本地库还不够，防止模型凭记忆引用。
- 每个非空、非标题的行都必须至少带一个有效回执；`## 局限与待确认` 一节下的内容除外，表格表头和分隔行也除外。
- 没有回执或引用了未知公开号的行，标记为"⚠ 无证据支撑"，并在顶部汇总计数。这些行永不被静默删除。
- 越界结论扫描：确定性的短语清单（如 具备新颖性、不具备创造性、不构成侵权、侵权风险低/高、与 概率/可能性 相邻的百分比）命中时标记为"⚠ 超出工具边界的结论"。清单只是安全网，不是保证。

## 运行日志

每次运行以 JSON 保存在应用数据目录的 `agent_runs/<时间戳>-<智能体 id>.json`：定义 id + 版本 + SHA-256、配置名、接口主机和模型、问题、每一步（工具、参数、返回的回执）、确认节点的修改、最终文本和被标记的行。API 密钥和完整的 Authorization 请求头永不写入。

## 边界

- 始终：代码强制白名单、步数上限、常驻发送说明、运行日志、证据校验。
- 需要时再问：原生 Anthropic 适配；流式输出；更多确认节点类型；任何写入或联网工具。
- 绝不：把 API 密钥写入 JSON 或日志；发送 `note`/`projects`/`tags`/`watch_rule_ids`；让定义文件扩大权限；为"修复"校验失败而自动重试。

## 测试策略

- 定义校验：表中每条规则一个测试，外加一个合法文件能加载。
- 用脚本化的假模型（`httpx.MockTransport`）测试运行框架：正常工具调用、非白名单工具被拒、达到步数上限、确认节点暂停并用用户修改后的检索词继续、取消、模型 HTTP 错误时保留部分日志。
- 证据：合法引用通过；引用了工具未返回的公开号被标记；无引用行被标记；`## 局限与待确认` 一节豁免；越界短语被标记。
- 密钥：运行后配置 JSON 和运行日志中都不含 API 密钥字符串。
- 预设：`model_presets.json` 每一项都是 HTTPS 地址且认证方式已知；MiMo 预设发送 `api-key` 而不是 `Authorization`；助手消息带 `reasoning_content` 时，下一轮请求原样发回。
- 现有离线测试不需要网络和密钥。

## 验收标准

1. 演示智能体 `library_qa` 至少用两个模型配置（其中一个是小米 MiMo）回答同一个本地库问题，每个回答中的每条引用都通过证据校验。
2. 故意写错的定义文件（未知工具、`max_steps = 99`、字段拼写错误）被拒绝，并给出清楚的提示。
3. 新测试全部通过；`python scripts/ai_self_audit.py --full` 和 `git diff --check` 保持通过。
