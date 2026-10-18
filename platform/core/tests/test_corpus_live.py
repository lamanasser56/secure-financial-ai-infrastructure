"""`make corpus-live` offline: the in-Pod program runs here against an echo redactor; nothing is sent anywhere.

The echo redactor masks nothing (the worst case), so with the client pipeline every covered value must still be masked
(the platform client does it), and with the redactor alone every value survives. The report holds ids, categories and
booleans only: no corpus value may appear in it.
"""
import builtins
import contextlib
import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.request

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'platform/clouds/gke'))
import corpus_live  # noqa: E402

CORPUS = json.loads(corpus_live.CORPUS.read_text(encoding='utf-8'))


class Echo:
    status = 200

    def __init__(self, request):
        self.body = json.dumps({'text': json.loads(request.data)['text'], 'categories': []}).encode()

    def read(self, limit=None):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    calls = 0

    def open(self, request, timeout=None):
        FakeOpener.calls += 1
        return Echo(request)


def run_in_pod_here(payload):
    """Execute corpus_live.IN_POD in this process: the agent's key file and the redactor are faked."""
    real_open = builtins.open
    fake_key = io.StringIO(json.dumps({'redactor_key': 'k' * 64}))
    opened = lambda path, *a, **k: fake_key if path == '/secrets/agent/agent.json' else real_open(path, *a, **k)  # noqa: E731
    out = io.StringIO()
    with mock.patch('builtins.open', opened), mock.patch.object(urllib.request, 'build_opener', lambda *a: FakeOpener()), \
            mock.patch('sys.stdin', io.StringIO(payload)), contextlib.redirect_stdout(out):
        exec(compile(corpus_live.IN_POD, 'in_pod', 'exec'), {'__name__': '__main__'})
    return out.getvalue()


class CorpusLive(unittest.TestCase):
    def test_the_plan_fits_the_redactor_budget_and_the_size_limit(self):
        job = corpus_live.batches(CORPUS)
        self.assertLessEqual(len(job), corpus_live.MAX_CALLS)
        for batch in job:
            prompt = json.dumps({'question': 'Please check this:\n' + batch['text'], 'history': [], 'observations': []}, ensure_ascii=False)
            self.assertLessEqual(len(prompt.encode()), 4096)
        items = [unit for b in job if b['mode'] == 'pipeline' for unit, _ in b['items']]
        self.assertEqual(sorted(items), sorted([i['id'] for i in CORPUS['items']] + [d['id'] for d in CORPUS['documents']]))

    def test_offline_run_with_an_echo_redactor(self):
        FakeOpener.calls = 0
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report.json'
            with contextlib.redirect_stdout(io.StringIO()):
                corpus_live.main(['--out', str(out)], exec_in_pod=run_in_pod_here, today=datetime.date(2026, 10, 19))
            text = out.read_text(encoding='utf-8')
        report = json.loads(text)
        self.assertEqual(FakeOpener.calls, report['redactions'])
        pipeline, sdp = report['summary']['pipeline'], report['summary']['sdp_only']
        self.assertEqual((pipeline['errors'], pipeline['not_measured'], pipeline['covered_leaked']), ([], [], []))
        self.assertEqual(pipeline['covered_masked'], sum(i['covered'] for i in CORPUS['items']) + len(CORPUS['documents']))
        self.assertGreater(len(sdp['covered_leaked']), 150)  # an echo "redactor" masks nothing by itself
        for value in [v for i in CORPUS['items'] for v in i['values']] + [v for d in CORPUS['documents'] for v in d['values']]:
            self.assertNotIn(value, text)


if __name__ == '__main__':
    unittest.main()
