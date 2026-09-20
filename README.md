# Patent Intelligence Workbench

面向工程师的专利搜索、专利族分析、批量下载、竞争对手监控和本地知识整理工具。

**当前版本：v0.1.0 RC1**

## Windows 快速开始

1. 从 GitHub Releases 下载 `PatentIntelligenceWorkbench.exe`。
2. 直接运行，无需安装 Python。
3. 进入 **Settings** 配置 EPO OPS Consumer Key / Consumer Secret。
4. 在 **Search** 中输入专利号、技术词，或选择“公司 + 技术”。
5. 双击结果进入 **Family**，查看 DOCDB Simple Family / INPADOC Extended Family。
6. 可将整族加入 **Local Library**，或执行整族 PDF 下载。
7. 在 **Patent Watch** 中按需启用默认监控规则。

EPO OPS 注册和应用凭据请使用官方 Developer Portal：

https://developers.epo.org/

Windows 下 EPO 凭据保存在系统 **Credential Manager**，不会写入 SQLite、JSON 或 Git 仓库。

## V1 / RC1 功能

- Patent Search
  - 专利号直查
  - 文字搜索
  - 公司搜索
  - 公司 + 技术搜索
  - 中 / 英 / 日减振器技术词扩展
- Patent Family
  - DOCDB Simple Family
  - INPADOC Extended Family
  - Priority 与 CN / JP / EP / US / WO / KR 成员
- Download Center
  - 单件 / 整族 PDF
  - Provider fallback
  - PDF 校验
  - 缓存与失败成员重试
  - family.json manifest
- Patent Watch
  - 公司 / 公司 + 技术
  - NEW_FAMILY
  - NEW_FAMILY_MEMBER
  - SQLite 状态持久化
  - 周期规则和运行历史
- Local Library
  - Family / Publication 分层存储
  - 收藏、备注、标签、项目
  - PDF 本地路径
  - Watch 来源
  - CSV / XLSX 导出
- Company Entity Graph
  - 历史申请人
  - IP holding entity
  - 技术前身
  - 并购专利组合
  - Security Interest 防污染

## 核心国家 / 地区

CN / JP / EP / US / WO / KR

JP 是一级支持区域。数据模型已预留 IPC、CPC、FI、F-term、Theme Code。

## 默认重点公司

- Hitachi Astemo
- KYB
- Tenneco / Monroe
- ZF / Sachs
- BWI
- HL Mando
- thyssenkrupp BILSTEIN
- Multimatic
- Öhlins
- ClearMotion

JTEKT 不在默认减振器核心监控列表中。

## RC1 边界

以下能力不进入首个 RC：

- 正式 Prior Art / 新颖性法律意见
- X/Y/A 文献评价
- Claim Chart
- FTO
- 图像 / 附图结构相似搜索
- 多模态检索
- Windows 后台服务化自动监控

JP / CN / WO 官方网页不会通过脆弱机器人方式抓取；自动 PDF 获取失败时会给出官方人工/注册/授权来源提示。

## 数据目录

默认 Windows 数据目录：

`%LOCALAPPDATA%\PatentIntelligenceWorkbench`

包含：

- `patent_library.db`
- `patent_watch.db`
- `downloads\`
- `exports\`

可通过环境变量 `PIW_DATA_DIR` 覆盖。

## 开发

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m app.desktop.main --smoke --data-dir ./tmp-smoke
```

Windows EXE：

```bash
python -m pip install -e ".[build]"
pyinstaller --noconfirm --clean --onefile --windowed \
  --name PatentIntelligenceWorkbench \
  --collect-data app.resources \
  app/desktop/main.py
```

## 架构原则

1. Normalize before search.
2. Family 是主要分析单元，Publication 是具体文献单元。
3. Original Assignee / Current Assignee / Security Interest 分离。
4. 公司历史用 Entity Graph，而不是平铺 alias。
5. Provider 可替换；Family/Search/Download 上层不绑定单一来源。
6. 自动下载失败必须留下可追溯来源和官方 fallback。
7. Release 必须通过 Windows + Ubuntu CI 和打包后 EXE smoke test。

## License

MIT
