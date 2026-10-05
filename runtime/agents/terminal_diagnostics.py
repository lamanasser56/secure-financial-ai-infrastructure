"""Closed terminal codes. No exception messages, inputs or credential values."""
from runtime.phase3.trusted_runtime import ControlFailure

STAGES = frozenset({
    'agent', 'authentication', 'tenant_context', 'authorization',
    'structured_input_validation', 'agent_policy_engine', 'presidio_analyzer',
    'presidio_anonymizer', 'litellm', 'structured_output_validation', 'audit',
    'prompt_injection_assessment', 'redaction', 'human_approval_verification',
})
REASONS = frozenset({
    'required_control_failed', 'deadline_exceeded', 'invalid_token',
    'invalid_correlation', 'malformed_claims', 'malformed_context', 'invalid_request',
    'denied', 'timeout', 'unavailable', 'malformed_decision', 'malformed_result',
    'ambiguous_result', 'incomplete_redaction', 'invalid_configuration', 'invalid_event',
    'invalid_language', 'invalid_context', 'invalid_limits', 'unsafe_input',
    'unsafe_context', 'unsafe_result', 'context_too_large', 'input_too_large',
    'output_too_large', 'invalid_refusal', 'invalid_clarification',
    'ungrounded_response', 'request_budget_exhausted', 'output_schema_mismatch',
    'malformed_assessment', 'suspected_injection', 'credential_unavailable',
    'attempt_budget', 'subject_attempt_budget_exhausted',
    'total_attempt_budget_exhausted', 'run_deadline_exceeded',
})
BUDGET_REASONS = frozenset({
    'subject_attempt_budget_exhausted', 'total_attempt_budget_exhausted',
    'run_deadline_exceeded',
})


class BudgetAdmissionFailure(ControlFailure):
    """Keep legacy control semantics and carry one exact closed budget reason."""
    def __init__(self, reason):
        if reason not in BUDGET_REASONS:
            raise ValueError('agent:invalid_budget_diagnostic')
        super().__init__('litellm', 'attempt_budget')
        self.reason = reason


def terminal_failure(error):
    stage, reason = 'agent', 'required_control_failed'
    if isinstance(error, ControlFailure):
        candidate = error.reason if isinstance(error, BudgetAdmissionFailure) else error.category
        if (type(error.stage) is str and error.stage in STAGES
                and type(candidate) is str and candidate in REASONS):
            stage, reason = error.stage, candidate
    return {'stage': stage, 'reason': reason}


def validate_terminal_failure(value):
    if (type(value) is not dict or set(value) != {'stage', 'reason'}
            or type(value['stage']) is not str or value['stage'] not in STAGES
            or type(value['reason']) is not str or value['reason'] not in REASONS):
        raise ControlFailure('audit', 'invalid_event')
    return dict(value)
