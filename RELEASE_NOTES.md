# Patent Intelligence Workbench v0.1.0 RC1

这是第一个可供 Windows 用户实际试用的 Release Candidate。

## 已实现

- CN / JP / EP / US / WO / KR 专利号标准化
- EPO OPS 专利检索与公开号直查
- 公司 + 技术联合检索
- 中 / 英 / 日减振器技术词典与概念组检索
- DOCDB Simple Family 与 INPADOC Extended Family
- 专利族优先权与成员分析
- 整族 PDF 批量下载、失败重试和来源 fallback
- Patent Watch：公司 / 技术、新 Family、新 Family Member
- 本地 SQLite 专利库
- 标签、项目、收藏、备注、PDF 路径
- CSV / XLSX 导出
- Windows 桌面 UI：Search / Family / Patent Watch / Local Library / Settings
- EPO OPS 凭据保存到 Windows Credential Manager
- Windows one-file EXE 自动构建与打包后 smoke test

## 默认重点公司

Hitachi Astemo、KYB、Tenneco / Monroe、ZF / Sachs、BWI、HL Mando、
thyssenkrupp BILSTEIN、Multimatic、Öhlins、ClearMotion。

## 首次使用

1. 下载 `PatentIntelligenceWorkbench.exe`。
2. 启动后进入 **Settings**。
3. 在 EPO Developer Portal 创建 OPS 应用并取得 Consumer Key / Consumer Secret。
4. 在 Settings 中保存凭据。
5. 使用 Search 搜索专利或公司 + 技术，进入 Family 做专利族分析和整族下载。
6. Patent Watch 默认模板初始为关闭状态，请按需要启用。

EPO OPS 使用 OAuth；官方 Developer Portal 负责注册和应用凭据管理。

## RC1 已知限制

- 当前实时检索主 Provider 为 EPO OPS；其它来源仍以补充/下载 fallback 为主。
- JP/CN/WO 官方网页不做脆弱机器人抓取；自动下载失败时提供官方替代来源提示。
- 正式 Prior Art / 新颖性意见、X/Y/A、Claim Chart、FTO 不在 V1 RC1。
- 图像/附图结构搜索和多模态检索尚未进入 RC1。
- Patent Watch 需要程序运行后执行到期规则；Windows 后台服务化调度尚未进入 RC1。
- RC1 未做代码签名，Windows SmartScreen 可能对首次下载程序给出提示。

## 数据与凭据

- 专利库和监控状态保存在本机用户数据目录。
- EPO Consumer Key / Secret 在 Windows 下存储于 Windows Credential Manager。
- 凭据不会写入 Git 仓库、SQLite 专利库或明文 JSON 配置。
