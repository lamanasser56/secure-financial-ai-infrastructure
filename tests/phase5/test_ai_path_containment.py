"""Guard the standalone runtime against a direct provider adapter."""

import ast
from pathlib import Path
import unittest

from runtime.phase3.adapters import (
    DEFAULT_ANALYZER_URL,
    DEFAULT_ANONYMIZER_URL,
)
from runtime.phase3.mocks import build_mock_runtime
from runtime.phase3.trusted_runtime import ControlFailure


ROOT = Path(__file__).resolve().parents[2]


class AIPathContainmentTests(unittest.TestCase):
    def test_default_presidio_adapters_are_internal_services(self):
        for url in (DEFAULT_ANALYZER_URL, DEFAULT_ANONYMIZER_URL):
            self.assertTrue(url.startswith("http://"))
            self.assertIn(".ai-platform.svc.cluster.local:", url)

    def test_runtime_contains_no_provider_client(self):
        source = "\n".join(p.read_text() for p in (ROOT / "runtime").rglob("*.py"))
        for prohibited in ("api.openai.com", "generativelanguage.googleapis.com", "google.generativeai", "vertexai.init("):
            self.assertNotIn(prohibited, source)

    def test_presidio_is_the_only_concrete_redactor(self):
        adapter_source = (ROOT / "runtime/phase3/adapters.py").read_text()
        classes = [
            node.name for node in ast.walk(ast.parse(adapter_source))
            if isinstance(node, ast.ClassDef)
            and any(isinstance(member, ast.FunctionDef) and member.name == "redact"
                    for member in node.body)
        ]
        self.assertEqual(classes, ["PresidioRedactor"])
        runtime_source = "\n".join(p.read_text() for p in (ROOT / "runtime").rglob("*.py"))
        for prohibited in ("google.cloud.dlp", "google_cloud_dlp", "dlp_v2", "GoogleSDPRedactor"):
            self.assertNotIn(prohibited, runtime_source)

    def test_authorization_denial_never_reaches_gateway(self):
        runtime, recorder = build_mock_runtime({"authorization": "deny"})
        with self.assertRaises(ControlFailure):
            runtime.execute("Bearer qualification-token", {
                "action": "chat.complete",
                "input": {"message": "synthetic", "response_format": "json"},
            }, "path-containment-0001")
        self.assertEqual((recorder.litellm_calls, recorder.provider_calls), (0, 0))


if __name__ == "__main__":
    unittest.main()
