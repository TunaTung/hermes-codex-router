# Integration guide — assemble the full stack

Step-by-step, tested on Windows 11 (git-bash), Hermes Agent v0.19.0, Codex CLI 0.146.0.

> Every step below was executed and verified on the author's machine. Where a
> step hides a known trap, it is called out with ⚠️.

---

## Prerequisites

- Hermes Agent v0.19.0+ (`hermes` CLI reachable)
- Node.js 20+ (for codex-plus-hermes-team MCP server)
- DeepSeek API key (`DEEPSEEK_API_KEY`)

---

## Step 1 — Codex CLI with DeepSeek official provider

Use DeepSeek's one-click script (recommended) or manual config:

```bash
# Windows PowerShell:
irm https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.ps1 | iex
# macOS/Linux:
bash <(curl -fsSL https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.sh)
```

The script backs up `~/.codex/config.toml`, writes `~/.codex/models.json`
(full metadata for `deepseek-v4-flash` + `deepseek-v4-pro`) and adds the
`[model_providers.deepseek]` section.

**Manual fallback** — see `config/codex-config.example.toml`.

⚠️ **Placeholder gotcha**: if you hand-edit and leave
`experimental_bearer_token = "<PASTE_YOUR_DEEPSEEK_API_KEY_HERE>"` in place,
Codex will send the literal placeholder → `401`. Use `env_key = "DEEPSEEK_API_KEY"`
instead (key stays in env, never on disk).

Verify:

```bash
codex exec "Reply with exactly: OK"     # banner must show model/provider: deepseek
```

⚠️ Windows sandbox bug: `--sandbox workspace-write` behaves read-only on
Windows (codex 0.145/0.146). Use `--dangerously-bypass-approvals-and-sandbox`
inside trusted directories only.

---

## Step 2 — Hermes main loop over the native Responses API

Append to Hermes `config.yaml` (see `config/hermes-config.example.yaml`):

```yaml
providers:
  deepseek-responses:
    name: DeepSeek Responses
    base_url: https://api.deepseek.com/
    api_mode: codex_responses      # Hermes speaks Responses API natively
    key_env: DEEPSEEK_API_KEY
    context_length: 1048576        # 1M context
    default_model: deepseek-v4-flash

model:
  aliases:
    ds-resp: deepseek-responses/deepseek-v4-flash   # /model ds-resp to switch
```

Verify (single-shot, no session side effects):

```bash
hermes chat -q "Reply with exactly: DS-RESP-OK" \
  --provider deepseek-responses --model deepseek-v4-flash -Q
# expect: DS-RESP-OK
```

> The trailing `RuntimeError: Event loop is closed` from MCP cleanup at exit is
> cosmetic noise in one-shot CLI mode — ignore it.

---

## Step 3 — Install this plugin

```bash
cp -r hermes-codex-router /path/to/hermes/runtime-data/plugins/
# env: CODEX_BIN / HERMES_HOME / HERMES_ENV_FILE (all optional)
```

Restart Hermes. The `codex` tool appears in the `codex` toolset.

---

## Step 4 — Reverse consult: codex-plus-hermes-team

```bash
git clone https://github.com/AlekseiUL/codex-plus-hermes-team.git
cd codex-plus-hermes-team && npm install && npm run build   # ⚠️ see build trap below
```

Create `team.yaml` (template in `config/team.example.yaml`), then add to
`~/.codex/config.toml`:

```toml
[mcp_servers.hermes-team]
command = "node"
args = ["/abs/path/to/codex-plus-hermes-team/dist/index.js"]

[mcp_servers.hermes-team.env]
CODEX_PLUS_HERMES_TEAM_CONFIG = "/abs/path/to/codex-plus-hermes-team/team.yaml"
```

⚠️ **Windows build trap**: with npm 11 + npmmirror registry, `typescript` may
silently not install. Build with a pinned npx instead:

```bash
npx -y -p typescript@5.8.3 tsc -p tsconfig.json
```

Verify: `codex exec "list your MCP tools"` should show `hermes_team_*`.

---

## Step 5 — Workspace & context bridge: Athena

```bash
git clone https://github.com/luckeyfaraday/Athena.git
cd Athena
# backend (headless, no Electron needed for Hermes coordination):
python -m backend.launcher --host 127.0.0.1 --port 8390
```

Add to Hermes `config.yaml` (see `config/hermes-config.example.yaml`):

```yaml
mcp_servers:
  context_workspace:
    command: "<your-python>"
    args: ["/abs/path/to/Athena/mcp_server/server.py"]
    timeout: 120
    connect_timeout: 30
    env:
      CONTEXT_WORKSPACE_BACKEND_URL: "http://127.0.0.1:8390"
      NO_PROXY: "127.0.0.1,localhost"
```

⚠️ **Windows traps**:
- Run the backend with `python -m backend.launcher` — running
  `backend/launcher.py` directly fails with `ModuleNotFoundError: backend`.
- With Clash/v2rayN system proxy enabled, the MCP bridge returns 502 to the
  backend unless `NO_PROXY=127.0.0.1,localhost` is set (httpx honors WinINET
  system proxy).

Verify: `hermes chat -q "list context_workspace tools"` → 29 tools, or call
`context_workspace_health`.

---

## Step 6 — Optional: codex skills for Athena

```bash
mkdir -p ~/.codex/skills
cp -r Athena/agent-skills/athena-context-workspace ~/.codex/skills/
```

Teaches Codex when/how to `ask hermes` through Athena's route.

---

## End-to-end verification

1. `/model ds-resp` → Hermes main loop on native Responses API.
2. Ask Hermes to "use the codex tool to fix X in repo Y".
3. Watch Codex execute; Hermes reports real output + `git diff --stat`.
4. Ask Hermes to have codex "ask hermes about Z" → `hermes_team_ask_agent`
   round-trips through the MCP server.
5. `context_workspace_write_recall_cache` → context survives into the next
   session.
