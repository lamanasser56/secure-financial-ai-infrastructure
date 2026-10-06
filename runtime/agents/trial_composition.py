"""Prepared live composition. Private native evidence precedes construction.

No local launcher populates an admission. Fixed qualification and a supervised
synthetic free-text trial have separate grants, ledgers, clients and counters.
The model can propose read tools/explanations, never operational authority.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
import threading
import uuid

from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.composition import BoundaryBudget, IntegratedCore, TenantDatabaseTools
from runtime.agents.credentials import FORBIDDEN_APPLICATION_ENVIRONMENTS, ScopedCredential
from runtime.agents.gateway_budget import RunAttemptBudget, ScopedHTTPGateway
from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
from runtime.agents.operations_model import ExplanationGateway
from runtime.agents.service_restoration import private_file
from runtime.agents.operations import private_directory
from runtime.agents.terminal_audit import TerminalAudit
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure
from runtime.phase3.adapters import _post_json
from runtime.phase3.trusted_runtime import ControlFailure, GatewayResult, RedactionResult, SUPPORTED_ENTITIES

ROOT=Path(__file__).resolve().parents[2]
ACK='I_ACKNOWLEDGE_SUPERVISED_SYNTHETIC_FREE_TEXT_NOT_FIXED_QUALIFICATION'
GATEWAY='http://127.0.0.1:14006'
REDACTOR='http://127.0.0.1:14007/redact'
SCOPES={'fixed_inputs_qualification','supervised_synthetic_free_text'}


def read_json(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError
            result[k]=v
        return result
    return json.loads(private_file(path),object_pairs_hook=unique)


def admit(path, *, scope, source, program_integrity, now=time.time):
    private_directory(Path(path).parent)
    admission=read_json(path)
    fields={'schema_version','scope','source','program_integrity','owner_approved','synthetic_only',
            'processor_location_accepted','fixture_authority_accepted','expires_at','evidence','subject'}
    if (set(admission)!=fields or type(admission['schema_version']) is not int or admission['schema_version']!=1 or scope not in SCOPES
            or admission['subject'] not in {'local-fixture-alpha','local-fixture-beta'}
            or admission['scope']!=scope or admission['source']!=source
            or admission['program_integrity']!=program_integrity
            or any(admission[k] is not True for k in ['owner_approved','synthetic_only','processor_location_accepted','fixture_authority_accepted'])
            or not re.fullmatch('[a-f0-9]{40}',source) or not re.fullmatch('[a-f0-9]{64}',program_integrity)
            or type(admission['expires_at']) not in {int,float} or not now()<admission['expires_at']<=now()+900
            or FORBIDDEN_APPLICATION_ENVIRONMENTS & os.environ.keys()):
        raise ValueError('trial:admission_rejected')
    rows=admission['evidence']
    expected={'campaign','provenance','network','scoped_client_denials','service_quarantine','policy_acceptance','application_isolation','private_channel'}
    if scope=='supervised_synthetic_free_text':expected.add('fixed_integration')
    if type(rows) is not dict or set(rows)!=expected:raise ValueError('trial:missing_gate')
    receipts={}
    for name,row in rows.items():
        if type(row) is not dict or set(row)!={'file','integrity'} or not re.fullmatch('[a-z][a-z0-9-]{1,70}\.json',row['file']):raise ValueError('trial:invalid_receipt')
        raw=private_file(Path(path).parent/row['file'])
        if hashlib.sha256(raw).hexdigest()!=row['integrity']:raise ValueError('trial:receipt_changed')
        receipts[name]=read_json(Path(path).parent/row['file'])
        if name!='campaign' and (receipts[name].get('status')!='PASS' or receipts[name].get('source')!=source):raise ValueError('trial:gate_failed')
    spec=importlib.util.spec_from_file_location('trial_campaign_gate',ROOT/'scripts/validate-sdp-context-campaign-result.py')
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    result=validator.validate(Path(path).parent/rows['campaign']['file'])
    if (result['mode']!='live_synthetic' or result['required_pass']!=70 or result['required_fail']!=0
            or result['observations']!=16 or result['observation_failures'] or result['operational_failures']
            or result['unexecuted'] or result['injected_attempts'] or result['authority_changed']
            or result['outcome']!='SYNTHETIC_POLICY_ONLY_REVIEW_REQUIRED'):
        raise ValueError('trial:redaction_not_qualified')
    containment=receipts['application_isolation']
    if (containment.get('source_overlay') is not False
            or any(containment.get(k) is not True for k in ['peer_namespace_denials','credential_file_denials','network_none','readonly_nonroot','audit_denials','tenant_denials'])
            or not re.fullmatch('sha256:[a-f0-9]{64}',containment.get('application_configuration',''))):
        raise ValueError('trial:application_isolation_unqualified')
    channels=receipts['private_channel']
    if (channels.get('worker_cloud_identity') is not False
            or channels.get('gateway')!=GATEWAY or channels.get('redactor')!=REDACTOR
            or channels.get('authenticated_tunnels') is not True
            or channels.get('current_listener_ownership') is not True):
        raise ValueError('trial:private_channels_unqualified')
    if scope=='supervised_synthetic_free_text':
        fixed=receipts['fixed_integration']
        if fixed.get('scope')!='fixed_inputs_qualification' or fixed.get('all_required_tools_grounded') is not True or any(fixed.get(k) is not True for k in ['actual_model_responses','owned_restoration_verified','audit_preserved','credentials_budgets_unchanged','denials_verified']):
            raise ValueError('trial:fixed_inputs_do_not_admit_free_text')
    return admission


def consume_admission(path,admission):
    directory=private_directory(Path(path).parent)
    marker=directory/('consumed-'+admission['scope']+'.json')
    fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(json.dumps({'scope':admission['scope'],'source':admission['source'],
            'admission_integrity':hashlib.sha256(private_file(path)).hexdigest(),'automatic_replay':False})+'\n')
        stream.flush();os.fsync(stream.fileno())
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class TrialLedger(DurableToolAudit):
    def __init__(self,*args,scope='supervised_synthetic_free_text',**kwargs):
        if scope not in SCOPES:raise ValueError('trial:invalid_scope')
        self.scope=scope
        self.model_limit,self.subject_limit=(16,8) if scope=='fixed_inputs_qualification' else (32,16)
        super().__init__(*args,**kwargs)
        # Count and commit form one atomic reservation; append also locks.
        self._lock=threading.RLock()
    @staticmethod
    def _encode(event):
        if (set(event)!={'event_id','kind','subject','amount'} or not re.fullmatch('[a-f0-9-]{36}',event['event_id'])
                or event['kind'] not in {'model','tool','redaction_input','redaction_output'}
                or event['subject'] not in {'local-fixture-alpha','local-fixture-beta','shared'}
                or type(event['amount']) is not int or not 1<=event['amount']<=4096):
            raise ControlFailure('audit','invalid_event')
        return json.dumps(event,sort_keys=True,separators=(',',':'))

    def reserve(self,kind,subject='shared',amount=1):
        with self._lock:
            if kind not in {'model','tool','redaction_input','redaction_output'} or kind in {'model','tool'} and amount!=1:
                raise ControlFailure('audit','invalid_event')
            self._check_files()
            rows=[json.loads(row[0]) for row in self._db.execute('SELECT event FROM events')]
            used=sum(row['kind']==kind for row in rows)
            cap={'model':self.model_limit,'tool':24,'redaction_input':87,'redaction_output':87}[kind]
            if kind=='model':
                if time.time()>=self.expires:raise BudgetAdmissionFailure('run_deadline_exceeded')
                if used>=cap:raise BudgetAdmissionFailure('total_attempt_budget_exhausted')
                if sum(row['kind']=='model' and row['subject']==subject for row in rows)>=self.subject_limit:
                    raise BudgetAdmissionFailure('subject_attempt_budget_exhausted')
            elif time.time()>=self.expires or used>=cap:
                raise ControlFailure('agent','request_budget_exhausted')
            if kind.startswith('redaction_') and sum(row['amount'] for row in rows if row['kind'].startswith('redaction_'))+amount>524288:
                raise ControlFailure('redaction','input_too_large')
            self.append({'event_id':str(uuid.uuid4()),'kind':kind,'subject':subject,'amount':amount})


class DurableModelBudget(RunAttemptBudget):
    def __init__(self,ledger):
        super().__init__(total=ledger.model_limit,per_subject=ledger.subject_limit,lifetime=900);self.ledger=ledger
    def reserve(self,subject):
        self.ledger.reserve('model',subject);super().reserve(subject)
    def snapshot(self,subject):
        with self.ledger._lock:
            self.ledger._check_files()
            rows=[json.loads(row[0]) for row in self.ledger._db.execute('SELECT event FROM events')]
            counts=super().snapshot(subject)
            return counts|{'total_used':sum(row['kind']=='model' for row in rows),
                'subject_used':sum(row['kind']=='model' and row['subject']==subject for row in rows),
                'remaining_seconds':min(counts['remaining_seconds'],max(0,self.ledger.expires-time.time()))}


class RemoteRedactor:
    offline_simulation=False
    def __init__(self,key,ledger):
        if not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('trial:invalid_redactor_client')
        self.key,self.ledger=key,ledger;self.budget=BoundaryBudget(operations=87)
    def redact(self,value):
        self.budget.reserve(value);self.ledger.reserve('redaction_input',amount=len(value.encode()))
        try:
            result=_post_json(REDACTOR,{'text':value},8,headers={'Authorization':'Bearer '+self.key})
            if (type(result) is not dict or set(result)!={'text','categories'} or type(result['text']) is not str
                    or type(result['categories']) is not list or not all(type(c) is str for c in result['categories'])
                    or not set(result['categories'])<=SUPPORTED_ENTITIES
                    or result['categories']!=sorted(set(result['categories']))):raise ValueError
            self.budget.accept_output(result['text']);self.ledger.reserve('redaction_output',amount=len(result['text'].encode()))
            return RedactionResult(result['text'],tuple(result['categories']))
        except ControlFailure:raise
        except Exception:raise ControlFailure('presidio_anonymizer','unavailable') from None


class TrialTerminal(TerminalAudit):
    @staticmethod
    def _encode(event):
        if event.get('schema_version')!=4 or (event.get('redaction_provider'),event.get('model_provider'))!=('google_sdp_context_candidate','vertex_gemini'):
            raise ControlFailure('audit','invalid_event')
        TerminalAudit._encode(dict(event,schema_version=3,redaction_provider='simulated',model_provider='stub'))
        return json.dumps(event,sort_keys=True,separators=(',',':'))


class TrialGateway(ScopedHTTPGateway):
    offline_simulation=False
    def __init__(self,budget,credential,*,subject,profile,redactor):
        from runtime.agents.composition import ProtocolHTTPGateway
        super().__init__(GATEWAY,budget,credential,subject=subject,profile=profile,timeout=8)
        class Protocol(ProtocolHTTPGateway):
            offline_simulation=False
            def complete(self,*args):
                result=super().complete(*args);return GatewayResult(result.output,True,'live')
        self._gateway=Protocol(GATEWAY,key=self._bound_key,redactor=redactor)


class TrialTools(TenantDatabaseTools):
    def __init__(self,*args,ledger,subject):super().__init__(*args);self.ledger,self.subject=ledger,subject
    def execute(self,invocation):self.ledger.reserve('tool',self.subject);return super().execute(invocation)


def compose_trial(config,*,admission,ledger,terminal,tools_audit,connect):
    if (config.get('mode')!='admitted_synthetic_trial' or config.get('gateway_url')!=GATEWAY
            or admission.get('scope') not in SCOPES or admission.get('owner_approved') is not True
            or admission.get('synthetic_only') is not True
            or config.get('subject')!=admission.get('subject')
            or config.get('subject') not in {'local-fixture-alpha','local-fixture-beta'}
            or not time.time()<config['expires_at']<=min(ledger.expires,admission['expires_at'])):raise ValueError('trial:configuration_rejected')
    budget=DurableModelBudget(ledger);redactor=RemoteRedactor(config['redactor_key'],ledger);agents={}
    for profile in ['financial','infrastructure']:
        identity=TrustedJWTIdentity(profile,issuer='https://fixture-issuer.invalid',audience='portfolio-local-composition',
            certificates=config['certificates'],snapshot_expires_at=config['expires_at'],
            subjects={config['subject']:SubjectGrant(config['tenant'],frozenset({'financial','infrastructure'}))},
            tenant_reference_key=bytes.fromhex(config['tenant_reference_key']))
        client=ScopedCredential(profile,config['client_keys'][profile],config['expires_at'])
        gateway=TrialGateway(budget,client,subject=config['subject'],profile=profile,redactor=redactor)
        tools=TrialTools(connect,identity,config['tenant_directory'],'Bearer '+config['token'],ledger=ledger,subject=config['subject'])
        core=IntegratedCore(profile,identity,identity,identity,redactor,gateway,simulation=False,
            tools=tools,audit_sink=tools_audit,terminal_sink=terminal,providers=('google_sdp_context_candidate','vertex_gemini'))
        agents[profile]=core,'Bearer '+config['token']
    return agents,budget,redactor


class TrialExplainer:
    mode='admitted_synthetic_trial'
    def __init__(self,config,budget,redactor):
        from runtime.agents.gateway_budget import BudgetedGateway
        from runtime.phase3.trusted_runtime import redact_checked
        self.redactor=redactor
        self.credential=ScopedCredential('infrastructure',config['client_keys']['infrastructure'],config['expires_at'])
        class Gateway(ExplanationGateway):
            offline_simulation=False
            def complete(self,*args):
                result=super().complete(*args)
                safe=redact_checked(redactor,result.output['summary']).text
                return GatewayResult({'summary':safe,'classification':'informational'},True,'live')
        self.gateway=BudgetedGateway(Gateway(GATEWAY,8,client_key=self.credential.value('infrastructure')),
                budget,self.credential,subject=config['subject'],profile='infrastructure')
    def __call__(self,facts):
        from runtime.phase3.trusted_runtime import APPROVED_MODEL_ALIAS,redact_checked
        prompt=redact_checked(self.redactor,json.dumps(facts,sort_keys=True)).text
        return self.gateway.complete(APPROVED_MODEL_ALIAS,prompt,{'correlation_id':str(uuid.uuid4()),'tenant_ref':'synthetic-operations'}).output['summary']
    def budgets(self):
        return {'transport':self.gateway.measurement_snapshot(),'content_operations_used':self.redactor.budget.operations,
                'content_operations_limit':87,'utf8_bytes_used':self.redactor.budget.bytes,'utf8_bytes_limit':524288,
                'client_expiry_epoch':self.credential._expires,'rpc_seconds':8}
