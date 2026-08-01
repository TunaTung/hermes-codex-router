# Hermes Codex Router

Make **Codex CLI** a first-class tool inside [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — alongside OpenCode, Claude Code, and other coding agents.

`codex` becomes a native Hermes tool (`task` / `model` / `directory` / `verify`), wired to **DeepSeek V4 Flash via the official Responses API adapter** (no proxy needed in China, no API key stored on disk).

```
User
  -> Hermes (main brain: memory, persona, orchestration)
    -> codex tool (this plugin)
      -> Codex CLI 0.146 (custom provider: DeepSeek official Responses API)
        -> api.deepseek.com/v1/responses
```

## Why

- DeepSeek officially adapted V4 Flash for Codex (native Responses API, `models.json` metadata, one-click setup script). This plugin exposes that adaptation to Hermes as a first-class tool.
- Bidirectional orchestration: Hermes dispatches to Codex, and Codex can consult Hermes back through [codex-plus-hermes-team](https://github.com/AlekseiUL/codex-plus-hermes-team) MCP — the two projects are complementary.
- China network: `api.deepseek.com` is reachable directly, no VPN required.

## Install

```bash
# 1. Put the plugin in your Hermes plugins dir
cp -r hermes-codex-router /path/to/hermes/runtime-data/plugins/

# 2. Configure Codex CLI for DeepSeek (official one-click script or manual)
#    https://api-docs.deepseek.com/quick_start/agent_integrations/codex/

# 3. Make sure DEEPSEEK_API_KEY is available (env var, or Hermes .env)
```

Restart Hermes. The `codex` tool appears in the `codex` toolset.

## Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `CODEX_BIN` | `D:/Agent/codex/node_modules/.bin/codex.cmd` → `codex` | Codex CLI binary path |
| `HERMES_HOME` | — | Hermes home (for `.env` discovery) |
| `HERMES_ENV_FILE` | — | Explicit `.env` path for `DEEPSEEK_API_KEY` |

Key lookup order: `DEEPSEEK_API_KEY` env → `HERMES_HOME/.env` → `~/.hermes/.env` → `cwd/.env`.

## Tool schema

```
codex(task, model=flash|pro, directory, verify=true)
```

- `flash` → `deepseek-v4-flash` (default)
- `pro` → `deepseek-v4-pro`
- `verify` runs `git diff --stat` after execution
- Runs with `--dangerously-bypass-approvals-and-sandbox` — use inside trusted directories only

## Known pitfalls (tested 2026-08)

- **Windows sandbox bug**: `--sandbox workspace-write` behaves read-only on Windows (codex 0.145/0.146). Use `--dangerously-bypass-approvals-and-sandbox` in trusted dirs (this plugin does).
- **`experimental_bearer_token` placeholder gotcha**: Codex sends the literal placeholder as the API key → 401. Use `env_key = "DEEPSEEK_API_KEY"` instead.
- **Key extraction on Windows/git-bash**: use `D:/` paths when reading `.env` (MSYS `/d/` prefixes break Windows curl/python).

## Acknowledgements

This plugin is a thin, parameterized fork of patterns from:

- [deepseek-router](https://github.com/NousResearch/hermes-agent) (in-repo plugin pattern: `register_tool` + `pre_session_init` + `pre_tool_call` hooks)
- [hermes-code-bridge](https://github.com/xuyang-liu16/hermes-code-bridge) — Hermes-as-control-plane dispatch protocols (session-first routing, evidence ladder)
- [Athena](https://github.com/luckeyfaraday/Athena) — workspace orchestration, Hermes MCP bridge, recall (29 tools)
- [codex-plus-hermes-team](https://github.com/AlekseiUL/codex-plus-hermes-team) — Codex consulting Hermes profiles via MCP (10 tools)
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — the platform this plugin extends
- DeepSeek official Codex integration (models.json, setup scripts)

## License

MIT
