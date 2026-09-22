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

After generating and reviewing a report, you can either use **复制 AI 解读提示词** or configure a user-chosen OpenAI-compatible **Chat Completions Endpoint**, model and API key in the Intelligence page. The key is held only in the active window. The application sends no local data until you tick the explicit consent box and press **请求 AI 解读**. The only content sent is the current report's bounded evidence packet: scope, counts, source publication numbers, report rows and limits. The packet instructs the model to separate facts from inferences, cite the supplied publication numbers, identify unknowns, and avoid definitive infringement, FTO, novelty, validity, market-share or performance claims. AI output still needs human checking against the linked patent documents.
