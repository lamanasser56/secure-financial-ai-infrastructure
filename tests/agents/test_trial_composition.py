"""Admission regressions only; all provider transport is constructed/local."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from runtime.agents.trial_composition import TrialLedger,DurableModelBudget,RemoteRedactor,admit,compose_trial,consume_admission
from runtime.agents.gateway_budget import BudgetedGateway
from runtime.agents.credentials import ScopedCredential
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure,terminal_failure
from runtime.phase3.trusted_runtime import APPROVED_MODEL_ALIAS
from runtime.phase3.trusted_runtime import ControlFailure

ROOT=Path(__file__).resolve().parents[2]


class TrialAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.path.chmod(0o700)
        self.source='a'*40;self.program='b'*64
        self.claim={'schema_version':1,'scope':'supervised_synthetic_free_text','source':self.source,
            'program_integrity':self.program,'owner_approved':True,'synthetic_only':True,
            'processor_location_accepted':True,'fixture_authority_accepted':True,
            'expires_at':time.time()+120,'evidence':{},'subject':'local-fixture-alpha'}
        for name in ['campaign','provenance','network','scoped_client_denials','service_quarantine','policy_acceptance','fixed_integration']:
            value={'status':'PASS','source':self.source}
            if name=='campaign':value=json.loads((ROOT/'evaluation/google-sdp-context/campaign-offline-result.json').read_text())
            if name=='fixed_integration':value|={'scope':'fixed_inputs_qualification','all_required_tools_grounded':True}
            p=self.path/(name.replace('_','-')+'.json');self.write(p,value)
            self.claim['evidence'][name]={'file':p.name,'integrity':hashlib.sha256(p.read_bytes()).hexdigest()}
        self.write(self.path/'admission.json',self.claim)

    def tearDown(self):self.tmp.cleanup()

    def write(self,path,value):path.write_text(json.dumps(value));path.chmod(0o600)

    def check(self):return admit(self.path/'admission.json',scope='supervised_synthetic_free_text',source=self.source,program_integrity=self.program)

    def test_offline_campaign_cannot_admit_live_transport(self):
        with self.assertRaisesRegex(ValueError,'redaction_not_qualified'):self.check()

    def test_fixed_input_scope_does_not_admit_free_text(self):
        self.claim['scope']='fixed_inputs_qualification';self.write(self.path/'admission.json',self.claim)
        with self.assertRaisesRegex(ValueError,'admission_rejected'):self.check()

    def test_once_only_admission_cannot_replenish_a_second_state(self):
        consume_admission(self.path/'admission.json',self.claim)
        with self.assertRaises(FileExistsError):consume_admission(self.path/'admission.json',self.claim)

    def test_source_program_expiry_owner_and_receipt_hash_are_mandatory(self):
        for key,value in [('source','c'*40),('program_integrity','d'*64),('expires_at',0),('owner_approved',False)]:
            with self.subTest(key=key):
                claim=self.claim|{key:value};self.write(self.path/'admission.json',claim)
                with self.assertRaises(ValueError):self.check()
        self.write(self.path/'admission.json',self.claim)
        (self.path/'network.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'receipt_changed'):self.check()

    def test_configuration_cannot_construct_without_owner_admission(self):
        with self.assertRaises(ValueError):compose_trial({'mode':'admitted_synthetic_trial','gateway_url':'http://127.0.0.1:14006'},admission={},ledger=None,terminal=None,tools_audit=None,connect=lambda:None)

    def test_durable_shared_reservations_reopen_without_replenishment(self):
        path=self.path/'ledger';path.mkdir(mode=0o700)
        ledger=TrialLedger(path);ledger.expires=time.time()+120
        for _ in range(16):ledger.reserve('model','local-fixture-alpha')
        with self.assertRaises(ControlFailure):ledger.reserve('model','local-fixture-alpha')
        ledger.reserve('model','local-fixture-beta');ledger.close()
        ledger=TrialLedger(path);ledger.expires=time.time()+120
        with self.assertRaises(ControlFailure):ledger.reserve('model','local-fixture-alpha')
        self.assertEqual(ledger._db.execute('SELECT COUNT(*) FROM events').fetchone()[0],17)
        ledger.close()

    def test_byte_capacity_expiry_and_event_kind_deny_before_dispatch(self):
        path=self.path/'ledger';path.mkdir(mode=0o700)
        ledger=TrialLedger(path);ledger.expires=time.time()+120
        with self.assertRaises(ControlFailure):ledger.reserve('model','local-fixture-alpha',2)
        with self.assertRaises(ControlFailure):ledger.reserve('unknown')
        ledger.expires=0
        with self.assertRaises(ControlFailure):ledger.reserve('tool','local-fixture-alpha')
        self.assertEqual(ledger._db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
        ledger.close()

    def test_durable_model_denial_has_exact_terminal_reason_and_attempt_accounting(self):
        path=self.path/'ledger';path.mkdir(mode=0o700)
        ledger=TrialLedger(path);ledger.expires=time.time()+120
        for _ in range(16):ledger.reserve('model','local-fixture-alpha')
        upstream=mock.Mock();upstream.measurement_snapshot.return_value={}
        client=ScopedCredential('financial','sk-'+('a'*48),time.time()+120)
        gateway=BudgetedGateway(upstream,DurableModelBudget(ledger),client,subject='local-fixture-alpha',profile='financial')
        with self.assertRaises(BudgetAdmissionFailure) as failure:
            gateway.complete(APPROVED_MODEL_ALIAS,'synthetic',{})
        self.assertEqual(terminal_failure(failure.exception),{'stage':'litellm','reason':'subject_attempt_budget_exhausted'})
        self.assertEqual(gateway.measurement_snapshot()['budget_denials'],1)
        self.assertEqual(gateway.measurement_snapshot()['budget_admissions'],0)
        self.assertEqual(gateway.measurement_snapshot()['shared_run_budget']['subject_used'],16)
        self.assertEqual(gateway.measurement_snapshot()['shared_run_budget']['total_used'],16)
        upstream.complete.assert_not_called()
        ledger.close()

    def test_preserved_sdk_ceiling_and_shared_input_output_bytes(self):
        path=self.path/'ledger';path.mkdir(mode=0o700)
        ledger=TrialLedger(path);ledger.expires=time.time()+120
        for _ in range(64):
            ledger.reserve('redaction_input',amount=4096);ledger.reserve('redaction_output',amount=4096)
        with self.assertRaises(ControlFailure):ledger.reserve('redaction_input',amount=1)
        ledger.close()
        path=self.path/'ceiling';path.mkdir(mode=0o700)
        ledger=TrialLedger(path);ledger.expires=time.time()+120
        for _ in range(87):ledger.reserve('redaction_input',amount=1)
        with self.assertRaises(ControlFailure):ledger.reserve('redaction_input',amount=1)
        ledger.close()

    def test_bridge_fixed_approval_cannot_admit_supervised_text(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('bridge',ROOT/'scripts/serve-synthetic-demo-redactor.py')
        bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
        claim={'approved':True,'program_sha256':'a'*64,'project_id':'approved-project','key':'b'*64,
            'expires_at':time.time()+30,'policy_sha256':bridge.POLICY_HASH,
            'redaction_qualification':'QUALIFIED_FOR_SUPERVISED_SYNTHETIC_SCOPE',
            'scope':'supervised_synthetic_free_text','campaign_evidence_sha256':'c'*64,'fixed_integration_evidence_sha256':'d'*64}
        with mock.patch.dict(os.environ,{'PORTFOLIO_SYNTHETIC_LIVE_DEMO_ACK':bridge.ACK},clear=True):
            with self.assertRaises(ValueError):bridge.admit_bridge(claim)
        with mock.patch.dict(os.environ,{'PORTFOLIO_SUPERVISED_TRIAL_ACK':bridge.TRIAL_ACK},clear=True):
            self.assertEqual(bridge.admit_bridge(claim),'supervised_synthetic_free_text')
            with self.assertRaises(ValueError):bridge.admit_bridge(claim|{'scope':'arbitrary'})

    def test_redaction_output_reservation_retains_audit_failure_before_delivery(self):
        ledger=mock.Mock();ledger.reserve.side_effect=[None,ControlFailure('audit','invalid_event')]
        redactor=RemoteRedactor('a'*64,ledger)
        with mock.patch('runtime.agents.trial_composition._post_json',return_value={'text':'synthetic','categories':[]}):
            with self.assertRaises(ControlFailure) as failure:redactor.redact('synthetic')
        self.assertEqual((failure.exception.stage,failure.exception.category),('audit','invalid_event'))

    def test_candidate_trace_retains_finite_audit_and_capacity_failure_codes(self):
        from runtime.agents.composition import CandidateTraceCollector
        value={'schema_version':1,'request_id':'synthetic:model:1','tenant_ref':'a'*16,'subject_ref':'b'*16,
            'outcome':'blocked','failed_stage':'audit','policy_outcome':'not_reached','redaction_status':'not_reached',
            'detected_categories':[],'model_alias':None,'provider_called':False,'error_category':'invalid_event'}
        collector=CandidateTraceCollector();collector.emit(value)
        self.assertFalse(collector.invalid)
        collector.emit(value|{'failed_stage':'redaction','error_category':'input_too_large'})
        self.assertFalse(collector.invalid)
