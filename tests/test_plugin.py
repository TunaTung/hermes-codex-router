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
        # Force no key available in any candidate
        self.mod._ENV_CANDIDATES = []
        result = json.loads(self.mod._codex_handler({"task": "do something"}))
        self.assertEqual(result["status"], "error")
        self.assertIn("DEEPSEEK_API_KEY", result["error"])

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


if __name__ == "__main__":
    unittest.main()
