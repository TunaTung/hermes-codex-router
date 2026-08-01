<div align="center">

# 🌉 Hermes Codex Router

**Give Codex CLI first-class citizenship inside Hermes Agent — wired to DeepSeek V4 Flash via the official Responses API.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-2e5a46)](#)
[![Requires](https://img.shields.io/badge/Requires-Hermes%20Agent%20v0.19%2B-6C5CE7)](#)
[![Codex](https://img.shields.io/badge/Codex-0.146%2B-000000)](#)

</div>

---

## Table of Contents

- [What this does](#what-this-does)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)
- [How it fits the ecosystem](#how-it-fits-the-ecosystem)
- [Troubleshooting](#troubleshooting)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## What this does

Hermes Agent is your main brain — memory, persona, orchestration. Coding CLIs like Codex are the hands. This plugin makes the hand a **native Hermes tool**, the same way `opencode` already is:

```text
You
  └─> Hermes (main brain: memory, persona, orchestration)
        └─> codex tool  ← this plugin
              └─> Codex CLI 0.146+ (custom provider: DeepSeek official Responses API)
                    └─> api.deepseek.com/v1/responses
```

**Why Codex + DeepSeek specifically?**

- DeepSeek officially adapted V4 Flash for Codex: native Responses API, full `models.json` metadata (1M context, reasoning effort levels, multi-agent v2), one-click setup scripts. No other agent CLI gets this depth of adaptation.
- `api.deepseek.com` is reachable directly from China — **no VPN required**.
- Your API key never touches disk in this plugin: it is injected from env / Hermes `.env` at call time.

---

## Quick Start

> Full setup takes about 2 minutes if Codex CLI and DeepSeek are already configured.

```bash
# 1. Install the plugin into Hermes
cp -r hermes-codex-router /path/to/hermes/runtime-data/plugins/

# 2. Point Codex CLI at DeepSeek (official one-click script — choose deepseek-v4-flash)
#    Windows:  irm https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.ps1 | iex
#    macOS/Linux: bash <(curl -fsSL https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.sh)

# 3. Make sure DEEPSEEK_API_KEY is visible to Hermes
export DEEPSEEK_API_KEY="sk-..."        # or put it in your Hermes .env
```

Restart Hermes. You now have a `codex` tool.

**First smoke test** — ask Hermes:

> Use the codex tool to create a hello.py in a git repo and run it.

Expected: Hermes calls `codex`, Codex writes the file, runs it, and reports the real output.

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

## Configuration

All optional. Defaults work for the common Hermes layout.

| Env var | Default | Purpose |
|---|---|---|
| `CODEX_BIN` | `D:/Agent/codex/node_modules/.bin/codex.cmd` → `codex` on PATH | Codex CLI binary path |
| `HERMES_HOME` | — | Hermes home dir (for `.env` discovery) |
| `HERMES_ENV_FILE` | — | Explicit path to an `.env` file holding `DEEPSEEK_API_KEY` |

**Key lookup order:** `DEEPSEEK_API_KEY` env var → `$HERMES_HOME/.env` → `~/.hermes/.env` → `<cwd>/.env`.

**delegate_task integration:** for coding goals, the plugin auto-injects Codex execution instructions into subagent context (marked with `codex-injected` to avoid double injection).

---

## How it fits the ecosystem

| Layer | Project | Role | Status |
|---|---|---|---|
| Execution tool | **this plugin** | Codex as a native Hermes tool | ✅ you are here |
| Reverse consult | [codex-plus-hermes-team](https://github.com/AlekseiUL/codex-plus-hermes-team) | Codex asks Hermes profiles (ask/panel/kanban) via MCP | complementary |
| Workspace orchestration | [Athena](https://github.com/luckeyfaraday/Athena) | Hermes MCP bridge: recall, sessions, spawn (29 tools) | complementary |
| Dispatch protocol | [hermes-code-bridge](https://github.com/xuyang-liu16/hermes-code-bridge) | Hermes as control plane: session-first routing, evidence ladder | complementary |

Together: **Hermes dispatches → Codex executes → Codex can consult Hermes back → context survives across sessions.**

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized: Your api key: ****HERE> is invalid` | Codex sends the literal `experimental_bearer_token` placeholder from config.toml | Use `env_key = "DEEPSEEK_API_KEY"` instead of `experimental_bearer_token` |
| Codex writes nothing: "read-only sandbox" even with `--sandbox workspace-write` | Known bug on Windows (codex 0.145/0.146): workspace-write behaves read-only | This plugin already uses `--dangerously-bypass-approvals-and-sandbox` — keep it to trusted directories |
| Tool reports "codex CLI 未找到" | `CODEX_BIN` not set and Codex not on PATH | Set `CODEX_BIN` to your `codex.cmd`/`codex` path, or add Codex to PATH |
| Tool reports "缺少 DEEPSEEK_API_KEY" | Key not in env, Hermes `.env`, or `HERMES_ENV_FILE` | Export the key or add it to one of the `.env` candidates |
| Plugin loads but `codex` tool missing from the toolset | Hermes hasn't reloaded plugins | Restart the Hermes session |

---

## Acknowledgements

This plugin is a thin, parameterized fork of patterns from:

- [deepseek-router](https://github.com/NousResearch/hermes-agent) — in-repo plugin pattern (`register_tool` + `pre_session_init` + `pre_tool_call` hooks)
- [hermes-code-bridge](https://github.com/xuyang-liu16/hermes-code-bridge) — Hermes-as-control-plane dispatch protocols
- [Athena](https://github.com/luckeyfaraday/Athena) — workspace orchestration, Hermes MCP bridge, recall
- [codex-plus-hermes-team](https://github.com/AlekseiUL/codex-plus-hermes-team) — Codex consulting Hermes via MCP
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — the platform this plugin extends
- DeepSeek official Codex integration (models.json, setup scripts)

---

## License

[MIT](LICENSE)
