"""Smoke tests for hermes-codex-router plugin.

Runs without a real Codex CLI or API key — verifies graceful degradation
and schema stability, which is all CI can do without secrets.
Also verifies the hot-reload mechanism (codex_impl.py mtime detection).
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

PLUGIN = os.path.join(os.path.dirname(__file__), "..", "__init__.py")


def load_plugin(path=None):
    spec = importlib.util.spec_from_file_location("codex_router", path or PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CodexRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Isolate from the real environment: no key, no binary.
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("CODEX_BIN", None)
        os.environ.pop("HERMES_HOME", None)
        os.environ.pop("HERMES_ENV_FILE", None)
        cls.mod = load_plugin()

    def setUp(self):
        # Patch the hot-reloaded impl module (not the skeleton), and restore after.
        impl = self.mod._load_impl()
        self._impl = impl
        self._orig_find = impl.find_codex
        self._orig_key = impl.get_api_key

    def tearDown(self):
        self._impl.find_codex = self._orig_find
        self._impl.get_api_key = self._orig_key

    def test_tool_schema_stable(self):
        schema = self.mod.CODEX_TOOL_SCHEMA
        self.assertEqual(schema["name"], "codex")
        self.assertIn("task", schema["parameters"]["required"])
        self.assertIn("model", schema["parameters"]["properties"])
        self.assertIn(
            "flash",
            schema["parameters"]["properties"]["model"]["enum"],
        )
        self.assertIn("pro", schema["parameters"]["properties"]["model"]["enum"])

    def test_missing_key_returns_error(self):
        # bin present, key absent → key error
        self._impl.find_codex = lambda: "codex"
        self._impl.get_api_key = lambda: ""
        result = json.loads(self.mod._codex_handler({"task": "do something"}))
        self.assertIn("error", result)
        self.assertIn("DEEPSEEK_API_KEY", result["error"])

    def test_missing_bin_returns_error(self):
        # key present, bin absent → bin error
        self._impl.find_codex = lambda: ""
        self._impl.get_api_key = lambda: "sk-test"
        result = json.loads(self.mod._codex_handler({"task": "do something"}))
        self.assertIn("error", result)
        self.assertIn("codex CLI", result["error"])

    def test_error_message_is_actionable(self):
        # bin absent → error must include the CODEX_BIN fix hint
        self._impl.find_codex = lambda: ""
        self._impl.get_api_key = lambda: "sk-test"
        result = json.loads(self.mod._codex_handler({"task": "do something"}))
        self.assertIn("error", result)
        self.assertIn("CODEX_BIN", result["error"])

    def test_missing_task_returns_error(self):
        result = json.loads(self.mod._codex_handler({}))
        self.assertEqual(result["error"], "task is required")

    def test_coding_task_detection(self):
        impl = self._impl
        self.assertTrue(impl.is_coding_task("Implement the auth module"))
        self.assertTrue(impl.is_coding_task("修复登录 bug"))
        self.assertFalse(impl.is_coding_task("Translate this to French"))

    def test_delegate_injection(self):
        args = {"tasks": [{"goal": "Refactor the config parser"}]}
        self.mod._pre_tool_call_hook("delegate_task", args)
        ctx = args["tasks"][0]["context"]
        self.assertIn("Codex CLI", ctx)
        # Second pass must not double-inject
        self.mod._pre_tool_call_hook("delegate_task", args)
        self.assertEqual(ctx.count("Codex CLI"), 1)

    def test_non_delegate_tool_untouched(self):
        args = {"goal": "whatever"}
        self.mod._pre_tool_call_hook("read_file", args)
        self.assertEqual(args["goal"], "whatever")

    def test_hot_reload_impl(self):
        """改 codex_impl.py 后 _load_impl() 必须返回新版本（免重启核心机制）。"""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = os.path.dirname(PLUGIN)
            shutil.copy(os.path.join(repo_root, "__init__.py"), tmp)
            impl_path = os.path.join(tmp, "codex_impl.py")
            shutil.copy(os.path.join(repo_root, "codex_impl.py"), impl_path)

            mod = load_plugin(os.path.join(tmp, "__init__.py"))
            v1 = mod._load_impl().IMPL_VERSION

            # 修改 impl 文件（追加版本号变更），mtime 变化应触发重载
            with open(impl_path, "a", encoding="utf-8") as f:
                f.write(f"\nIMPL_VERSION = {v1 + 1}  # hot-reload test\n")

            v2 = mod._load_impl().IMPL_VERSION
            self.assertEqual(v2, v1 + 1, "hot reload did not pick up impl change")

            # 未改动时命中缓存
            v3 = mod._load_impl().IMPL_VERSION
            self.assertEqual(v3, v2)


if __name__ == "__main__":
    unittest.main()
