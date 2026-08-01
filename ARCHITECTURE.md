# Architecture: the four-layer Hermes ↔ Codex closed loop

This repository ships the complete integration, not just a plugin. The full stack
looks like this:

```
┌─────────────────────────────────────────────────────────────┐
│                  Layer 1 — Main brain                       │
│  Hermes Agent (memory, persona, orchestration, MCP client)  │
└─────────────────────────────────────────────────────────────┘
        │  main loop (Responses API)          ▲ reverse consult
        ▼                                     │
┌──────────────────────┐        ┌─────────────────────────────┐
│ Layer 2 — Model      │        │ Layer 3a — Reverse consult  │
│ deepseek-responses   │        │ codex-plus-hermes-team MCP  │
│ provider (ds-resp)   │        │  hermes_team_ask_agent      │
│ api_mode:            │        │  ask_panel / kanban tasks   │
│   codex_responses    │        └─────────────────────────────┘
│ base: api.deepseek…  │                     ▲
└──────────────────────┘                     │ hermes_team_*
        │  dispatch                          │
        ▼                                    │
┌─────────────────────────────────────────────────────────────┐
│ Layer 3b — Execution tool (this repo's plugin)              │
│  codex tool → Codex CLI 0.146+                              │
│  DeepSeek official models.json adapter                     │
│  apply_patch native │ effort levels │ no VPN needed         │
└─────────────────────────────────────────────────────────────┘
        │  session artifacts
        ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 4 — Workspace & context bridge                        │
│  Athena backend + MCP bridge (29 tools)                     │
│  recall cache │ session summaries │ memory read/write       │
│  spawn / live-terminal management                           │
└─────────────────────────────────────────────────────────────┘
```

## The closed loop

1. **Hermes thinks** over the native Responses API (`deepseek-responses`
   provider) — full persona, SoulLink-style memory, 1M context.
2. **Hermes dispatches** to Codex via the `codex` tool (this repo).
3. **Codex executes** with DeepSeek's official Codex adaptation
   (apply_patch freeform, reasoning effort levels, multi-agent v2 metadata).
4. **Codex consults Hermes back** through codex-plus-hermes-team MCP
   (`hermes_team_ask_agent` / `ask_panel`).
5. **Context survives sessions** through Athena recall and session summaries.

Any layer can be swapped without touching the others — that is the point of the
layer boundary design.

## Layer ownership

| Layer | Component | In this repo? |
|---|---|---|
| 1 | Hermes Agent | no — [upstream](https://github.com/NousResearch/hermes-agent) |
| 2 | `deepseek-responses` provider config | yes — `config/hermes-config.example.yaml` |
| 3a | codex-plus-hermes-team integration | config template only — [upstream](https://github.com/AlekseiUL/codex-plus-hermes-team) |
| 3b | codex tool plugin | yes — `__init__.py` |
| 4 | Athena bridge integration | config template only — [upstream](https://github.com/luckeyfaraday/Athena) |
| — | dispatch protocol | [hermes-code-bridge](https://github.com/xuyang-liu16/hermes-code-bridge) skill |
