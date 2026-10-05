"""Offline full-campaign envelopes; constructed SDK data is not Google quality evidence."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

try:
    from google.cloud import dlp_v2
    from google.api_core.exceptions import DeadlineExceeded
except ImportError:
    dlp_v2 = DeadlineExceeded = None
from runtime.phase3.google_sdp_adapter import ENDPOINT

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("campaign_accounting", ROOT / "scripts/evaluate-sdp-context-policy.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SDKCampaignTransport:
    api_endpoint = ENDPOINT

    def __init__(self, *, fail_case=None, mismatch_case=None, change_safe_text=False):
        self.cases = {case["text"]: case for case in runner.load_corpus()["cases"]}
        self.fail_case, self.mismatch_case = fail_case, mismatch_case
        self.change_safe_text = change_safe_text
        self.events = []

    def inspect_content(self, *, request, retry, timeout):
        dlp_v2.InspectContentRequest(request)
        self.events.append(("inspect", retry, timeout))
        text = request["item"]["value"]
        case = self.cases[text]
        if case["case_id"] == self.fail_case:
            raise DeadlineExceeded("private transport marker")
        spans = [] if case["case_id"] == self.mismatch_case else case["expected_spans"]
        return dlp_v2.InspectContentResponse(result={"findings": [
            {"info_type": {"name": span["info_type"]}, "location": {
                "codepoint_range": {"start": span["start"], "end": span["end"]},
                "byte_range": {"start": len(text[:span["start"]].encode()),
                               "end": len(text[:span["end"]].encode())}}}
            for span in spans
        ]})

    def deidentify_content(self, *, request, retry, timeout):
        dlp_v2.DeidentifyContentRequest(request)
        self.events.append(("deidentify", retry, timeout))
        text = request["item"]["value"]
        case = self.cases[text]
        spans = [] if case["case_id"] == self.mismatch_case else case["expected_spans"]
        pieces, groups, cursor = [], {}, 0
        for span in spans:
            start, end, name = span["start"], span["end"], span["info_type"]
            pieces.extend((text[cursor:start], "[" + name + "]"))
            cursor = end
            count, size = groups.get(name, (0, 0))
            groups[name] = (count + 1, size + len(text[start:end].encode()))
        pieces.append(text[cursor:])
        return dlp_v2.DeidentifyContentResponse(
            item={"value": "".join(pieces) + (" changed" if self.change_safe_text else "")},
            overview={"transformed_bytes": sum(size for _, size in groups.values()),
                      "transformation_summaries": [
                          {"info_type": {"name": name}, "transformed_bytes": size,
                           "transformation": {"replace_with_info_type_config": {}},
                           "results": [{"count": count, "code": "SUCCESS"}]}
                          for name, (count, size) in groups.items()]})


@unittest.skipIf(dlp_v2 is None, "separate mandatory locked SDK gate")
class CampaignAccountingTests(unittest.TestCase):
    def test_complete_sdk_envelopes_exact_scoring_and_shared_172_budget(self):
        client = SDKCampaignTransport()
        result = runner.evaluate(client=client)
        self.assertEqual((result["required_pass"], result["required_fail"], result["observations"],
                          result["observation_failures"], result["operational_failures"],
                          result["injected_attempts"], result["sdk_attempts"], result["unexecuted"]),
                         (70, 0, 16, 0, 0, 172, 0, 0))
        self.assertEqual(len(client.events), 172)
        self.assertTrue(all(retry is None and 0 < timeout <= 3 for _, retry, timeout in client.events))
        self.assertEqual(result["google_quality"], "unmeasured")

    def test_unsupported_rpc_failure_is_operational_not_mandatory_acceptance(self):
        corpus = runner.load_corpus()["cases"]
        index = next(i for i, case in enumerate(corpus)
                     if case["classification"].startswith("unsupported_"))
        client = SDKCampaignTransport(fail_case=corpus[index]["case_id"])
        result = runner.evaluate(client=client)
        self.assertEqual(result["required_fail"], 0)
        self.assertEqual((result["observation_failures"], result["operational_failures"]), (1, 1))
        self.assertEqual(result["outcome"], "FAIL_CLOSED")
        self.assertEqual(result["injected_attempts"], 2 * index + 1)
        self.assertEqual(len(client.events), 2 * index + 1)
        self.assertEqual(result["cases"][-1]["diagnostic"], {"code": "RPC_TIMEOUT", "stage": "inspect",
                                                                       "rpc_status": "DEADLINE_EXCEEDED"})
        self.assertEqual(result["unexecuted"], 85 - index)

    def test_last_mandatory_failure_still_fails_with_zero_unexecuted(self):
        client = SDKCampaignTransport(fail_case="context-086")
        result = runner.evaluate(client=client)
        self.assertEqual((result["required_pass"], result["required_fail"], result["observations"],
                          result["observation_failures"], result["operational_failures"], result["unexecuted"]),
                         (69, 1, 16, 0, 1, 0))
        self.assertEqual(result["outcome"], "FAIL_CLOSED")
        self.assertEqual(result["injected_attempts"], 171)
        self.assertNotIn("private transport marker", json.dumps(result))

    def test_required_miss_and_safe_text_change_each_stop_without_retry(self):
        client = SDKCampaignTransport(mismatch_case="context-001")
        result = runner.evaluate(client=client)
        self.assertEqual((result["required_fail"], result["operational_failures"]), (1, 0))
        self.assertEqual(result["cases"][0]["fn"], 1)
        self.assertEqual(len(client.events), 2)
        client = SDKCampaignTransport(change_safe_text=True)
        result = runner.evaluate(client=client)
        self.assertEqual((result["required_fail"], result["operational_failures"]), (1, 1))
        self.assertEqual(result["cases"][0]["diagnostic"]["code"], "OUTPUT_MISMATCH")
        self.assertEqual(len(client.events), 2)

    def test_deadline_has_bounded_diagnostic_without_fabricated_acceptance_failure(self):
        clock = iter([0, 900])
        result = runner.evaluate(clock=lambda: next(clock))
        self.assertEqual((result["required_fail"], result["operational_failures"], result["sdk_attempts"]), (0, 1, 0))
        self.assertEqual(result["cases"], [])
        self.assertEqual(result["campaign_diagnostic"], {"code": "OVERALL_TIMEOUT", "stage": "sequence"})
        self.assertEqual(result["unexecuted"], 86)

    def test_result_rejects_wrong_accounting_order_scope_and_unsanitized_fields(self):
        valid = runner.evaluate()
        changes = [("required_pass", 69), ("required_fail", 1), ("observations", 15),
                   ("sdk_attempts", 1), ("injected_attempts", 173), ("unexecuted", 1),
                   ("operational_failures", 1), ("observation_failures", 1),
                   ("outcome", "FAIL_CLOSED"), ("google_quality", "synthetic_policy_observations_only")]
        for key, value in changes:
            invalid = deepcopy(valid)
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(Exception):
                runner.validate_result(invalid)
        for mutation in ("order", "observation_pass", "placeholder", "raw"):
            invalid = deepcopy(valid)
            if mutation == "order":
                invalid["cases"][1]["case_id"] = "context-001"
            elif mutation == "observation_pass":
                next(c for c in invalid["cases"] if c["status"] == "OBSERVATION")["status"] = "PASS"
            elif mutation == "placeholder":
                invalid["cases"][0]["fn"] = 1
            else:
                invalid["raw_text"] = "private fixture marker"
            with self.subTest(mutation=mutation), self.assertRaises(Exception):
                runner.validate_result(invalid)
