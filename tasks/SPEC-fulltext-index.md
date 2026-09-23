# 规格：本地专利全文索引（市场对标 v2 · A0）

## 目标

把本地库 PDF 预先解析成按段落存储的文本，建立全文索引，让智能体和检索能在**权利要求和说明书全文**中查找，而不是只看题名；阅读全文时直接读缓存，不再每次现场解析 PDF。

起因：2026-09-23 智能体用"复原弹簧"提问时，回答自己写明 `search_library` 只按公开号/题名/申请人/分类号匹配，正文中出现该词的专利会漏检；另有 2 件 PDF 解析不出权利要求。

## 决定（2026-09-23，产品负责人确认）

1. 智能体只查本地索引；回答过程中不联网。联网只在同步阶段补齐本地缺失的文本。
2. 顺序：排在新开发顺序第 2 步，与分类号映射同期或之前完成。
3. 扫描件本地 OCR：**本规格不做**（不新增依赖）。扫描件优先用 EPO OPS 全文补齐；补不到的标记为"需要 OCR"，不猜测内容。是否以后加入 OCR（如 Tesseract + 中文语言包）属于"需要时再问"。

## 技术栈与命令

Python 3.12、现有 SQLite 本地库、PyMuPDF（已有依赖）、SQLite FTS5 的 `trigram` 分词器（SQLite ≥ 3.34；Windows 版 Python 3.12 自带的 SQLite 满足，启动时检测，不满足则退回 LIKE 检索并在状态中说明）。不新增依赖。运行 `python -m pytest tests/test_fulltext_index.py tests/test_agent_tools.py -q`、`python scripts/ai_self_audit.py --full`、`git diff --check`。

## 数据模型（仅新增表，不改现有表）

```sql
CREATE TABLE IF NOT EXISTS library_text_source (
    publication_number TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,      -- 'PDF' | 'EPO_OPS'
    source_ref TEXT NOT NULL,       -- PDF 路径或 OPS 请求说明
    pdf_sha256 TEXT,                -- PDF 内容指纹，用于增量更新
    status TEXT NOT NULL,           -- 'ok' | 'partial' | 'needs_ocr' | 'failed'
    detail TEXT NOT NULL DEFAULT '',
    parsed_at TEXT NOT NULL,
    FOREIGN KEY(publication_number) REFERENCES library_publication(publication_number)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS library_text_segment (
    segment_id INTEGER PRIMARY KEY,
    publication_number TEXT NOT NULL,
    section TEXT NOT NULL,          -- 'claims' | 'description'
    ordinal INTEGER NOT NULL,       -- 段落/权利要求序号，从 1 开始
    claim_number INTEGER,           -- 权利要求编号（能识别时）
    page_start INTEGER,             -- PDF 页码（EPO 文本为空）
    page_end INTEGER,
    text TEXT NOT NULL,
    FOREIGN KEY(publication_number) REFERENCES library_publication(publication_number)
        ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS library_text_fts
    USING fts5(text, content='library_text_segment', content_rowid='segment_id',
               tokenize='trigram');
```

- 同一公开件重新解析时，先删除它的旧段落再写入，保证不残留过期文本。
- 来源优先级：本地 PDF 解析成功 > EPO OPS 全文。两者都有时只保留 PDF 结果，并在 `detail` 中记录。

## 解析规则

- 复用 `app/services/pdf_reader.py` 的章节定位（`_infer_layout`、`_section_text`），扩展为逐页记录页码。
- 权利要求按"1.""2、"等编号切分为独立段；说明书按空行/段落号（如 [0012]、【0012】）切分。
- 判定：某章节文字少于阈值（如 200 字）→ `partial`；整份 PDF 几乎无文字层 → `needs_ocr`；打开失败 → `failed`（记录原因，不中断同步）。
- 增量：PDF 的 SHA-256 未变且状态为 `ok` 时跳过。

## 同步与补齐

- 在 LocalLibrary 同步/补全流程（`app/library/root_sync.py`、`app/library/enrichment.py`）之后增加"全文索引"步骤；桌面"本地专利库"页提供"更新全文索引"按钮和进度（后台线程，不阻塞界面）。
- 对 `needs_ocr`/`failed`/`partial`/无 PDF 的公开件，若已配置 EPO OPS，则调用现有 `get_fulltext_section` 补齐，来源记为 `EPO_OPS`。EPO OPS 全文主要覆盖 EP/WO 等，CN/JP 可能取不到——取不到就保持原状态，不猜。
- 首次对全库（当前约 692 件）建索引需要一段时间，显示进度和可取消；之后为增量。

## 检索规则

- 检索词 ≥ 3 个字符：走 FTS5 trigram 精确子串匹配。
- 检索词 < 3 个字符（如"阀芯"）：退回 `LIKE` 模糊匹配，并在结果 `notes` 中注明。
- 多个检索词：默认"全部包含"；支持 `any` 模式"任一包含"。
- 结果按公开件聚合，每件最多返回 3 个命中片段（命中处前后各约 60 字），并附段落位置（章节、权利要求号/段落号、页码）。

## 智能体工具变化（M1 工具，保持只读、不联网）

| 工具 | 变化 |
| --- | --- |
| `search_library` | 新增 `fulltext`（全文检索词）和 `match`（`all`/`any`）参数；结果增加 `snippets`（片段 + 位置）；原有题名/申请人/分类号匹配保留。 |
| `read_publication_text` | 改为读缓存段落；新增 `claims`（如 `[1, 3]`）和 `from_ordinal`/`limit` 分段读取；返回 `source_type`、`status`、页码；缓存不存在时才现场解析 PDF（不写库，因为连接是只读的），并提示"尚未建索引"。 |
| `library_status` | 增加索引覆盖：已索引件数、各状态件数、需要 OCR 件数、最近更新时间。 |

智能体定义 `library_qa.md` 的步骤更新为优先用 `fulltext` 检索。

## 边界

- 始终：同步阶段才联网；智能体运行期间不联网；每段文本都能追溯到来源（PDF 路径+页码，或 EPO OPS）；解析失败有记录、不中断。
- 始终：只新增表；现有检索、下载、监控、本地库行为不变。私有字段（笔记、项目、标签、监控规则）不进入全文索引。
- 需要时再问：本地 OCR；向量/语义检索（v2 A4，独立决策）；索引 PDF 附图中的文字。
- 绝不：用模型"补全"缺失的专利文本；把 EPO 文本和 PDF 文本拼接成一份而不标来源；从文件名或公开号推断文本内容。

## 测试策略

- 解析：用 PyMuPDF 生成含权利要求/说明书的测试 PDF，验证分段、权利要求编号、页码；无文字层 PDF 判为 `needs_ocr`。
- 增量：同一 PDF 第二次同步被跳过；PDF 变化后旧段落被替换，无残留。
- 检索：中文三字词（"复原弹簧"）在正文命中；两字词走 LIKE 并有说明；`all`/`any` 语义；片段含位置。
- 补齐：用假的 EPO 提供者验证 `needs_ocr` 件被补齐并标 `EPO_OPS`；提供者报错时状态不变、同步不中断。
- 工具：`search_library(fulltext=...)` 与 `read_publication_text` 的返回格式、回执、只读保证（数据库哈希不变）沿用 M1 测试。
- 隐私：笔记内容不会出现在全文检索结果中。

## 验收标准

1. 在真实本地库上建完索引后，智能体再问"复原弹簧相关的技术方案"，能检出正文（而非仅题名）中提到复原弹簧的专利，并引用到具体权利要求或段落。
2. `library_status` 显示索引覆盖和需要 OCR 的件数；这些件在回答的"局限与待确认"中被如实提及。
3. 新测试全部通过；`python scripts/ai_self_audit.py --full` 和 `git diff --check` 保持通过。
