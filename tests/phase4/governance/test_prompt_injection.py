import unittest

from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.prompt_injection import assess_prompt_injection
from _mocks import GovernanceRecorder, MockPromptInjectionAssessor


class PromptInjectionTests(unittest.TestCase):
    def setUp(self):
        self.arguments = {"as_of_date": "2026-08-01"}

    def test_clear_assessment_passes(self):
        result = assess_prompt_injection(
            MockPromptInjectionAssessor(GovernanceRecorder(), "clear"),
            self.arguments,
        )
        self.assertEqual(result.outcome.value, "clear")

    def test_suspected_hard_blocks(self):
        self._failure("suspected", "suspected_injection")

    def test_malformed_blocks(self):
        self._failure("malformed", "malformed_assessment")

    def test_unsupported_category_blocks(self):
        self._failure("unsupported", "unsupported_indicator_category")

    def test_timeout_blocks(self):
        self._failure("timeout", "timeout")

    def test_unavailable_blocks_without_raw_text(self):
        assessor = MockPromptInjectionAssessor(
            GovernanceRecorder(), "unavailable"
        )
        with self.assertRaises(ControlFailure) as ctx:
            assess_prompt_injection(assessor, self.arguments)
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("prompt_injection_assessment", "unavailable"),
        )
        self.assertNotIn("sensitive-detail", str(ctx.exception))

    def _failure(self, mode, category):
        with self.assertRaises(ControlFailure) as ctx:
            assess_prompt_injection(
                MockPromptInjectionAssessor(GovernanceRecorder(), mode),
                self.arguments,
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("prompt_injection_assessment", category),
        )


if __name__ == "__main__":
    unittest.main()
