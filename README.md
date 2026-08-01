<div align="center">

# 🌉 Hermes Codex Router

**The complete Hermes ↔ Codex integration bundle — Codex as a first-class Hermes tool, DeepSeek V4 Flash on the native Responses API, with bidirectional consult and cross-session context.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-2e5a46)](#)
[![Requires](https://img.shields.io/badge/Requires-Hermes%20Agent%20v0.19%2B-6C5CE7)](#)
[![Codex](https://img.shields.io/badge/Codex-0.146%2B-000000)](#)

</div>

---

## The stack at a glance

One picture, the whole architecture — every layer tested and verified end-to-end:

```
┌──────────────────────────────────────────────────────────────┐
│                  LAYER 1 · MAIN BRAIN                         │
│        Hermes Agent — memory, persona, orchestration          │
└──────────────────────────────────────────────────────────────┘
        │  main loop (Responses API)           ▲ reverse consult
        ▼                                      │ (two channels)
┌────────────────────────┐      ┌───────────────────────────────┐
│  LAYER 2 · MODEL       │      │  LAYER 3a · REVERSE CONSULT   │
│  deepseek-responses    │      │  codex-plus-hermes-team MCP   │
│  api_mode:             │      │  hermes_team_ask_agent ✅     │
│    codex_responses     │      │  auto-resume live session ✅  │
│  api.deepseek.com      │      │  model/provider pinned ✅     │
│  1M context · no VPN   │      └───────────────────────────────┘
└────────────────────────┘                   ▲
        │  dispatch                          │ mcp__hermes_team__*
        ▼                                    │
┌──────────────────────────────────────────────────────────────┐
│  LAYER 3b · EXECUTION TOOL (this repo)                       │
│  codex tool → Codex CLI 0.146+                               │
│  DeepSeek official models.json adapter                       │
│  apply_patch native · effort levels · no VPN                 │
└──────────────────────────────────────────────────────────────┘
        │  session artifacts
        ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 4 · CONTEXT & FALLBACK BRIDGE                         │
│  Athena backend /hermes/ask (HTTP, any caller)               │
│  auto-resume live session · recall cache · memory read       │
│  standby role: L2 covers ask; Athena stays as fallback       │
└──────────────────────────────────────────────────────────────┘
```

**简体中文版**

```
┌────────────────────────────────────────────────────────────┐
│                       第 1 层 · 主脑                       │
│             Hermes Agent —— 记忆 · 人设 · 编排             │
└────────────────────────────────────────────────────────────┘
│  主循环（Responses API）       ▲ 反向咨询（双通道）
▼                               │
┌────────────────────────────┐  ┌────────────────────────────┐
│       第 2 层 · 模型       │  │    第 3a 层 · 反向咨询     │
│     deepseek-responses     │  │ codex-plus-hermes-team MCP │
│ api_mode: codex_responses  │  │ hermes_team_ask_agent ✅   │
│      api.deepseek.com      │  │ 自动 resume 当前会话 ✅    │
│     1M 上下文 · 免梯子     │  │ 模型/通道 pin 已修 ✅      │
└────────────────────────────┘  └────────────────────────────┘
│  派发                           ▲ mcp__hermes_team__*
▼                               │
┌────────────────────────────────────────────────────────────┐
│                第 3b 层 · 执行体（本仓库）                 │
│               codex 工具 → Codex CLI 0.146+                │
│               DeepSeek 官方 models.json 适配               │
│            apply_patch 原生 · 推理档位 · 免梯子            │
└────────────────────────────────────────────────────────────┘
│  会话产物
▼
┌────────────────────────────────────────────────────────────┐
│           第 4 层 · 上下文与兜底桥                          │
│        Athena 后端 /hermes/ask（HTTP，任意调用方）          │
│        自动 resume 当前会话 · recall 缓存 · 记忆读取        │
│        备用角色：L2 已覆盖 ask，Athena 降级为兜底           │
└────────────────────────────────────────────────────────────┘
```

**The closed loop**: Hermes thinks on the native Responses API → dispatches to
Codex → Codex executes with DeepSeek's official adaptation → Codex consults
Hermes back through **two verified channels** — native MCP (`hermes_team_ask_agent`,
auto-resumes the live Hermes session) and the HTTP fallback (Athena
`/hermes/ask`, any caller) → context survives sessions (resume, read-only).

---

## Table of Contents

- [The stack at a glance](#the-stack-at-a-glance)
- [What this is](#what-this-is)
- [Quick Start](#quick-start)
- [Repository layout](#repository-layout)
- [Usage](#usage)
- [Orchestration rules](#orchestration-rules)
- [Reverse consult (bidirectional loop)](#reverse-consult-bidirectional-loop)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## What this is

This is **not just a plugin** — it is the assembled, tested recipe for the full
Hermes ↔ Codex closed loop (see the diagram above):

1. **Hermes thinks** over DeepSeek's native Responses API (`deepseek-responses` provider, 1M context)
2. **Hermes dispatches** to Codex through the `codex` tool (this repo's plugin)
3. **Codex executes** with DeepSeek's official Codex adaptation (apply_patch, effort levels, multi-agent v2)
4. **Codex consults Hermes back** — native MCP (`hermes_team_ask_agent`, auto-resumes the live session) or HTTP fallback (Athena `/hermes/ask`)
5. **Context survives sessions** — both channels resume the live Hermes session read-only, so reverse-asks carry the real conversation, not a vacuum

See [ARCHITECTURE.md](ARCHITECTURE.md) for layer ownership details and
[INTEGRATION.md](INTEGRATION.md) for the step-by-step assembly guide
(every step verified on Windows 11).

**Why this combination?**

- DeepSeek officially adapted V4 Flash for Codex (native Responses API, full
  `models.json` metadata, one-click setup) — no other agent CLI gets this depth.
- `api.deepseek.com` is reachable directly from China — **no VPN required**.
- Your API keys never touch disk: everything reads from env / Hermes `.env`.

---

## Quick Start

> Full stack takes ~10 minutes following [INTEGRATION.md](INTEGRATION.md).
> Plugin-only is ~2 minutes if Codex + DeepSeek are already configured.

**Step 0 — health check (recommended):**

```bash
bash scripts/check-setup.sh   # ✅ all green → proceed; ❌ tells you exactly what's missing
```

```bash
# 1. Install the plugin into Hermes
# (ZIP downloads extract to <repo>-main/ — rename or adjust the path)
cp -r hermes-codex-loop /path/to/hermes/runtime-data/plugins/

# 2. Point Codex CLI at DeepSeek (official one-click script — choose deepseek-v4-flash)
#    Windows:  irm https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.ps1 | iex
#    macOS/Linux: bash <(curl -fsSL https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.sh)

# 2b. IMPORTANT — un-break MCP tool visibility (DeepSeek setup pitfall, openai/codex#36382):
#     The official setup writes supports_search_tool=true + tool_mode=null, which
#     silently hides ALL configured MCP tools in exec mode. Fix in ~/.codex/models.json:
#     set "supports_search_tool": false for every deepseek model. check-setup.sh [7/7]
#     detects the conflict automatically.

# 3. Make sure DEEPSEEK_API_KEY is visible to Hermes
export DEEPSEEK_API_KEY="sk-..."        # or put it in your Hermes .env
```

Restart Hermes. You now have a `codex` tool.

**First smoke test** — ask Hermes:

> Use the codex tool to create a hello.py in a git repo and run it.

Expected: Hermes calls `codex`, Codex writes the file, runs it, and reports the real output.

For the full stack (native Responses API main loop + reverse consult + recall),
follow [INTEGRATION.md](INTEGRATION.md) — it's the exact tested path.

---

## Repository layout

```text
hermes-codex-loop/
├── __init__.py                 # the plugin: `codex` tool + guidance + delegate injection
├── README.md                   # you are here
├── ARCHITECTURE.md             # four-layer closed-loop diagram
├── INTEGRATION.md              # step-by-step assembly (verified on Windows 11)
├── config/
│   ├── hermes-config.example.yaml   # deepseek-responses provider + Athena MCP blocks
│   ├── codex-config.example.toml    # ~/.codex/config.toml blocks (deepseek/zen/hermes-team)
│   └── team.example.yaml            # codex-plus-hermes-team team.yaml template
└── LICENSE
```

---

## Usage

### Tool schema

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task` | string | — | What to build/fix/refactor. Be specific: files, expected behavior, constraints. |
| `model` | `flash` \| `pro` | `flash` | `flash` → `deepseek-v4-flash`, `pro` → `deepseek-v4-pro` |
| `directory` | string | cwd | Working directory (should be a git repo) |
| `verify` | bool | `true` | Runs `git diff --stat` after execution |

### Example prompts

```text
# Daily fix
codex(task="Fix the flaky test in tests/auth_test.py and make sure the suite passes",
      directory="/path/to/project")

# Complex architecture work
codex(task="Refactor the auth module into a plugin architecture with clear interfaces",
      model="pro",
      directory="/path/to/project")

# Skip verification for scratch work
codex(task="Scaffold a minimal FastAPI app", verify=false, directory="/tmp/scratch")
```

### What you get back

```json
{
  "status": "ok",
  "model": "deepseek-v4-flash",
  "output": "…real output from Codex…",
  "git_diff_stat": " auth.py | 12 ++++++++++++"
}
```

`status` is based on the real exit code — this plugin never fabricates results.

---

## Orchestration rules

Codex is the **primary coding executor** — Hermes dispatches coding work to
Codex instead of doing it inline. Three constraints + one boundary (inline
one-line edits are allowed; everything else goes to Codex) are codified in
[AGENTS.md](AGENTS.md) and enforced by the plugin's session guidance and
delegate injection.

---

## Reverse consult (bidirectional loop)

Two verified channels let Codex ask Hermes back — both carry the **live
conversation context** (auto `--resume` of the most recent active session,
read-only, no pollution):

| | L2 · native MCP | L1 · HTTP fallback |
|---|---|---|
| How | `mcp__hermes_team__hermes_team_ask_agent` | `curl POST http://127.0.0.1:8390/hermes/ask` |
| Requires | `~/.codex/config.toml` hermes-team MCP + `startup_timeout_sec=120` | Athena backend running (Hermes venv python, PATH prefix) |
| Model pin | `team.yaml`: `model: deepseek-v4-flash`, `provider: deepseek` | built into hermes.py |
| Context | auto-resume live session | auto-resume live session (or explicit `session_id`) |
| Status | ✅ verified (29s round trip, real answer) | ✅ verified (15s round trip) |
| Role | primary channel | fallback / any non-codex caller (scripts, other agents) |

**Codex-side trigger** — `~/.codex/AGENTS.md` (global) defines when to
reverse-ask: project conventions / user preferences / historical decisions
missing and material to the task. Ask once, verbatim `answer`, never block on
failure. Verified live: Codex asked a naming convention mid-task and followed
Hermes's answer (`count_by_extension`).

**MCP toolset status (10 tools)**:

| Tool | Status | Notes |
|---|---|---|
| `hermes_team_ask_agent` | ✅ verified | sync consult, ~15-30s |
| `hermes_team_health` / `list_agents` / `inspect_agent` / `discover_roles` | ✅ present | diagnostics |
| `hermes_team_route` / `ask_panel` | ⏸ single-profile | meaningful with 2+ Hermes profiles |
| `hermes_team_create_task` / `get_task` / `collect_result` | ⏸ needs kanban | set `kanban.enabled: true` + Hermes kanban board |

---

## Configuration

All optional. Defaults work for the common Hermes layout.

| Env var | Default | Purpose |
|---|---|---|
| `CODEX_BIN` | `D:/Agent/codex/node_modules/.bin/codex.cmd` → `codex` on PATH | Codex CLI binary path |
| `HERMES_HOME` | — | Hermes home dir (for `.env` discovery) |
| `HERMES_ENV_FILE` | — | Explicit path to an `.env` file holding `DEEPSEEK_API_KEY` |

**Key lookup order:** `DEEPSEEK_API_KEY` env var → `$HERMES_HOME/.env` → `~/.hermes/.env` → `<cwd>/.env`.

**delegate_task integration:** for coding goals, the plugin auto-injects Codex
execution instructions into subagent context (marked with `codex-injected` to
avoid double injection).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized: Your api key: ****HERE> is invalid` | Codex sends the literal `experimental_bearer_token` placeholder from config.toml | Use `env_key = "DEEPSEEK_API_KEY"` instead of `experimental_bearer_token` |
| Codex writes nothing: "read-only sandbox" even with `--sandbox workspace-write` | Known bug on Windows (codex 0.145/0.146): workspace-write behaves read-only | This plugin already uses `--dangerously-bypass-approvals-and-sandbox` — keep it to trusted directories |
| Tool reports "codex CLI 未找到" | `CODEX_BIN` not set and Codex not on PATH | Set `CODEX_BIN` to your `codex.cmd`/`codex` path, or add Codex to PATH |
| Tool reports "缺少 DEEPSEEK_API_KEY" | Key not in env, Hermes `.env`, or `HERMES_ENV_FILE` | Export the key or add it to one of the `.env` candidates |
| Plugin loads but `codex` tool missing from the toolset | Hermes hasn't reloaded plugins | Restart the Hermes session |
| Athena MCP bridge returns 502 to backend | System proxy (Clash/v2rayN) hijacks localhost via httpx | Set `NO_PROXY=127.0.0.1,localhost` in the MCP server env |
| Athena backend: `ModuleNotFoundError: backend` | Running `backend/launcher.py` directly | Use `python -m backend.launcher` from the repo root |
| Athena `/hermes/ask` → 503 `WinError 2` | backend can't find `hermes` on its process PATH (Windows) | Prefix PATH with hermes.exe's dir when launching backend — see INTEGRATION.md |
| MCP tools silently missing in `codex exec` (hermes-team tools never appear) | DeepSeek official setup writes `supports_search_tool=true` + `tool_mode=null` in models.json — hides all MCP tools (openai/codex#36382) | Set `"supports_search_tool": false` for deepseek models in `~/.codex/models.json`; `check-setup.sh [7/7]` verifies |
| MCP server "was not ready" / tools appear intermittently | hermes-team server starts slower than codex's default MCP timeout | Add `startup_timeout_sec = 120` under `[mcp_servers.hermes-team]` in `~/.codex/config.toml` |
| Reverse-ask returns Zen `401 CreditsError` | hermes-team server didn't pin model/provider → profile falls back to a paid gateway model | `team.yaml`: `model: "deepseek-v4-flash"`, `provider: "deepseek"` (schema must include the fields — keep dist in sync with src if you build manually) |

More traps (Windows build, npm registry, MSYS paths) in [INTEGRATION.md](INTEGRATION.md).

> ⚠️ **Third-party license note**: this repo is MIT and contains no third-party
> source code. It only links to and configures upstream projects. Upstream
> licenses: hermes-agent / hermes-code-bridge / codex-plus-hermes-team are MIT.
> **Athena declares no license** (no LICENSE file as of 2026-08) — check its repo
> before depending on it for your own project.

---

## Acknowledgements

The plugin is a thin, parameterized fork of patterns from; the bundle relies on:

- [deepseek-router](https://github.com/NousResearch/hermes-agent) — in-repo plugin pattern (`register_tool` + `pre_session_init` + `pre_tool_call` hooks)
- [hermes-code-bridge](https://github.com/xuyang-liu16/hermes-code-bridge) — Hermes-as-control-plane dispatch protocols
- [Athena](https://github.com/luckeyfaraday/Athena) — workspace orchestration, Hermes MCP bridge, recall
- [codex-plus-hermes-team](https://github.com/AlekseiUL/codex-plus-hermes-team) — Codex consulting Hermes via MCP
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — the platform this extends
- DeepSeek official Codex integration (models.json, setup scripts)

---

## License

[MIT](LICENSE)
