"""RedactorClient: the only way text reaches a model. Cloud-agnostic HTTP contract with the platform redactor.

Contract: POST {base}/redact {"text"} with a per-namespace bearer key -> {"text", "categories"}.
Any failure (network, status, shape, unsupported category, size) raises ControlFailure, so the caller never
sends a model request with unredacted text. It plugs into the existing agent core as its redactor.
"""
import json
import urllib.error
import urllib.request

from runtime.agents.composition import BoundaryBudget
from runtime.phase3.trusted_runtime import ControlFailure, RedactionResult, SUPPORTED_ENTITIES

SUPPORTED_CATEGORIES = frozenset(SUPPORTED_ENTITIES)  # the runtime's canonical set (same check as the C trial client)


class RedactorClient:
    offline_simulation = False

    def __init__(self, base_url, key, *, timeout=8, budget=None, opener=None, supported=SUPPORTED_CATEGORIES):
        if not base_url.startswith('http://') or len(key) != 64:
            raise ValueError('redaction:invalid_client')
        self._url, self._key, self._timeout = base_url.rstrip('/') + '/redact', key, timeout
        self.budget = budget or BoundaryBudget()
        self._open = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        self._supported = supported

    def redact(self, value):
        self.budget.reserve(value)
        try:
            request = urllib.request.Request(self._url, data=json.dumps({'text': value}).encode(), method='POST',
                                             headers={'Authorization': 'Bearer ' + self._key,
                                                      'Content-Type': 'application/json'})
            with self._open(request, timeout=self._timeout) as response:
                if response.status != 200:
                    raise ValueError('status')
                result = json.loads(response.read(16385))
            if (type(result) is not dict or set(result) != {'text', 'categories'} or type(result['text']) is not str
                    or type(result['categories']) is not list or not all(type(c) is str for c in result['categories'])
                    or not set(result['categories']) <= self._supported
                    or result['categories'] != sorted(set(result['categories']))):
                raise ValueError('shape')
            self.budget.accept_output(result['text'])
            return RedactionResult(result['text'], tuple(result['categories']))
        except ControlFailure:
            raise
        except (urllib.error.URLError, OSError, ValueError):
            raise ControlFailure('redaction', 'unavailable') from None
