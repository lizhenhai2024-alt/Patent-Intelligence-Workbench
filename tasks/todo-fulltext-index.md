# 本地专利全文索引任务清单

- [x] 新表与 trigram 检测。
  - 验收：旧库自动升级、数据不变；trigram 不可用时退回 LIKE 并在状态中说明。
  - 验证：`tests/test_fulltext_index.py`。
- [x] PDF 分段解析与增量更新。
  - 验收：权利要求按编号分段、说明书按段落分段、带页码；无文字层判 `needs_ocr`；PDF 未变则跳过。
  - 验证：`tests/test_fulltext_index.py`。
- [x] 同步集成与 EPO OPS 补齐。（同步后自动索引新 PDF；EPO OPS 补齐仍由阶段 0 补全流程负责）
  - 验收：`choose_library_root` 同步后自动触发全文索引；新增 PDF 在后台线程中被索引。
  - 验证：`fulltext.unindexed_items()` + `index_pdfs()` 自动调用。
- [x] 全文检索。
  - 验收：三字及以上词走 trigram；短词走 LIKE 并注明；片段带位置；笔记不参与。
  - 验证：检索测试。
- [x] 智能体工具升级与 `library_qa.md` 更新。
  - 验收：`fulltext`、`snippets`、分段读取、索引覆盖统计；只读保证不变。
  - 验证：`tests/test_agent_tools.py`。
- [x] 桌面"更新全文索引"。（按钮、进度、取消已完成；真实库人工验收待做）
  - 验收：后台运行、有进度、可取消；在真实库上重问"复原弹簧"能命中正文。
  - 验证：桌面测试 + 人工验收。
