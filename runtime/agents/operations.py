"""Registered local operations. No shell, discovery-based writes or model authority.

The first write backend owns process-only demo stacks and public disposable caches.
Container/VM resources are deliberately not inferred from a listening port. The
existing integrated Docker stack can be registered for monitoring only.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import threading
import time
import uuid
import urllib.request
import urllib.error

from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.controls import BoundedInjectionAssessor
from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.prompt_injection import assess_prompt_injection
from runtime.phase4.tool_approval import ApprovalContext, canonical_arguments_digest, verify_tool_approval
from runtime.phase4.tool_policy import PolicyOutcome, ToolPolicyDecision, ToolPolicyInput, evaluate_tool_policy
from runtime.phase4.tool_registry import Approval, Authorization, ExecutionBoundary, OperationType, RiskClass, ToolMetadata

ID = re.compile(r"[a-z][a-z0-9-]{2,47}")
CODES = frozenset({'OK', 'TARGET_DENIED', 'IDENTITY_DENIED', 'APPROVAL_DENIED',
    'EVIDENCE_CHANGED', 'ACTIVE_FILE', 'UNSAFE_FILE', 'INCOMPLETE_VISIBILITY',
    'OWNER_CHANGED', 'NOT_ORPHANED', 'AUDIT_FAILED', 'ACTION_FAILED',
    'BUDGET_EXHAUSTED', 'GATEWAY_UNAVAILABLE', 'MODEL_RESPONSE_REJECTED', 'MODEL_DISABLED', 'INVALID_REQUEST'})
ACTIONS = {'monitor': 'operations.monitor', 'recover': 'operations.recover', 'clean': 'operations.clean',
           'restore': 'operations.restore', 'test_failure': 'operations.test_failure'}


class OperationsBlocked(Exception):
    def __init__(self, code):
        self.code = code if code in CODES else 'ACTION_FAILED'
        super().__init__(self.code)


def digest(value):
    return canonical_arguments_digest(value)


def private_directory(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise OperationsBlocked('UNSAFE_FILE')
    i = path.lstat()
    if not stat.S_ISDIR(i.st_mode) or i.st_uid != os.getuid() or stat.S_IMODE(i.st_mode) != 0o700:
        raise OperationsBlocked('UNSAFE_FILE')
    return path


def process_identity(pid):
    """Never export command text or environment; command digest is private proof."""
    p = Path('/proc') / str(pid)
    try:
        fields = (p / 'stat').read_text().split(') ', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'pid': pid, 'start_ticks': fields[19], 'uid': p.stat().st_uid,
                'command_integrity': hashlib.sha256((p / 'cmdline').read_bytes()).hexdigest()}
    except FileNotFoundError:
        return None


def listeners(pid):
    try:
        owned = {os.readlink(p)[8:-1] for p in (Path('/proc') / str(pid) / 'fd').iterdir()
                 if os.readlink(p).startswith('socket:[')}
        return sorted({int(row.split()[1].split(':')[1], 16)
            for row in Path('/proc/net/tcp').read_text().splitlines()[1:]
            if row.split()[3] == '0A' and row.split()[9] in owned})[:8]
    except (FileNotFoundError, PermissionError):
        return []


def sanitized_log(path):
    """Only closed indicators survive. Log instructions/quotes never reach models."""
    if path is None:
        return {'available': False, 'indicators': [], 'truncated': False}
    i = Path(path).lstat()
    if not stat.S_ISREG(i.st_mode) or i.st_uid != os.getuid() or i.st_nlink != 1:
        raise OperationsBlocked('UNSAFE_FILE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd) != i:
            raise OperationsBlocked('EVIDENCE_CHANGED')
        os.lseek(fd, max(0, i.st_size - 4096), os.SEEK_SET)
        text = os.read(fd, 4096).decode('utf-8', errors='replace').lower()
    finally:
        os.close(fd)
    indicators = [code for code, marker in (('PORT_CONFLICT', 'address already in use'),
        ('STORAGE_FULL', 'no space left on device'), ('MEMORY_PRESSURE', 'out of memory'),
        ('SERVICE_EXIT', 'service exited')) if marker in text]
    return {'available': True, 'indicators': indicators, 'truncated': i.st_size > 4096}


def health_status(ports):
    result = {}
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in sorted(set(ports) & {4001, 8765, 8768}):
        endpoint = '/health/liveliness' if port == 4001 else '/'
        try:
            with client.open('http://127.0.0.1:' + str(port) + endpoint, timeout=1) as response:
                result[str(port)] = response.status
        except urllib.error.HTTPError as failure:
            result[str(port)] = failure.code
        except Exception:
            result[str(port)] = 'UNAVAILABLE'
    return result


@dataclass(frozen=True)
class StackTarget:
    tenant_ref: str
    supervisor: dict
    members: tuple
    mutable: bool = False
    log: Path | None = None
    resource_scope: str = 'process_only'


@dataclass(frozen=True)
class CacheTarget:
    tenant_ref: str
    path: Path
    manifest: tuple
    mutable: bool = False


@dataclass(frozen=True)
class ServiceTarget:
    """Created only by a trusted owner of a separate composition stack."""
    tenant_ref: str
    adapter: object
    mutable: bool = True


def cache_inventory(path):
    root = private_directory(path)
    # Only a flat, specifically disposable public cache, never source or secrets.
    if root.name != 'disposable-cache':
        raise OperationsBlocked('UNSAFE_FILE')
    entries = list(root.iterdir())
    if len(entries) > 32:
        raise OperationsBlocked('BUDGET_EXHAUSTED')
    result = []
    for p in sorted(entries):
        if not re.fullmatch(r'(?:public-[0-9]{1,2}\.cache|trivy\.db|fanal\.db|metadata\.json)', p.name):
            raise OperationsBlocked('UNSAFE_FILE')
        i = p.lstat()
        if (not stat.S_ISREG(i.st_mode) or i.st_uid != os.getuid() or i.st_nlink != 1
                or i.st_dev != root.stat().st_dev or i.st_mode & 0o022
                or i.st_size > 8 * 1024 * 1024):
            raise OperationsBlocked('UNSAFE_FILE')
        result.append((p.name, i.st_dev, i.st_ino, i.st_size, i.st_mtime_ns, i.st_ctime_ns, i.st_blocks))
    if (sum(x[3] for x in result) > 64 * 1024 * 1024
            or sum(x[6] * 512 for x in result) > 64 * 1024 * 1024):
        raise OperationsBlocked('BUDGET_EXHAUSTED')
    return tuple(result)


def active_files(path, *, visibility=None):
    """Fail closed on incomplete /proc visibility, bounded by time and FD count.

    A root read-only inspector may be injected by a reviewed deployment. The
    local backend does not acquire elevated privileges or silently omit users.
    """
    if visibility is not None:
        return visibility(path)
    prefix = str(path) + '/'
    end, count = time.monotonic() + 2, 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            if not (proc / 'cmdline').read_bytes():
                continue
            for kind in ('cwd', 'root'):
                target = os.readlink(proc / kind)
                if target == str(path) or target.startswith(prefix):
                    return True
            for fd in (proc / 'fd').iterdir():
                count += 1
                if count > 16384 or time.monotonic() >= end:
                    raise OperationsBlocked('INCOMPLETE_VISIBILITY')
                target = os.readlink(fd).removesuffix(' (deleted)')
                if target == str(path) or target.startswith(prefix):
                    return True
            for line in (proc / 'maps').read_text()[:1048576].splitlines():
                if len(line.split(None, 5)) == 6:
                    target = line.split(None, 5)[5].removesuffix(' (deleted)')
                    if target.startswith(prefix):
                        return True
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise OperationsBlocked('INCOMPLETE_VISIBILITY') from None
    return False


class OperationsAudit(DurableToolAudit):
    @staticmethod
    def _encode(event):
        fields = {'schema_version', 'event_id', 'phase', 'request_id', 'target_id',
                  'tenant_ref', 'subject_ref', 'action', 'evidence_id', 'code',
                  'mutation_count', 'reclaimed_bytes', 'occurred_at'}
        if type(event) is not dict:raise ControlFailure('audit','invalid_event')
        if event.get('schema_version')==2:
            if set(event)!=fields|{'verification'} or event.get('phase')!='outcome':raise ControlFailure('audit','invalid_event')
            proof=event['verification']
            required={'health_verified','restore_attempts','attempt_limit','credentials_renewed','application_restarted','database_recreated','request_replayed'}
            optional={'controlled_failure_verified','health_checks','credentials_unchanged'}
            if (type(proof) is not dict or not required<=set(proof)<=required|optional
                    or type(proof['attempt_limit']) is not int or proof['attempt_limit']!=1 or type(proof['restore_attempts']) is not int or not 0<=proof['restore_attempts']<=1
                    or any(proof[k] is not False for k in ['credentials_renewed','application_restarted','database_recreated','request_replayed'])
                    or any(type(proof[k]) is not bool for k in set(proof)-{'restore_attempts','attempt_limit','health_checks'})
                    or 'health_checks' in proof and (type(proof['health_checks']) is not int or not 0<=proof['health_checks']<=32)):
                raise ControlFailure('audit','invalid_event')
            if event['code']=='OK' and (event['action']=='restore' and not (proof['health_verified'] and proof['restore_attempts']==1)
                    or event['action']=='test_failure' and proof.get('controlled_failure_verified') is not True):
                raise ControlFailure('audit','invalid_event')
            fields=fields|{'verification'}
        if (set(event) != fields or type(event['schema_version']) is not int or event['schema_version'] not in {1,2}
                or event['phase'] not in {'observation', 'proposal', 'approval', 'admission', 'step', 'outcome', 'model_admission', 'model_outcome'}
                or event['code'] not in CODES or event['action'] not in ACTIONS
                or not ID.fullmatch(event['target_id'])
                or not re.fullmatch(r'[a-zA-Z0-9:._-]{8,128}', event['event_id'])
                or not re.fullmatch(r'[a-zA-Z0-9:._-]{8,128}', event['request_id'])
                or not re.fullmatch(r'[a-f0-9]{64}', event['evidence_id'])
                or any(not re.fullmatch(r'[a-f0-9]{16}', event[k]) for k in ('tenant_ref', 'subject_ref'))
                or any(type(event[k]) is not int or not 0 <= event[k] <= bound
                       for k, bound in (('mutation_count', 32), ('reclaimed_bytes', 64 * 1024 * 1024)) )):
            raise ControlFailure('audit', 'invalid_event')
        stamp = datetime.fromisoformat(event['occurred_at'])
        if stamp.tzinfo is None:
            raise ControlFailure('audit', 'invalid_event')
        return json.dumps(event, sort_keys=True, separators=(',', ':'))


def tool_metadata(action):
    write = action != 'monitor'
    return ToolMetadata('ops_' + action, 'Registered ' + action,
        'Bounded server-registered local operation with immediate ownership checks.',
        '1.0.0', 'Local operations operator', True,
        RiskClass.IRREVERSIBLE_HIGH_IMPACT if write else RiskClass.LOW_RISK_READ,
        OperationType.WRITE if write else OperationType.READ,
        'contracts/operations/action.schema.json', 'contracts/operations/result.schema.json',
        Authorization(ACTIONS[action]), Approval(write, 'local-operator' if write else None),
        'standard', 'internal', ExecutionBoundary(20, 1))


class RegisteredPolicy:
    def __init__(self, allowed):
        self.allowed = allowed

    def evaluate(self, value):
        if not self.allowed:
            return ToolPolicyDecision(PolicyOutcome.DENY, 'engine_denied')
        if value.registry_requires_approval:
            return ToolPolicyDecision(PolicyOutcome.REQUIRE_APPROVAL, 'registry_requires_approval')
        return ToolPolicyDecision(PolicyOutcome.ALLOW, 'engine_allowed')


class ApprovalStore:
    def __init__(self):
        self.records = {}

    def retrieve_verified(self, identifier):
        return self.records.get(identifier)


def eligible(target, current, action):
    return bool(target.mutable and (
        (isinstance(target, ServiceTarget) and action in {'restore', 'test_failure'}
         and current.get('permitted_action') == action)
        or
        (action == 'recover' and isinstance(target, StackTarget)
         and not current['supervisor_alive'] and current['members_alive']
         and len(target.members) <= 4 and target.resource_scope == 'process_only')
        or (action == 'clean' and isinstance(target, CacheTarget)
            and not current['active'] and current['files'])))


class OperationsController:
    """One serialized operator run. Journal admission precedes every mutation."""
    def __init__(self, audit, identity, authorization, targets, *, approval_secret,
                 visibility=None, clock=time.time, lifetime=1800, model=None):
        if not 0 < lifetime <= 1800 or len(targets) > 8:
            raise ValueError('operations:invalid_configuration')
        if any(not ID.fullmatch(k) for k in targets):
            raise ValueError('operations:invalid_configuration')
        self.audit, self.identity, self.authorization = audit, identity, authorization
        self.targets = dict(targets)
        self.secret, self.visibility, self.clock = approval_secret, visibility, clock
        self.expires = clock() + lifetime
        self.model, self.models = model, 0
        self.observations, self.actions, self.bytes, self.mutations = 0, 0, 0, 0
        self.poisoned, self.pending, self.reports = False, {}, []
        self.approvals = ApprovalStore()
        self.lock = threading.RLock()
        # New controllers cannot replenish a retained run or replay interrupted
        # admissions. Reopen is available for inspection, with writes disabled.
        self.poisoned = bool(audit._db.execute('SELECT COUNT(*) FROM events').fetchone()[0])

    def budgets(self):
        try:
            audit_events = self.audit._db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        except Exception:
            audit_events = None
        model_limits=None
        if hasattr(self.model,'budgets'):
            try:model_limits=self.model.budgets()
            except Exception:
                # Broken shared accounting must neither allow another write nor
                # make deterministic observations depend on model availability.
                self.poisoned=True
                model_limits={'available':False,'code':'REQUIRED_MODEL_ACCOUNTING_UNAVAILABLE'}
        return {'observations_used': self.observations, 'observations_limit': 64,
            'actions_used': self.actions, 'actions_limit': 4,
            'mutation_steps_used': self.mutations, 'mutation_steps_limit': 64,
            'evidence_bytes_used': self.bytes, 'evidence_bytes_limit': 262144,
            'model_attempts_used': self.models, 'model_attempts_limit': 4,
            'per_action_seconds': 20, 'approval_seconds': 180, 'expiry_epoch': self.expires,
            'retries': 0, 'audit_available': not self.poisoned,
            'model_mode': getattr(self.model,'mode','local_stub') if self.model else 'disabled',
            'live_enabled': getattr(self.model,'mode',None)=='admitted_synthetic_trial',
            'cache_file_limit': 32, 'cache_byte_limit': 67108864, 'stack_member_limit': 4,
            'log_byte_limit': 4096,
            'targets_used': len(self.targets), 'targets_limit': 8,
            'pending_proposals_used': len(self.pending), 'pending_proposals_limit': 16,
            'retained_reports_limit': 16,
            'audit_events_used': audit_events, 'audit_events_limit': self.audit._maximum,
            'audit_file_bytes_limit': 2097152,
            'model_utf8_input_output_limit': 4096, 'model_summary_byte_limit': 2048,
            'model_output_token_limit': 256, 'model_run_seconds': 900,
            'model_limits': model_limits}

    def _principal(self, tid, action):
        if type(tid) is not str or not ID.fullmatch(tid):
            raise OperationsBlocked('TARGET_DENIED')
        if self.clock() >= self.expires:
            raise OperationsBlocked('BUDGET_EXHAUSTED')
        try:
            claims = self.identity.authenticate(self.authorization)
            tenant = self.identity.resolve(claims)
            allowed = self.identity.authorize(claims, tenant, ACTIONS[action])
        except Exception:
            raise OperationsBlocked('IDENTITY_DENIED') from None
        target = self.targets.get(tid)
        if not target or tenant.tenant_ref != target.tenant_ref or not allowed:
            raise OperationsBlocked('TARGET_DENIED')
        return target, tenant.tenant_ref, hashlib.sha256(claims.subject.encode()).hexdigest()[:16]

    def _event(self, phase, request, tid, action, evidence, code='OK', count=0, reclaimed=0, *, outcome_principal=None,verification=None):
        if outcome_principal is None:
            _, tenant, subject = self._principal(tid, action)
        else:
            # Recording the outcome of an already admitted action is read-only
            # authority. Expiry must still block each mutation, but must not
            # suppress its terminal journal or fabricate an audit failure.
            if phase != 'outcome':
                raise OperationsBlocked('INVALID_REQUEST')
            tenant, subject = outcome_principal
        if self.poisoned:
            raise OperationsBlocked('AUDIT_FAILED')
        try:
            self.audit.append({'schema_version': 1 if verification is None else 2, 'event_id': str(uuid.uuid4()),
                'phase': phase, 'request_id': request, 'target_id': tid,
                'tenant_ref': tenant, 'subject_ref': subject, 'action': action,
                'evidence_id': evidence, 'code': code, 'mutation_count': count,
                'reclaimed_bytes': reclaimed,
                **({'verification':verification} if verification is not None else {}),
                'occurred_at': datetime.now(timezone.utc).isoformat()})
        except Exception:
            self.poisoned = True
            raise OperationsBlocked('AUDIT_FAILED') from None

    def _snapshot(self, target):
        if isinstance(target, ServiceTarget):
            return target.adapter.snapshot()
        if isinstance(target, StackTarget):
            actual = [process_identity(r['pid']) for r in target.members]
            for expected, current in zip(target.members, actual):
                if current is not None and current != expected:
                    raise OperationsBlocked('OWNER_CHANGED')
            supervisor = process_identity(target.supervisor['pid'])
            if supervisor is not None and supervisor != target.supervisor:
                raise OperationsBlocked('OWNER_CHANGED')
            ports = [listeners(x['pid']) if x else [] for x in actual]
            return {'kind': 'stack', 'supervisor_alive': supervisor is not None,
                'members_alive': sum(x is not None for x in actual),
                'listeners': ports, 'http_health_status': health_status([p for row in ports for p in row]),
                'ownership_verified': True, 'processes': actual,
                'log': sanitized_log(target.log), 'resource_scope': target.resource_scope}
        if isinstance(target, CacheTarget):
            inventory = cache_inventory(target.path)
            if inventory != target.manifest and inventory:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            active = active_files(target.path, visibility=self.visibility)
            return {'kind': 'cache', 'files': len(inventory), 'bytes': sum(x[3] for x in inventory),
                    'allocated_bytes': sum(x[6] * 512 for x in inventory),
                    'active': active, 'inventory': inventory}
        raise OperationsBlocked('TARGET_DENIED')

    def observe(self, tid):
        with self.lock:
            if self.observations >= 64:
                raise OperationsBlocked('BUDGET_EXHAUSTED')
            self.observations += 1
            target, _, _ = self._principal(tid, 'monitor')
            value = self._snapshot(target)
            evidence = digest(value)
            encoded = len(json.dumps(value).encode())
            if self.bytes + encoded > 262144:
                raise OperationsBlocked('BUDGET_EXHAUSTED')
            self.bytes += encoded
            try:
                self._event('observation', str(uuid.uuid4()), tid, 'monitor', evidence)
            except OperationsBlocked as failure:
                if failure.code != 'AUDIT_FAILED':
                    raise
            public = {k: v for k, v in value.items() if k not in {'inventory', 'processes'}}
            fs = os.statvfs('/')
            public['root_storage'] = {'available_bytes': fs.f_bavail * fs.f_frsize,
                                      'total_bytes': fs.f_blocks * fs.f_frsize}
            condition = value['condition'] if isinstance(target, ServiceTarget) else ('ORPHANED' if value.get('members_alive') and not value.get('supervisor_alive')
                else 'RUNNING' if value.get('supervisor_alive') else 'STOPPED') if value['kind'] == 'stack' else ('ACTIVE' if value['active'] else 'DISPOSABLE')
            report = {'target_id': tid, 'evidence_id': evidence, 'observed': condition,
                'suspected_causes': [], 'unknowns': ['SERVICE_EXIT_CAUSE'] if isinstance(target, ServiceTarget) and condition == 'SERVICE_FAILED' else ['SUPERVISOR_EXIT_CAUSE'] if condition == 'ORPHANED'
                    else ['IDENTITY_AND_AUTHORIZED_REQUEST_PATH_UNTESTED'] if isinstance(target, StackTarget) else [],
                'facts': public, 'actions': [value['permitted_action']] if isinstance(target, ServiceTarget) and target.mutable and value.get('permitted_action') else ['recover'] if isinstance(target, StackTarget) and target.mutable and condition == 'ORPHANED' and target.resource_scope == 'process_only'
                    else ['clean'] if isinstance(target, CacheTarget) and target.mutable and not value['active'] and value['files'] else [],
                'policy_decision': 'monitor_allowed' if not self.poisoned else 'monitor_observed_audit_unavailable',
                'audit_committed': not self.poisoned, 'budgets': self.budgets()}
            if self.poisoned:
                report['actions'] = []
            self.reports.append(report)
            self.reports = self.reports[-16:]
            return report

    def propose(self, tid, action, evidence):
        with self.lock:
            if action not in {'recover', 'clean', 'restore', 'test_failure'} or not re.fullmatch('[a-f0-9]{64}', evidence):
                raise OperationsBlocked('INVALID_REQUEST')
            target, tenant, subject = self._principal(tid, action)
            current = self._snapshot(target)
            if digest(current) != evidence:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            allowed = eligible(target, current, action)
            args = {'target_id': tid, 'evidence_id': evidence}
            request = str(uuid.uuid4()); tool = tool_metadata(action)
            context = ApprovalContext(request, tenant, subject, tool.id, tool.version,
                ACTIONS[action], tool.risk_classification.value, digest(args))
            assess_prompt_injection(BoundedInjectionAssessor(), args)
            decision = evaluate_tool_policy(RegisteredPolicy(bool(allowed)), ToolPolicyInput(
                request, tenant, subject, tool.id, tool.version, ACTIONS[action],
                tool.risk_classification.value, digest(args), True), tool)
            if decision.outcome is PolicyOutcome.DENY:
                raise OperationsBlocked('TARGET_DENIED')
            self._event('proposal', request, tid, action, evidence)
            self.pending[request] = (tid, action, evidence, context)
            if len(self.pending) > 16:
                self.pending.pop(next(iter(self.pending)))
            return {'request_id': request, 'target_id': tid, 'action': action,
                    'evidence_id': evidence, 'policy_decision': decision.outcome.value,
                    'approval_required': True, 'approval_expiry_seconds': 180}

    def approve(self, request, operator_secret):
        with self.lock:
            if not hmac.compare_digest(str(operator_secret), self.secret):
                raise OperationsBlocked('APPROVAL_DENIED')
            if request not in self.pending:
                raise OperationsBlocked('APPROVAL_DENIED')
            if any(r['request_id'] == request for r in self.approvals.records.values()):
                raise OperationsBlocked('APPROVAL_DENIED')
            tid, action, evidence, context = self.pending[request]
            target, tenant, subject = self._principal(tid, action)
            if (tenant, subject) != (context.tenant_ref, context.subject_ref):
                raise OperationsBlocked('IDENTITY_DENIED')
            if digest(self._snapshot(target)) != evidence:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            self._event('approval', request, tid, action, evidence)
            identifier = 'a' + secrets.token_urlsafe(24)
            now = datetime.now(timezone.utc)
            record = {'schema_version': 1, 'approval_id': identifier, 'decision': 'approved',
                **context.__dict__, 'issued_at': now.isoformat(),
                'expires_at': (now + timedelta(seconds=180)).isoformat(), 'consumed': False}
            self.approvals.records[identifier] = record
            return {'approval_id': identifier, 'request_id': request,
                    'expires_at': record['expires_at'], 'action': action, 'target_id': tid,
                    'evidence_id': evidence}

    def execute(self, request, approval):
        with self.lock:
            if request not in self.pending:
                raise OperationsBlocked('APPROVAL_DENIED')
            tid, action, evidence, context = self.pending[request]
            target, tenant, subject = self._principal(tid, action)
            if (tenant, subject) != (context.tenant_ref, context.subject_ref):
                raise OperationsBlocked('IDENTITY_DENIED')
            try:
                approved_decision = verify_tool_approval(self.approvals, approval, context, now=datetime.now(timezone.utc))
            except Exception:
                raise OperationsBlocked('APPROVAL_DENIED') from None
            if self.actions >= 4 or self.mutations >= 64:
                raise OperationsBlocked('BUDGET_EXHAUSTED')
            before = self._snapshot(target)
            if digest(before) != evidence:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            if not eligible(target, before, action):
                raise OperationsBlocked('TARGET_DENIED')
            self._event('admission', request, tid, action, evidence)
            self.approvals.records[approval]['consumed'] = True
            del self.pending[request]
            self.actions += 1
            started, mutations, reclaimed, code = time.monotonic(), 0, 0, 'OK'
            before_mutations = self.mutations
            storage_before = os.statvfs('/').f_bavail * os.statvfs('/').f_frsize
            try:
                if isinstance(target, ServiceTarget):
                    def admit_step():
                        if time.monotonic() - started >= 20 or self.mutations >= 64:
                            raise OperationsBlocked('BUDGET_EXHAUSTED')
                        self._principal(tid, action)
                        if datetime.now(timezone.utc) >= approved_decision.expires_at:
                            raise OperationsBlocked('APPROVAL_DENIED')
                        self._event('step', request, tid, action, evidence, count=mutations)
                        # Audit commit may take time: recheck expiry after it.
                        self._principal(tid, action)
                        if datetime.now(timezone.utc) >= approved_decision.expires_at:
                            raise OperationsBlocked('APPROVAL_DENIED')
                        self.mutations += 1
                    target.adapter.execute(action, before, started + 20, admit_step)
                    mutations = 1
                elif isinstance(target, StackTarget):
                    if process_identity(target.supervisor['pid']) is not None:
                        raise OperationsBlocked('NOT_ORPHANED')
                    for member in target.members:
                        if time.monotonic() - started >= 20:
                            raise OperationsBlocked('BUDGET_EXHAUSTED')
                        if process_identity(member['pid']) != member or member['uid'] != os.getuid() or member['pid'] == os.getpid():
                            raise OperationsBlocked('OWNER_CHANGED')
                        fd = os.pidfd_open(member['pid'])
                        try:
                            if process_identity(member['pid']) != member:
                                raise OperationsBlocked('OWNER_CHANGED')
                            self._event('step', request, tid, action, evidence, count=mutations)
                            if time.monotonic() - started >= 20:
                                raise OperationsBlocked('BUDGET_EXHAUSTED')
                            if process_identity(target.supervisor['pid']) is not None or process_identity(member['pid']) != member:
                                raise OperationsBlocked('OWNER_CHANGED')
                            self._principal(tid, action)
                            if datetime.now(timezone.utc) >= approved_decision.expires_at:
                                raise OperationsBlocked('APPROVAL_DENIED')
                            signal.pidfd_send_signal(fd, signal.SIGTERM)
                            self.mutations += 1; mutations += 1
                        finally:
                            os.close(fd)
                    until = min(started + 20, time.monotonic() + 2)
                    while time.monotonic() < until and any(process_identity(x['pid']) for x in target.members):
                        time.sleep(.05)
                    if any(process_identity(x['pid']) for x in target.members):
                        raise OperationsBlocked('ACTION_FAILED')
                else:
                    expected = list(target.manifest)
                    for row in target.manifest:
                        if time.monotonic() - started >= 20 or self.mutations >= 64:
                            raise OperationsBlocked('BUDGET_EXHAUSTED')
                        if cache_inventory(target.path) != tuple(expected):
                            raise OperationsBlocked('EVIDENCE_CHANGED')
                        if active_files(target.path, visibility=self.visibility):
                            raise OperationsBlocked('ACTIVE_FILE')
                        self._event('step', request, tid, action, evidence, count=mutations)
                        if active_files(target.path, visibility=self.visibility):
                            raise OperationsBlocked('ACTIVE_FILE')
                        if time.monotonic() - started >= 20:
                            raise OperationsBlocked('BUDGET_EXHAUSTED')
                        root_fd = os.open(target.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                        try:
                            info = os.stat(row[0], dir_fd=root_fd, follow_symlinks=False)
                            if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != row[1:6]:
                                raise OperationsBlocked('EVIDENCE_CHANGED')
                            self._principal(tid, action)
                            if datetime.now(timezone.utc) >= approved_decision.expires_at:
                                raise OperationsBlocked('APPROVAL_DENIED')
                            os.unlink(row[0], dir_fd=root_fd)
                            self.mutations += 1; mutations += 1; reclaimed += row[6] * 512
                            os.fsync(root_fd)
                        finally:
                            os.close(root_fd)
                        expected.remove(row)
                    if cache_inventory(target.path):
                        raise OperationsBlocked('ACTION_FAILED')
            except OperationsBlocked as failure:
                code = failure.code
            except Exception:
                code = 'ACTION_FAILED'
            if isinstance(target, ServiceTarget):
                mutations = self.mutations - before_mutations
            try:
                self._event('outcome', request, tid, action, evidence, code, mutations, reclaimed,
                            outcome_principal=(tenant, subject),
                            verification=target.adapter.verification() if isinstance(target,ServiceTarget) else None)
            except OperationsBlocked:
                code = 'AUDIT_FAILED'
            outcome = {'request_id': request, 'target_id': tid, 'action': action,
                'evidence_id': evidence, 'status': 'VERIFIED' if code == 'OK' else 'FAILED',
                'code': code, 'mutation_count': mutations, 'reclaimed_allocated_bytes': reclaimed,
                'seconds': round(time.monotonic() - started, 3), 'audit_committed': code != 'AUDIT_FAILED',
                'root_available_bytes_before': storage_before,
                'root_available_bytes_after': os.statvfs('/').f_bavail * os.statvfs('/').f_frsize,
                'budgets': self.budgets()}
            if isinstance(target, ServiceTarget):
                outcome['verification'] = target.adapter.verification()
                # A start attempt is consumed even if startup/verification fails.
                outcome['mutation_count'] = self.mutations - before_mutations
            self.reports.append(outcome)
            return outcome

    def explain(self, tid):
        report = self.observe(tid)
        if self.poisoned:
            return {'code':'AUDIT_FAILED','monitoring_available':True,'evidence':report}
        if self.model is None:
            return {'code': 'MODEL_DISABLED', 'monitoring_available': True, 'evidence': report}
        if self.models >= 4:
            raise OperationsBlocked('BUDGET_EXHAUSTED')
        self.models += 1
        # Only typed facts and indicator enums; no raw logs, paths or commands.
        try:
            request=str(uuid.uuid4())
            self._event('model_admission',request,tid,'monitor',report['evidence_id'])
            result = self.model(report)
            self._event('model_outcome',request,tid,'monitor',report['evidence_id'])
            return {'code': 'OK', 'mode': getattr(self.model,'mode','local_stub'), 'untrusted_explanation': result,
                    'action_authority': False, 'evidence': report}
        except OperationsBlocked as failure:
            return {'code':failure.code,'monitoring_available':True,'evidence':report}
        except ControlFailure as failure:
            if failure.stage=='audit':
                self.poisoned=True
                return {'code':'AUDIT_FAILED','monitoring_available':True,'evidence':report}
            code = 'MODEL_RESPONSE_REJECTED' if failure.stage in {'structured_output_validation', 'model_output_validation'} else 'GATEWAY_UNAVAILABLE'
            return {'code': code, 'monitoring_available': True, 'evidence': report}
        except Exception:
            return {'code': 'GATEWAY_UNAVAILABLE', 'monitoring_available': True, 'evidence': report}

    def diagnose(self, tid, evidence):
        """Measured observations establish action eligibility, never model text."""
        with self.lock:
            target, _, _ = self._principal(tid, 'monitor')
            current = self._snapshot(target)
            if digest(current) != evidence:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            condition = current.get('condition', 'REGISTERED_LOCAL_TARGET')
            return {'target_id': tid, 'evidence_id': evidence,
                'observed': condition, 'confirmed': ['REGISTERED_PROCESS_EXITED'] if condition == 'SERVICE_FAILED' else [],
                'suspected_causes': [], 'unknowns': ['SERVICE_EXIT_CAUSE'] if condition == 'SERVICE_FAILED' else [],
                'permitted_action': None if self.poisoned else current.get('permitted_action'),
                'model_authority': False, 'policy_authority': 'registered_code_controls',
                'budgets': self.budgets()}
