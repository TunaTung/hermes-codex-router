"""
codex-router — Hermes → Codex CLI 集成插件。

与 deepseek-router（opencode）平行：codex 成为 Hermes 一等公民工具。
保留 opencode 集成不动；本插件让 codex 作为第二编码执行体可用。

核心事实（2026-08-01 实测）：
- Codex 0.146 + DeepSeek V4 Flash 官方 provider（Responses API 原生适配）
- api.deepseek.com 国内直连，不需要梯子
- Windows 上 --sandbox workspace-write 有 bug（0.145/0.146 均表现为只读）
  → 用 --dangerously-bypass-approvals-and-sandbox（受控目录 + 单机可接受）
- ~/.codex/config.toml 已配好 [model_providers.deepseek] + models.json
"""

from __future__ import annotations
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 配置（环境变量可覆盖，默认适配 Hermes 常见布局）──

_HERMES_ENV = Path(os.environ.get("HERMES_HOME", "")) if os.environ.get("HERMES_HOME") else None
_ENV_CANDIDATES = [
    p for p in [
        _HERMES_ENV / ".env" if _HERMES_ENV else None,
        Path(os.environ.get("HERMES_ENV_FILE", "")) if os.environ.get("HERMES_ENV_FILE") else None,
        Path.home() / ".hermes" / ".env",
        Path.cwd() / ".env",
    ] if p is not None
]

# 优先用 CODEX_BIN 指定的 codex（默认 D:\Agent\codex 的 0.146；PATH 里的 0.145 有 workspace-write 沙箱 bug）
_CODEX_CANDIDATES = [
    c for c in [
        os.environ.get("CODEX_BIN", ""),
        "D:/Agent/codex/node_modules/.bin/codex.cmd",
        "codex",
    ] if c
]

_DEFAULT_MODEL = "deepseek-v4-flash"
_PRO_MODEL = "deepseek-v4-pro"
_KEY_VAR = "DEEPSEEK_API_KEY"

CODEX_TOOL_SCHEMA = {
    "name": "codex",
    "description": (
        "编码工具（备选执行体）——用 Codex CLI 执行编码任务，走 DeepSeek V4 Flash 官方 Responses API。"
        "当 opencode 不可用或需要 Codex 协议层适配（Responses API、multi-agent v2、1M context）时使用。"
        "日常编码优先用 opencode（免费）；codex 是官方深度适配路径，flash 默认，pro 选复杂任务。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "编码任务描述。要具体：改什么文件、预期行为、约束条件。",
            },
            "model": {
                "type": "string",
                "enum": ["flash", "pro"],
                "description": (
                    "模型选择：flash（默认）deepseek-v4-flash；pro 用 deepseek-v4-pro。"
                    "复杂/架构/审查选 pro。"
                ),
                "default": "flash",
            },
            "directory": {
                "type": "string",
                "description": "工作目录（必须）。默认当前会话目录。",
            },
            "verify": {
                "type": "boolean",
                "description": "自动验证：执行后跑 git diff --stat。默认开启。",
                "default": True,
            },
        },
        "required": ["task"],
    },
}

SESSION_GUIDANCE = """
## Codex 编码工具（首选执行体）

你有一个 `codex` 工具（Codex CLI + DeepSeek V4 Flash 官方适配），这是你写代码的**首选方式**。

**什么时候用 codex（硬规则）：**
- 任何写新代码、新功能、重构、跨文件修改、修 bug 需要读多个文件的场景 → 优先 codex
- 写测试、跑测试验证 → codex
- 代码审查 → codex（model="pro"）
- opencode 仅作为兜底：codex 不可用/报错/超时 时才考虑

**什么时候用自己的工具（保持）：**
- 读文件 → read_file
- 单行修补、改配置 → patch（一行能解决的不用派 codex）
- 跑单条命令 → terminal
- 调研、查资料 → web_search / delegate_task

**模型选择：**
- 日常开发：model="flash" → deepseek-v4-flash
- 复杂/架构/审查：model="pro" → deepseek-v4-pro

**注意事项：**
- codex 需要 git 仓库目录（非 git 目录会拒绝执行）
- Windows 上 codex 沙箱参数固定为 full-access（受控目录内使用）
- 执行后检查 git diff 和测试输出，不轻信自报告
"""

# ── key 获取：优先环境变量，其次 Hermes .env ──


def _get_api_key() -> str:
    v = os.environ.get(_KEY_VAR, "")
    if v:
        return v
    for p in _ENV_CANDIDATES:
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith(f"{_KEY_VAR}="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            continue
    return ""


def _find_codex() -> str:
    for c in _CODEX_CANDIDATES:
        if c == "codex":
            found = shutil.which("codex")
            if found:
                return found
        elif Path(c).exists():
            return c
    return ""


# ── 工具 handler ──


def _codex_handler(args: dict, **kwargs) -> str:
    task = (args.get("task") or "").strip()
    if not task:
        return json.dumps({"error": "task is required"})

    model_choice = (args.get("model") or "flash").strip()
    directory = (args.get("directory") or "").strip() or os.getcwd()
    verify = args.get("verify", True)

    codex_bin = _find_codex()
    if not codex_bin:
        return json.dumps({"error": "codex CLI 未找到：set CODEX_BIN or add codex to PATH"})

    api_key = _get_api_key()
    if not api_key:
        return json.dumps({"error": f"缺少 {_KEY_VAR}（环境变量或 Hermes .env）"})

    model = _PRO_MODEL if model_choice == "pro" else _DEFAULT_MODEL

    cmd = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model", model,
        task,
    ]
    env = os.environ.copy()
    env[_KEY_VAR] = api_key

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=directory,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "timeout", "error": "执行超时（10 分钟）"})
    except Exception as e:
        return json.dumps({"status": "error", "error": f"执行失败: {e}"})

    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    text = output.strip()

    response = {
        "status": "ok" if result.returncode == 0 else "error",
        "model": model,
        "output": text[-5000:],
    }
    if result.stderr:
        response["stderr"] = result.stderr[-1000:]

    if verify:
        try:
            v = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=directory, timeout=30,
            )
            response["git_diff_stat"] = v.stdout.strip() or "(no changes tracked)"
        except Exception:
            response["git_diff_stat"] = "(git diff 不可用)"

    return json.dumps(response, ensure_ascii=False)


# ── pre_session_init hook：注入引导规则（与 opencode 引导并存）──


def _inject_session_guidance(**kwargs):
    agent = kwargs.get("agent")
    if agent is None:
        return
    if hasattr(agent, "valid_tool_names") and "codex" in agent.valid_tool_names:
        if not hasattr(agent, "_codex_guidance_injected"):
            if hasattr(agent, "extra_system_prompt"):
                agent.extra_system_prompt = (
                    (agent.extra_system_prompt or "") + "\n\n" + SESSION_GUIDANCE
                )
                agent._codex_guidance_injected = True
                logger.info("codex guidance injected into system prompt")


# ── pre_tool_call hook：编码类 delegate_task 注入 codex 指令（备选执行体声明）──

_CODEX_CONTEXT_INJECTION = """

## 执行指令（自动注入·首选执行体）
编码任务优先用 Codex CLI（DeepSeek 官方 API，key 已注入环境）：
  codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox '<任务>'
codex 不可用/报错/超时 时，再用 OpenCode CLI 兜底：opencode run '<任务>' --model opencode/deepseek-v4-flash-free --auto
执行后用 git diff 验证改动，跑测试确认通过，报告真实输出。
"""

_CODING_KEYWORDS = [
    "implement", "write", "create", "add", "fix", "refactor",
    "modify", "update", "delete", "remove", "rename", "build",
    "编码", "写", "创建", "修改", "修复", "重构",
]


def _is_coding_task(goal: str) -> bool:
    g = goal.lower()
    return any(k in g for k in _CODING_KEYWORDS)


def _pre_tool_call_hook(tool_name: str, args: dict, **kwargs):
    if tool_name != "delegate_task":
        return None

    if "goal" in args and "tasks" not in args:
        entry = {"goal": args.pop("goal")}
        for k in ("context", "toolsets", "role"):
            if k in args:
                entry[k] = args.pop(k)
        args["tasks"] = [entry]

    for t in args.get("tasks", []):
        goal = t.get("goal", "")
        if _is_coding_task(goal):
            ctx = t.get("context", "")
            if "codex-injected" not in ctx:
                if ctx:
                    t["context"] = ctx.rstrip() + _CODEX_CONTEXT_INJECTION
                else:
                    t["context"] = f"任务目标：{goal}\n{_CODEX_CONTEXT_INJECTION}"
                logger.info("codex context injected for: %s", goal[:60])

    return None


# ── 入口 ──


def register(ctx):
    """Hermes 插件入口。"""
    ctx.register_tool(
        name="codex",
        toolset="codex",
        schema=CODEX_TOOL_SCHEMA,
        handler=_codex_handler,
        check_fn=lambda: bool(_find_codex() and _get_api_key()),
        requires_env=[],
        description="Codex 编码工具（备选执行体）— DeepSeek V4 Flash 官方 Responses API 适配",
        emoji="🐙",
    )
    ctx.register_hook("pre_session_init", _inject_session_guidance)
    ctx.register_hook("pre_tool_call", _pre_tool_call_hook)
    logger.info("codex-router loaded (tool + guidance + context injection)")
