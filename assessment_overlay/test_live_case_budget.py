"""The twelve approved live cases keep their original per-case allocations."""
import unittest

from live_case_guard import CASES, CASE_LIMITS, PLANNED_LIMITS, SETUP_LIMITS, case_delta


class LiveCaseBudgetTest(unittest.TestCase):
    def test_only_original_twelve_cases_are_allocated(self):
        self.assertEqual(set(CASE_LIMITS), CASES)
        self.assertEqual(len(CASES), 12)
        self.assertEqual(CASE_LIMITS['D02'], (4, 10))
        self.assertEqual(CASE_LIMITS['R01'], (2, 5))
        self.assertTrue(all(limits == (0, 0) for case, limits in CASE_LIMITS.items()
                            if case not in ('D02', 'R01')))

    def test_setup_plus_cases_fits_planned_and_hard_limits(self):
        total = tuple(SETUP_LIMITS[i] + sum(limits[i] for limits in CASE_LIMITS.values()) for i in (0, 1))
        self.assertEqual(total, PLANNED_LIMITS)
        self.assertLessEqual(total[0], 20)
        self.assertLessEqual(total[1], 60)

    def test_zero_allocation_case_rejects_any_redaction_or_sdk_call(self):
        before = {'completed_redactions': 2, 'sdk_attempts': 4}
        self.assertEqual(case_delta('K01', before, before), (0, 0))
        with self.assertRaisesRegex(RuntimeError, 'case allocation exceeded'):
            case_delta('K01', before, {'completed_redactions': 2, 'sdk_attempts': 5})

    def test_d02_caps_each_counter_and_rejects_decreases(self):
        before = {'completed_redactions': 2, 'sdk_attempts': 4}
        self.assertEqual(case_delta('D02', before, {'completed_redactions': 6, 'sdk_attempts': 14}), (4, 10))
        with self.assertRaisesRegex(RuntimeError, 'case allocation exceeded'):
            case_delta('D02', before, {'completed_redactions': 7, 'sdk_attempts': 14})
        with self.assertRaisesRegex(RuntimeError, 'durable counter decreased'):
            case_delta('D02', before, {'completed_redactions': 1, 'sdk_attempts': 4})


if __name__ == '__main__':
    unittest.main()
