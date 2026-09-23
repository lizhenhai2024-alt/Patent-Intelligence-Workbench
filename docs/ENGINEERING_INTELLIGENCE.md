# Engineering Intelligence (source checkout)

The desktop **Intelligence** page works on the selected LocalLibrary SQLite collection. It is an engineering research aid, not a substitute for reading patent documents or obtaining legal advice. It is available in the RC preview, with a deliberately bounded local-data and optional-AI workflow.

## Common workflow

1. Add or sync relevant patents to LocalLibrary. For meaningful company charts, assign verified company groups through the existing entity-graph workflow.
2. Open **Intelligence** and select a task card. Read the displayed purpose, required inputs, output and limits before entering information.
3. Check **数据就绪度**. An empty library directs you to Search; a limited library explains missing family, company-group, technology-topic or Watch information. Do not interpret zero counts as a global absence of patents.
4. Run the task. The preview shows the main counts and a continuation action; **保存离线 HTML** saves the full tables, calculation rules and publication receipts.
5. Open the cited publications in Reader/Family before making engineering or legal decisions. External evidence links in HTML are optional and need network access.

| Task | Required input | Output and limits |
| --- | --- | --- |
| 专利全景分析 | Optional topic, jurisdiction and year window | Known-family trend, company and technology nodes, country publication counts and unresolved-family records. Coverage is limited to indexed local records. |
| 公司技术画像 | One exact registered company name or group ID; optional scope | Family-backed technology distribution and representative records. Unknown/ambiguous names are rejected; group membership is not a legal-assignee finding. |
| 竞争格局分析 | At least two exact company groups; optional scope | Side-by-side known-family and technology-node counts. A family can appear in multiple groups; row totals are not additive. |
| 技术路线对比 | At least two taxonomy/technology node IDs or exact names; optional scope | Family-backed route counts and shared coverage. The table does not establish product performance or technical superiority. |
| 工程问题检索 | A stated engineering problem | Multilingual search terms from the local dictionary. Edit the query and explicitly move it to Search; no remote search runs automatically. |
| 新专利监控简报 | Existing archived Watch events | Event-type counts and a reviewable list. Mark events 待复核 / 重要 / 忽略 with a note; the Watch baseline is untouched. Only archived events are included. |

## Counting and provenance

Known families are de-duplicated by nonempty `family_key`; a missing family key remains an unresolved publication, not a presumed one-member family. National publications are counted separately by publication number. Date charts use filing date, falling back to earliest priority date and then publication date, with the chosen basis shown. Technical nodes are derived from stored topics and deterministic title/classification evidence scores. Company-group charts use exact entity mapping, not substring matching or inferred legal ownership.

## Optional AI interpretation

After generating and reviewing a report, you can either use **复制 AI 解读提示词** or pick one of the shared **AI 模型配置** profiles (managed in 设置 → AI 模型配置, the same profiles used by 智能体 and 大模型翻译; keys live in Windows Credential Manager). Since 2026-09-23 the Intelligence page no longer has its own endpoint/model/key fields. The application sends no local data until you press **请求 AI 解读**; a standing notice beside the button states what is sent and where (the consent checkbox was replaced by this notice on 2026-09-23, matching the 智能体 page). The only content sent is the current report's bounded evidence packet: scope, counts, source publication numbers, report rows and limits. The packet instructs the model to separate facts from inferences, cite the supplied publication numbers, identify unknowns, and avoid definitive infringement, FTO, novelty, validity, market-share or performance claims. AI output still needs human checking against the linked patent documents.

## 智能体页面（M2）

桌面程序左侧的 **智能体** 页面运行受控智能体。约束见 `docs/AI_PRODUCT_SPEC.md` 第 11 节，设计见 `tasks/SPEC-agent-runtime.md`。

### 使用步骤

1. **AI 模型配置（在“设置”页）：** 选择厂商预设（OpenAI、Anthropic Claude、Google Gemini、DeepSeek、通义千问、Kimi、智谱 GLM、豆包、小米 MiMo 按量付费、小米 MiMo Token Plan，或自定义），填入 API Key，点“获取模型列表”，再从下拉框选择模型后保存。模型只能下拉选择，不手填。小米 MiMo 的 `sk-` Key 和 `tp-` Key 不能混用，选错预设保存时会提示。配置文件 `model_profiles.json` 不含密钥；Windows 上密钥存进凭据管理器（`PatentIntelligenceWorkbench/AI/<配置名>`），其他系统只在本次运行内存中保留。同一批配置也用于“设置 → 翻译设置”中的“大模型”翻译。
2. **在智能体页选择智能体和模型，填写问题，点“运行”。** 运行按钮下方常驻说明本次会把什么发送到哪个接口：问题和工具查到的公开专利资料会发送；笔记、项目、标签、监控规则不会发送。运行时不再逐次弹窗确认（2026-09-23 决定）。
3. 如果智能体设置了确认节点，运行中会弹出对话框，让你修改检索词或最终回答；点“取消运行”即结束。
4. **结果：** 标题、要点、表格按卡片方式排版，公开号以蓝色显示。没有引用、引用了未返回的公开号、或出现新颖性/侵权/概率类结论的行，会标红并注明原因，但不会被删除。`## 局限与待确认` 一节不要求引用。点“在浏览器中查看结果”可打开排版更完整的 HTML 版本，公开号可点击跳转到 Google Patents。
5. 常见错误会显示中文提示（Key 无效、余额不足、模型名错误等），原始错误信息保留在下方。每次运行的日志和 HTML 结果保存在应用数据目录的 `agent_runs/` 下，日志不含 API Key。

### 编写或修改智能体定义

内置定义在 `app/agents/definitions/`。你自己的定义放在应用数据目录的 `agents/` 文件夹，每个智能体一个 `.md` 文件，写好后点"重新加载定义"。与内置定义 id 重复的文件会被忽略。

```markdown
+++
id = "tech_solution_explore"          # 必须与文件名一致
name = "技术方案探索"
version = 1
description = "从工程问题出发找专利中的解决方案线索"
tools = ["search_library", "get_publication", "read_publication_text", "get_family"]
max_steps = 12
checkpoints = ["confirm_search_terms"]
output = "report_with_receipts"
+++

## 目标
## 步骤
## 输出模板
```

| 字段 | 规则 |
| --- | --- |
| `id` | 小写字母、数字、下划线；与文件名一致；不能重复 |
| `tools` | 非空；只能是 M1 的只读工具：`library_status`、`list_companies`、`list_technology_topics`、`search_library`、`get_publication`、`read_publication_text`、`get_family`、`run_landscape`、`run_company_profile`、`run_comparison` |
| `max_steps` | 1–30 的整数 |
| `checkpoints` | 只能取 `confirm_search_terms`（检索前确认检索词）和 `confirm_before_final`（显示前确认最终回答） |
| `output` | 目前只能是 `report_with_receipts` |
| 其他字段 | 一律拒绝，拼写错误不会被静默忽略 |
| 正文 | 必须有 `## 目标`、`## 步骤`、`## 输出模板` 三个标题 |

不符合规则的文件不会加载，页面上会列出原因。定义文件只能缩小权限（少用工具、少走几步），不能扩大权限：没有任何字段可以开启写入、联网、私有字段或法律结论。
