"""Smoke tests for hermes-codex-router plugin.

Runs without a real Codex CLI or API key — verifies graceful degradation
and schema stability, which is all CI can do without secrets.
"""

import importlib.util
import json
import os
import sys
import unittest

PLUGIN = os.path.join(os.path.dirname(__file__), "..", "__init__.py")


def load_plugin():
    spec = importlib.util.spec_from_file_location("codex_router", PLUGIN)
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
        mod = self.mod
        mod._ENV_CANDIDATES = []
        orig_find, orig_key = mod._find_codex, mod._get_api_key
        mod._find_codex = lambda: "codex"
        mod._get_api_key = lambda: ""
        try:
            result = json.loads(mod._codex_handler({"task": "do something"}))
            self.assertIn("error", result)
            self.assertIn("DEEPSEEK_API_KEY", result["error"])
        finally:
            mod._find_codex, mod._get_api_key = orig_find, orig_key

    def test_missing_bin_returns_error(self):
        # key present, bin absent → bin error
        mod = self.mod
        orig_find, orig_key = mod._find_codex, mod._get_api_key
        mod._find_codex = lambda: ""
        mod._get_api_key = lambda: "sk-test"
        try:
            result = json.loads(mod._codex_handler({"task": "do something"}))
            self.assertIn("error", result)
            self.assertIn("codex CLI", result["error"])
        finally:
            mod._find_codex, mod._get_api_key = orig_find, orig_key

    def test_error_message_is_actionable(self):
        # bin absent → error must include the CODEX_BIN fix hint
        mod = self.mod
        orig_find, orig_key = mod._find_codex, mod._get_api_key
        mod._find_codex = lambda: ""
        mod._get_api_key = lambda: "sk-test"
        try:
            result = json.loads(mod._codex_handler({"task": "do something"}))
            self.assertIn("error", result)
            self.assertIn("CODEX_BIN", result["error"])
        finally:
            mod._find_codex, mod._get_api_key = orig_find, orig_key

    def test_missing_task_returns_error(self):
        result = json.loads(self.mod._codex_handler({}))
        self.assertEqual(result["error"], "task is required")

    def test_coding_task_detection(self):
        self.assertTrue(self.mod._is_coding_task("Implement the auth module"))
        self.assertTrue(self.mod._is_coding_task("修复登录 bug"))
        self.assertFalse(self.mod._is_coding_task("Translate this to French"))

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

    def test_delegate_injection_mentions_self_decomposition(self):
        # 拆解分工约束（2026-08-02）必须随 delegate 注入生效
        self.assertIn("自行拆解", self.mod._CODEX_CONTEXT_INJECTION)
        self.assertIn("先列执行计划", self.mod._CODEX_CONTEXT_INJECTION)

    def test_check_directory_ok(self):
        self.assertEqual(self.mod._check_directory(os.getcwd()), "")

    def test_check_directory_blocks_system(self):
        err = self.mod._check_directory("C:/Windows")
        self.assertIn("拒绝", err)
        self.assertIn("Windows", err)

    def test_check_directory_missing(self):
        err = self.mod._check_directory("C:/definitely/not/a/real/dir")
        self.assertIn("不存在", err)

    def test_handler_rejects_system_directory(self):
        # handler 层：目录校验失败 → 错误 JSON，不 spawn codex
        result = json.loads(self.mod._codex_handler({"task": "x", "directory": "C:/Windows"}))
        self.assertIn("error", result)
        self.assertIn("拒绝", result["error"])


if __name__ == "__main__":
    unittest.main()
