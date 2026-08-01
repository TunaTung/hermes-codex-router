"""codex-router — Hermes → Codex CLI 集成插件（注册骨架）。

实现逻辑全部在 codex_impl.py——**改实现文件无需重启 Hermes**，
下一次工具调用按 mtime 检测自动热重载生效。
只有注册结构（CODEX_TOOL_SCHEMA / hook 注册 / 本文件）改动才需重启。

codex 是 Hermes 唯一的编码执行体（opencode 已于 2026-08-01 弃用归档）。
"""

from __future__ import annotations
import importlib.util
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# ── 实现层热重载 ──

_IMPL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex_impl.py")
_IMPL_NAME = __name__ + "_impl"  # hermes_plugins.codex_router_impl

_impl_state = {"mtime": -1.0, "module": None}


def _load_impl():
    """按 mtime 检测并加载 codex_impl.py；文件变化时重新 exec。

    每次工具调用都会走这里：mtime 未变 → 返回缓存模块（微秒级开销）；
    变了 → 重新加载，新逻辑立即生效，无需重启 Hermes。
    """
    try:
        mtime = os.path.getmtime(_IMPL_FILE)
    except OSError:
        return _impl_state["module"]
    if _impl_state["module"] is not None and _impl_state["mtime"] == mtime:
        return _impl_state["module"]
    spec = importlib.util.spec_from_file_location(_IMPL_NAME, _IMPL_FILE)
    if spec is None or spec.loader is None:
        logger.error("codex_impl spec failed for %s", _IMPL_FILE)
        return _impl_state["module"]
    module = importlib.util.module_from_spec(spec)
    sys.modules[_IMPL_NAME] = module
    spec.loader.exec_module(module)
    _impl_state["mtime"] = mtime
    _impl_state["module"] = module
    logger.info("codex-impl hot-loaded (mtime=%s, version=%s)", mtime, getattr(module, "IMPL_VERSION", "?"))
    return module


# ── 工具 schema（注册时用；改动需重启）──

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


# ── 薄壳：handler / hook / check_fn 全部转发到热重载实现 ──


def _codex_handler(args: dict, **kwargs) -> str:
    impl = _load_impl()
    if impl is None:
        return json.dumps({"error": "codex_impl.py 加载失败，请检查插件目录"})
    return impl.run(args, kwargs)


def _pre_tool_call_hook(tool_name: str, args: dict, **kwargs):
    impl = _load_impl()
    if impl is None:
        return None
    return impl.pre_tool_call(tool_name, args, kwargs)


def _check_available() -> bool:
    impl = _load_impl()
    return bool(impl and impl.find_codex() and impl.get_api_key())


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
        check_fn=_check_available,
        requires_env=[],
        description="Codex 编码工具（首选执行体）— DeepSeek V4 Flash 官方 Responses API 适配",
        emoji="🐙",
    )
    ctx.register_hook("pre_tool_call", _pre_tool_call_hook)
    logger.info("codex-router loaded (tool + context injection, hot-reload impl)")
