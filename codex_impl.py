"""codex-router 实现层（可热重载）。

__init__.py 只保留注册骨架；本文件承载全部运行逻辑。
改动本文件后**下一次工具调用自动生效，无需重启 Hermes**
（__init__.py 的薄壳按 mtime 检测并重新加载本模块）。

唯一例外：修改 CODEX_TOOL_SCHEMA / hook 注册结构仍需重启（低频）。

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

# 递增以验证热重载生效
IMPL_VERSION = 3

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


# ── key 获取：优先环境变量，其次 Hermes .env ──


def get_api_key() -> str:
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


def find_codex() -> str:
    for c in _CODEX_CANDIDATES:
        if c == "codex":
            found = shutil.which("codex")
            if found:
                return found
        elif Path(c).exists():
            return c
    return ""


# ── 工具 handler 逻辑 ──


def resolve_codex_js(codex_bin: str) -> str:
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


def build_codex_cmd(codex_bin: str, model: str, task: str) -> list:
    base = [
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model", model,
        task,
    ]
    js = resolve_codex_js(codex_bin)
    node = shutil.which("node")
    if js and node:
        return [node, js] + base
    return [codex_bin] + base


def kill_tree(proc: subprocess.Popen) -> None:
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


def run(args: dict, kwargs: dict | None = None) -> str:
    task = (args.get("task") or "").strip()
    if not task:
        return json.dumps({"error": "task is required"})

    model_choice = (args.get("model") or "flash").strip()
    directory = (args.get("directory") or "").strip() or os.getcwd()
    verify = args.get("verify", True)

    codex_bin = find_codex()
    if not codex_bin:
        return json.dumps({"error": "codex CLI 未找到：set CODEX_BIN or add codex to PATH"})

    api_key = get_api_key()
    if not api_key:
        return json.dumps({"error": f"缺少 {_KEY_VAR}（环境变量或 Hermes .env）"})

    model = _PRO_MODEL if model_choice == "pro" else _DEFAULT_MODEL
    timeout = float(os.environ.get("CODEX_TIMEOUT", "600"))

    cmd = build_codex_cmd(codex_bin, model, task)
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
                    kill_tree(proc)
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


def is_coding_task(goal: str) -> bool:
    g = goal.lower()
    return any(k in g for k in _CODING_KEYWORDS)


def pre_tool_call(tool_name: str, args: dict, kwargs: dict | None = None):
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
        if is_coding_task(goal):
            ctx = t.get("context", "")
            if "codex-injected" not in ctx:
                if ctx:
                    t["context"] = ctx.rstrip() + _CODEX_CONTEXT_INJECTION
                else:
                    t["context"] = f"任务目标：{goal}\n{_CODEX_CONTEXT_INJECTION}"
                logger.info("codex context injected for: %s", goal[:60])

    return None
