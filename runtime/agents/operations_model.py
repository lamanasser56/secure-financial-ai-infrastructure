"""Scoped local LiteLLM explanation only; never grants operational authority."""
import json
import uuid
from urllib.parse import urlsplit

from runtime.agents.composition import BoundaryBudget, SharedSimulatedRedactor
from runtime.agents.credentials import ScopedCredential
from runtime.agents.gateway_budget import BudgetedGateway, RunAttemptBudget
from runtime.agents.protocol_preparation import completion_content
from runtime.phase3.adapters import HttpLiteLLMGateway, _post_json
from runtime.phase3.trusted_runtime import APPROVED_MODEL_ALIAS, ControlFailure, GatewayResult, redact_checked


class ExplanationGateway(HttpLiteLLMGateway):
    def complete(self, alias, prompt, metadata):
        if alias != APPROVED_MODEL_ALIAS or len(prompt.encode()) > 4096:
            raise ControlFailure('litellm', 'invalid_configuration')
        self.call_count += 1
        response = _post_json(self._url, {'model': alias, 'stream': False,
            'messages': [{'role': 'system', 'content': 'Explain observed local operational evidence, suspected causes and unknowns. Never grant approval, invent evidence, or provide executable commands. Return JSON with summary (text) and classification (informational).'},
                         {'role': 'user', 'content': prompt}],
            'response_format': {'type': 'json_object'}, 'max_tokens': 256, 'temperature': 0,
            'metadata': metadata}, self._timeout, headers={'Authorization': self._authorization})
        self.http_responses += 1
        usage = response.get('usage') if type(response) is dict else None
        if (type(usage) is dict and all(type(usage.get(k)) is int and 0 <= usage[k] <= 2000000 for k in self.usage_totals)
                and usage['prompt_tokens'] + usage['completion_tokens'] == usage['total_tokens']):
            for key in self.usage_totals:
                self.usage_totals[key] += usage[key]
        else:
            self.usage_unavailable += 1
        content = completion_content(response)
        if len(content.encode()) > 4096:
            raise ControlFailure('structured_output_validation', 'output_schema_mismatch')
        result = json.loads(content)
        if (set(result) != {'summary', 'classification'} or result['classification'] != 'informational'
                or type(result['summary']) is not str or not 0 < len(result['summary'].encode()) <= 2048):
            raise ControlFailure('structured_output_validation', 'output_schema_mismatch')
        return GatewayResult(result, False, 'offline_simulation')


class OperationsExplainer:
    def __init__(self, config, *, model_budget=None, redactor=None):
        url = urlsplit(config['gateway_url'])
        if config.get('mode') != 'local_stub' or config.get('live_enabled') is not False or url.hostname != '127.0.0.1':
            raise ValueError('operations:live_disabled')
        self.redactor = redactor or SharedSimulatedRedactor(BoundaryBudget(operations=8, byte_limit=32768, lifetime=900))
        self.credential = ScopedCredential('infrastructure', config['client_keys']['infrastructure'], config['expires_at'])
        self.gateway = BudgetedGateway(ExplanationGateway(config['gateway_url'], 8,
            client_key=self.credential.value('infrastructure')),
            model_budget or RunAttemptBudget(total=4, per_subject=4, lifetime=900), self.credential,
            subject=config['subject'], profile='infrastructure')

    def __call__(self, facts):
        prompt = redact_checked(self.redactor, json.dumps(facts, sort_keys=True)).text
        value = self.gateway.complete(APPROVED_MODEL_ALIAS, prompt,
            {'correlation_id': str(uuid.uuid4()), 'tenant_ref': 'local-operations'}).output
        # Provider text cannot enter tools, policy, approval or target registration.
        return redact_checked(self.redactor, value['summary']).text

    def budgets(self):
        return {'content_operations_used': self.redactor.budget.operations,
            'content_operations_limit': self.redactor.budget._max_operations, 'utf8_bytes_used': self.redactor.budget.bytes,
            'utf8_bytes_limit': self.redactor.budget._max_bytes, 'client_expiry_epoch': self.credential._expires,
            'rpc_seconds': 8, 'transport': self.gateway.measurement_snapshot()}
