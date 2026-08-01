# AGENTS.md

## 项目定位

hermes-codex-loop 让 Codex CLI 成为 Hermes Agent 的一等公民工具——走 DeepSeek V4 Flash 官方 Responses API 适配（原生协议、官方 models.json、1M 上下文）。

## 编码执行纪律：三层约束 + 一个边界

保证"有编码任务时派给 codex，而不是自己开干"。

### 约束 1 — codex 是唯一执行体（硬规则）

- 新功能、重构、跨文件修改、修 bug（需读多文件）、写测试、跑测试、代码审查 → **codex 工具**
- 无兜底执行体（opencode 已于 2026-08-01 弃用归档）

### 约束 2 — delegate 注入

- 编码类 `delegate_task` 自动注入 codex 执行指令（`codex-injected` 标记防重复注入）

### 约束 3 — 工具可见

- `codex` 是注册工具（toolset: codex），所有调用全程可见、可审计

### 边界 — 单点小改自己干

- 一行 patch、单点配置修改 → 直接改，不派 codex（避免过度派发）
- 判断标准：**多文件 / 新功能 / 重构 / 测试 → codex；单点小改 → 直接改**
- 用户明确指令优先于以上规则

## 验证

- 编码任务后：检查 git diff 与测试输出，不轻信自报告
- CI：`python -m unittest discover -s tests -v`
- 环境体检：`bash scripts/check-setup.sh`（✅ 全绿再动手，❌ 缺什么一目了然）

## Codex 反问 Hermes（反向咨询开关）

Codex 编码过程中拿不准项目约定 / 用户偏好 / 历史决策时，可反问 Hermes
获取上下文。规则全文在 `~/.codex/AGENTS.md`（codex 全局加载）；核心：

- **方式**：curl `POST http://127.0.0.1:8390/hermes/ask`，body
  `{"project_dir": "<cwd>", "question": "...", "timeout_seconds": 40}`，
  加 `--noproxy "*"`；Windows 引号转义用 `--data-binary "@文件"` 传
- **回答**：取响应 `answer` 字段原样使用
- **边界**：信息缺失且影响决策才问；失败不卡任务，按最佳判断继续
