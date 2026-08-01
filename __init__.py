"""
codex-router — Hermes → Codex CLI 集成插件。

codex 是 Hermes 唯一的编码执行体（opencode 已于 2026-08-01 弃用归档）。

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
import signal
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 配置（环境变量可覆盖，默认适配 Hermes 常见布局）──

_HERMES_ENV = Path(os.environ.get("HERMES_HOME", "")) if os.environ.get("HERMES_HOME") else None


def _home_dir() -> "Path | None":
    """Path.home() with graceful degradation (no HOME/USERPROFILE → None)."""
    try:
        return Path.home()
    except (RuntimeError, OSError):
        return None


_ENV_CANDIDATES = [
    p for p in [
        _HERMES_ENV / ".env" if _HERMES_ENV else None,
        Path(os.environ.get("HERMES_ENV_FILE", "")) if os.environ.get("HERMES_ENV_FILE") else None,
        _home_dir() / ".hermes" / ".env" if _home_dir() else None,
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
        "编码工具（首选执行体）——用 Codex CLI 执行编码任务，走 DeepSeek V4 Flash 官方 Responses API。"
        "日常编码优先用 codex；复杂/架构/审查用 pro。"
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
- 任何写新代码、新功能、重构、跨文件修改、修 bug 需要读多个文件的场景 → codex
- 写测试、跑测试验证 → codex
- 代码审查 → codex（model="pro"）

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


def _resolve_codex_js(codex_bin: str) -> str:
    """把 codex.cmd/.bat 解析为真正的 JS 入口（node_modules/@openai/codex/bin/codex.js）。

    Windows 上直接用 subprocess 跑 .cmd 会多一层 cmd.exe 壳：timeout 后
    kill() 只杀壳，node 子进程残留并持有 stdout 管道，communicate() 无限
    阻塞（实测 600s 超时拖到 851s 才返回）。绕过壳、node 直调 JS 入口后
    kill 可直达 node 进程。
    """
    if not (codex_bin.endswith(".cmd") or codex_bin.endswith(".bat")):
        return ""
    d = os.path.dirname(os.path.abspath(codex_bin))
    js = os.path.join(d, "..", "@openai", "codex", "bin", "codex.js")
    return os.path.abspath(js) if os.path.exists(js) else ""


def _build_codex_cmd(codex_bin: str, model: str, task: str) -> list:
    base = [
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model", model,
        task,
    ]
    js = _resolve_codex_js(codex_bin)
    node = shutil.which("node")
    if js and node:
        return [node, js] + base
    return [codex_bin] + base


def _kill_tree(proc: subprocess.Popen) -> None:
    """杀掉整个进程树，避免 communicate() 无超时阻塞。

    Windows: taskkill /T /F（树杀）；POSIX: killpg(SIGKILL)。
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, text=True, timeout=15,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


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
    timeout = float(os.environ.get("CODEX_TIMEOUT", "600"))

    cmd = _build_codex_cmd(codex_bin, model, task)
    env = os.environ.copy()
    env[_KEY_VAR] = api_key

    t0 = time.monotonic()
    out_fd, out_path = tempfile.mkstemp(prefix="codex-out-", suffix=".txt")
    err_fd, err_path = tempfile.mkstemp(prefix="codex-err-", suffix=".txt")
    try:
        try:
            # stdout/stderr 重定向到临时文件而非 PIPE：
            # codex 在 git 仓库内运行时会 spawn git 子进程，主进程退出后
            # git 残留仍持有管道句柄 → communicate() 等 EOF 会无限阻塞
            # （实测 18s 的任务被拖到 593s）。文件方案无 EOF 依赖，
            # 主进程退出即返回，残留进程无法阻塞回传。
            with open(out_fd, "wb", closefd=True) as outf, \
                 open(err_fd, "wb", closefd=True) as errf:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=outf,
                    stderr=errf,
                    cwd=directory,
                    env=env,
                )
                try:
                    proc.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # 超时：杀进程树（而非 subprocess.run 的 kill 壳+无限 communicate）
                    _kill_tree(proc)
                    try:
                        proc.communicate(timeout=20)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    with open(out_path, "rb") as f:
                        out_data = f.read().decode("utf-8", errors="replace")
                    with open(err_path, "rb") as f:
                        err_data = f.read().decode("utf-8", errors="replace")
                    return json.dumps({
                        "status": "timeout",
                        "error": f"执行超时（{int(timeout)} 秒），已强制终止进程树——任务可能未完成",
                        "elapsed_s": round(time.monotonic() - t0, 1),
                        "output": ((out_data or "") + "\n" + (err_data or "")).strip()[-2000:],
                    })
        except Exception as e:
            return json.dumps({"status": "error", "error": f"执行失败: {e}"})

        with open(out_path, "rb") as f:
            stdout = f.read().decode("utf-8", errors="replace")
        with open(err_path, "rb") as f:
            stderr = f.read().decode("utf-8", errors="replace")
    finally:
        for p in (out_path, err_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    output = (stdout or "") + ("\n" + stderr if stderr else "")
    text = output.strip()

    response = {
        "status": "ok" if proc.returncode == 0 else "error",
        "model": model,
        "elapsed_s": round(time.monotonic() - t0, 1),
        "output": text[-5000:],
    }
    if stderr:
        response["stderr"] = stderr[-1000:]

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


# ── pre_tool_call hook：编码类 delegate_task 注入 codex 指令 ──

_CODEX_CONTEXT_INJECTION = """

## 执行指令（自动注入）
编码任务用 Codex CLI（DeepSeek 官方 API，key 已注入环境）：
  codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox '<任务>'
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
    """Hermes 插件入口。

    Hermes 0.19: 引导规则（codex 首选）由 skill codex-primary-execution 承载
    （pre_session_init hook 已在 0.19 移除；skill 是官方跨项目引导机制）。
    """
    ctx.register_tool(
        name="codex",
        toolset="codex",
        schema=CODEX_TOOL_SCHEMA,
        handler=_codex_handler,
        check_fn=lambda: bool(_find_codex() and _get_api_key()),
        requires_env=[],
        description="Codex 编码工具（首选执行体）— DeepSeek V4 Flash 官方 Responses API 适配",
        emoji="🐙",
    )
    ctx.register_hook("pre_tool_call", _pre_tool_call_hook)
    logger.info("codex-router loaded (tool + context injection)")
