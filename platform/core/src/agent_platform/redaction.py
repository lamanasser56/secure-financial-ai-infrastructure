"""RedactorClient: the only way text reaches a model. Cloud-agnostic HTTP contract with the platform redactor.

Contract: POST {base}/redact {"text"} with a per-namespace bearer key -> {"text", "categories"}.
Any failure (network, status, shape, unsupported category, size) raises ControlFailure, so the caller never
sends a model request with unredacted text. It plugs into the existing agent core as its redactor.

Before sending, structured identifiers (phone, IBAN, VAT, card, labelled IDs and bank accounts) are masked locally
(agent_platform.identifiers): the redactor's policy anchors those patterns to the start of a line, which never happens
inside the JSON string an agent redacts per model call. The redactor never sees the original values, and an answer that
still contains one is refused like any other failure.
"""
import json
import threading
import time
import urllib.error
import urllib.request

from agent_platform import request_context
from agent_platform.identifiers import identifier_spans, mask
from runtime.agents.composition import BoundaryBudget
from runtime.phase3.trusted_runtime import ControlFailure, RedactionResult, SUPPORTED_ENTITIES

SUPPORTED_CATEGORIES = frozenset(SUPPORTED_ENTITIES)  # the runtime's canonical set (same check as the C trial client)
WINDOW_SECONDS = 900  # the core BoundaryBudget's maximum lifetime


class WindowedBoundaryBudget(BoundaryBudget):
    """The core redaction budget (operations and bytes) per 15-minute window, renewed for a long-lived session.

    A single BoundaryBudget may live at most 900 s, while an app session lasts an hour; without renewal every
    redaction after 15 minutes fails. Each window gets a fresh core budget with the same limits.
    """

    def __init__(self, *, clock=time.monotonic, **limits):
        self._limits, self._clock_fn = limits, clock
        self._window_lock = threading.Lock()
        self._window = None
        self._roll()

    def _roll(self):
        with self._window_lock:
            if self._window is None or self._clock_fn() >= self._window_end:
                self._window = BoundaryBudget(lifetime=WINDOW_SECONDS, clock=self._clock_fn, **self._limits)
                self._window_end = self._clock_fn() + WINDOW_SECONDS
            return self._window

    @property
    def operations(self):
        return self._roll().operations

    def reserve(self, value):
        self._roll().reserve(value)

    def accept_output(self, value):
        self._roll().accept_output(value)


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
        try:
            self.budget.reserve(value)
        except ControlFailure:  # budget exhausted: a runtime redaction stage, so the trace says unavailable
            raise ControlFailure('presidio_anonymizer', 'unavailable') from None
        try:
            spans = identifier_spans(value)  # raises ValueError on a non-str or oversized value: unavailable
            masked = mask(value, spans)
            headers = {'Authorization': 'Bearer ' + self._key, 'Content-Type': 'application/json'}
            if request_context.current():  # the redactor's audit line carries the same request ID
                headers[request_context.HEADER] = request_context.current()
            request = urllib.request.Request(self._url, data=json.dumps({'text': masked}).encode(), method='POST',
                                             headers=headers)
            with self._open(request, timeout=self._timeout) as response:
                if response.status != 200:
                    raise ValueError('status')
                result = json.loads(response.read(16385))
            if (type(result) is not dict or set(result) != {'text', 'categories'} or type(result['text']) is not str
                    or type(result['categories']) is not list or not all(type(c) is str for c in result['categories'])
                    or not set(result['categories']) <= self._supported
                    or result['categories'] != sorted(set(result['categories']))):
                raise ValueError('shape')
            if any(value[start:end] in result['text'] for start, end, _ in spans):
                raise ValueError('residual')  # fail closed: a masked value came back
            self.budget.accept_output(result['text'])
            categories = sorted(set(result['categories']) | {category for _, _, category in spans})
            return RedactionResult(result['text'], tuple(categories))
        except ControlFailure:  # output budget: same runtime stage as every other redaction failure
            raise ControlFailure('presidio_anonymizer', 'unavailable') from None
        except (urllib.error.URLError, OSError, ValueError):
            raise ControlFailure('presidio_anonymizer', 'unavailable') from None  # a runtime REDACTION_STAGES name
