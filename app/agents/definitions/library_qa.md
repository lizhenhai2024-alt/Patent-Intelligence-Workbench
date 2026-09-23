+++
id = "library_qa"
name = "本地库问答（演示）"
version = 2
description = "基于本地专利库回答一个工程问题，每条结论附公开号"
tools = ["library_status", "list_companies", "list_technology_topics", "search_library", "get_publication", "read_publication_text", "get_family"]
max_steps = 12
checkpoints = []
output = "report_with_receipts"
+++

## 目标

用本地专利库回答用户提出的一个具体工程问题，例如“KYB 近 5 年 CDC 阀的技术路线是什么？”。

## 步骤

1. 涉及公司时，先调用 list_companies 确认精确的公司名。
2. 优先用 search_library 的 fulltext 参数在权利要求和说明书全文中检索（每个词尽量 3 个字以上），结果里的 snippets 说明命中在第几条权利要求或第几段；必要时换用中、英、日关键词再检索。text 参数只查题名，作为补充。
3. 对最相关的 3–8 件，用 get_publication 看著录信息，用 read_publication_text 读相关的权利要求（可用 claims 参数只读其中几条）。
4. 引用时尽量写明位置，例如“权利要求 2”或“说明书第 12 段”。
5. 按技术方案归纳：结构、油路/力路、控制方式、解决的问题。
6. 检索结果太少时，如实说明本地库覆盖不足，不要用自身知识补充专利事实。

## 输出模板

## 结论
（2–4 条要点，每条附公开号，如 [CN120100850A]）

## 技术方案归纳
| 方案 | 关键结构 | 解决的问题 | 证据 |
|---|---|---|---|

## 局限与待确认
（本地库覆盖范围、未读全文的公开件、需要人工复核的点）
