#!/usr/bin/env python3
"""`make corpus-live`: the synthetic Saudi/bilingual corpus through the real redactor, after `make up`. Owner only.

Two measurements per corpus item (platform/core/tests/corpus/saudi_bilingual_corpus.json, 225 values + 6 documents):
  sdp_only   the text straight to the platform redactor (Sensitive Data Protection with the qualified policy), each value
             on its own line: what the central redactor catches by itself, in its best case (line-anchored patterns).
  pipeline   the Financial Agent's real client path (deterministic email layer + platform client + redactor) on the
             prompt shape the agent sends (json.dumps(..., ensure_ascii=False), the value at the start of a pasted line).

Runs inside the Financial Agent's Pod (kubectl exec, its own redactor key, the image's own client code). The corpus goes
in on stdin; whether a value survived is decided inside the Pod, so **no value is ever printed or written**: the output is
item ids, categories and booleans only, written to docs/evidence/redaction-corpus-live-<date>.json.

Budget: the redactor allows 174 SDK operations per hour (2 per redaction). Items are packed one per line into batches of
at most MAX_BATCH_BYTES (the 4096-byte redaction limit, with room for the JSON prompt); each line starts with one space
(the redactor's line patterns allow up to three, and it keeps an email at a line start from touching the "n" of an
escaped newline). A leak is attributed by line. About 24 redactions in all; the tool refuses to start above MAX_CALLS.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parents[1] / 'core/tests/corpus/saudi_bilingual_corpus.json'
MAX_BATCH_BYTES = 3000  # the raw batch; its JSON prompt (escapes, wrapper) must stay under the 4096-byte limit
MAX_CALLS = 80          # redactions per run: under the redactor's 87 per hour (174 SDK operations, 2 per redaction)
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def normalized(text):
    """The same leak test as test_realistic_corpus.py: escapes decoded, marks/separators gone, digits as ASCII."""
    text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return re.sub(r'[\s\-–.()+   ‑＠@]', '', text).translate(DIGITS).lower()


def batches(corpus):
    """[{'mode', 'text', 'items': [[id, [values]]]}]: one item per line (" " + text), lines packed per batch; each
    document is its own batch (its lines are one item)."""
    packed = []
    # Covered and uncovered items never share a batch: a value masked in one line and present again in an uncovered
    # form in another makes the client fail closed for the whole batch (its residual check), which is right for a user
    # but would leave the batch unmeasured here.
    for covered in (True, False):
        current, size = [], 0
        for item in [i for i in corpus['items'] if i['covered'] is covered]:
            cost = len(item['text'].encode()) + 2
            if current and size + cost > MAX_BATCH_BYTES:
                packed.append(current)
                current, size = [], 0
            current.append((item['id'], ' ' + item['text'], item['values']))
            size += cost
        if current:
            packed.append(current)
    out = []
    for mode in ('sdp_only', 'pipeline'):
        for group in packed:
            out.append({'mode': mode, 'text': '\n'.join(text for _, text, _ in group), 'lines': True,
                        'items': [[unit_id, values] for unit_id, _, values in group]})
        for d in corpus['documents']:
            out.append({'mode': mode, 'text': d['text'], 'lines': False, 'items': [[d['id'], d['values']]]})  # gaps: not covered
    return out


# Runs in the agent Pod: the image's own client code, the agent's own redactor key. Prints ids, categories, booleans.
IN_POD = r'''
import json, re, sys, unicodedata, urllib.request
sys.path[:0] = ['/app/platform/src', '/app']
from agent_platform.redaction import RedactorClient
from runtime.phase3.deterministic_email import DeterministicEmailRedactor
URL = 'http://redactor.platform.svc.cluster.local:4003'
KEY = json.load(open('/secrets/agent/agent.json'))['redactor_key']
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
def normalized(text):
    text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return re.sub(r'[\s\-–.()+   ‑＠@]', '', text).translate(DIGITS).lower()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
out = []
for batch in json.load(sys.stdin):
    try:
        if batch['mode'] == 'sdp_only':
            request = urllib.request.Request(URL + '/redact', data=json.dumps({'text': batch['text']}).encode(), method='POST',
                                             headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
            reply = json.load(opener.open(request, timeout=30))
            text, categories = reply['text'], reply['categories']
        else:
            prompt = json.dumps({'question': 'Please check this:\n' + batch['text'], 'history': [], 'observations': []}, ensure_ascii=False)
            result = DeterministicEmailRedactor(RedactorClient(URL, KEY, timeout=30)).redact(prompt)
            text, categories = json.loads(result.text)['question'].split('\n', 1)[1], list(result.categories)
        lines = text.split('\n') if batch['lines'] else [text]
        if len(lines) != len(batch['items']):
            raise ValueError('lines')
        out.append({'mode': batch['mode'], 'categories': sorted(set(categories)),
                    'items': [[unit, any(normalized(v) in normalized(line) for v in values)]
                              for (unit, values), line in zip(batch['items'], lines)]})
    except Exception as error:
        out.append({'mode': batch['mode'], 'error': type(error).__name__, 'items': [[unit, None] for unit, _ in batch['items']]})
print(json.dumps(out))
'''


def summarize(corpus, results):
    """Per mode: covered items that leaked (must be none on the pipeline), uncovered items the redactor still masked."""
    covered = {i['id']: i['covered'] for i in corpus['items']}
    covered.update({d['id']: True for d in corpus['documents']})
    summary = {}
    for mode in ('sdp_only', 'pipeline'):
        rows = [(unit, leaked) for r in results if r['mode'] == mode for unit, leaked in r['items']]
        summary[mode] = {
            'redactions': sum(1 for r in results if r['mode'] == mode),
            'errors': sorted({r['error'] for r in results if r['mode'] == mode and 'error' in r}),
            'covered_leaked': sorted(u for u, leaked in rows if covered.get(u) and leaked),
            'covered_masked': sum(1 for u, leaked in rows if covered.get(u) and leaked is False),
            'uncovered_masked_by_redactor': sorted(u for u, leaked in rows if not covered.get(u) and leaked is False),
            'not_measured': sorted(u for u, leaked in rows if leaked is None),
            'categories_seen': sorted({c for r in results if r['mode'] == mode for c in r.get('categories', [])}),
        }
    return summary


def main(argv, *, exec_in_pod=None, today=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
    job = batches(corpus)
    if len(job) > MAX_CALLS:
        raise SystemExit('corpus-live: refused: %d redactions planned, more than %d' % (len(job), MAX_CALLS))
    if exec_in_pod is None:
        sys.path.insert(0, str(HERE))
        import lifecycle
        lifecycle.kubeconfig()

        def exec_in_pod(payload):
            result = lifecycle.kubectl('-n', 'agent-financial', 'exec', '-i', 'deploy/agent', '-c', 'agent', '--',
                                       '/usr/local/bin/python3.12', '-c', IN_POD, check=False, capture=True, input=payload)
            if result.returncode != 0:
                raise SystemExit('corpus-live: the agent Pod did not run the check (is the platform up?)')
            return result.stdout
    results = json.loads(exec_in_pod(json.dumps(job, ensure_ascii=False)))
    report = {'record': 'Synthetic Saudi/bilingual corpus through the live redactor (categories and booleans only; no values)',
              'date': (today or datetime.date.today()).isoformat(), 'corpus': str(CORPUS.relative_to(HERE.parents[2])),
              'redactions': len(job), 'summary': summarize(corpus, results), 'batches': results}
    out = Path(args.out or HERE.parents[2] / ('docs/evidence/redaction-corpus-live-%s.json' % report['date']))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'written': str(out), **{m: {k: (len(v) if isinstance(v, list) else v) for k, v in s.items()}
                                              for m, s in report['summary'].items()}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
