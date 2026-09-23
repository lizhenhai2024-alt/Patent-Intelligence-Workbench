# 智能体运行框架（M2）实施计划

前提：M1 的 `app/agent_tools/tools.py` 已合入。

1. `app/agents/definition.py` + 演示定义 `library_qa.md`。
   - 检查点：每条校验规则都有测试；演示定义能加载。
2. `app/resources/model_presets.json` + `app/agents/model_profiles.py`：预设（含小米 MiMo）、配置 JSON、凭据管理器密钥、按配置区分认证方式。
   - 检查点：往返测试；密钥从不出现在 JSON 文件中；MiMo 预设使用 `api-key` 请求头。
3. `app/agents/receipts.py`：引用解析、回执校验、越界短语扫描。
   - 检查点：证据测试通过，包括豁免章节。
4. `app/agents/runtime.py`：循环、白名单、步数上限、确认节点、运行日志。
   - 检查点：假模型测试通过；运行日志不含密钥。
5. `app/desktop/agent_tab.py`：选择器、同意对话框、确认对话框、带标记的结果视图；后台工作走现有异步机制（工作线程不直接调用 Tk）。
   - 检查点：桌面冒烟测试；按验收标准用两个真实模型配置人工运行。
6. 文档：在 `docs/ENGINEERING_INTELLIGENCE.md` 中增加编写定义文件的说明；更新 ROADMAP。
   - 检查点：完整自检和 `git diff --check`。

## 边界

- 始终：只做新增；现有 `ai_interpreter.py` 报告解读功能保持不变。
- 需要时再问：把 `ai_interpreter.py` 迁移到模型配置上（顺理成章的后续工作，不属于 M2）。
- 绝不：新增必需依赖。
