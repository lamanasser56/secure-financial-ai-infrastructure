"""Actual isolated process restoration; gateway/PG acceptance runs on worker."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from runtime.agents.operations import OperationsAudit, OperationsBlocked, OperationsController, ServiceTarget, process_identity
from runtime.agents.operations_local import fixture_identity
from runtime.agents.service_restoration import OwnedServiceAdapter
from runtime.phase3.trusted_runtime import ControlFailure

ROOT=Path(__file__).resolve().parents[2]


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name);self.state.chmod(0o700)
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.write('operator.json',{'stub_key':'local-test-only','admin_key':'local-test-admin'})
        for u in ['alpha','beta']:self.write('application-'+u+'.json',{'expires_at':time.time()+900})
        self.write('gateway-config.yaml',{})
        self.write('stub-launch.json',{'argv':[sys.executable,str(ROOT/'scripts/local-agent-upstream.py'),'--state',str(self.state),'--port',str(self.port)],'cwd':str(ROOT),'environment':dict(os.environ)})
        (self.state/'service-control.lock').touch(mode=0o600)
        self.guard=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],stdin=subprocess.DEVNULL)
        self.stub=subprocess.Popen([sys.executable,str(ROOT/'scripts/local-agent-upstream.py'),'--state',str(self.state),'--port',str(self.port)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.1):break
            except OSError:time.sleep(.01)
        else:self.fail('isolated stub not ready')
        self.write('processes.json',[{'pid':p.pid,'start_ticks':process_identity(p.pid)['start_ticks'],'name':name} for p,name in [(self.stub,'stub'),(self.guard,'database-guard')]])
        self.adapter=OwnedServiceAdapter(self.state,'stub',python=sys.executable,port=self.port,database_check=lambda:True)
        audit=self.state/'audit';audit.mkdir(mode=0o700);self.audit=OperationsAudit(audit)
        identity,auth,tenant=fixture_identity();self.controller=OperationsController(self.audit,identity,auth,{'owned-service':ServiceTarget(tenant,self.adapter)},approval_secret='test-operator-only')

    def write(self,name,value):
        p=self.state/name;p.write_text(json.dumps(value)+'\n');p.chmod(0o600)

    def tearDown(self):
        for p in [self.adapter.child,self.stub,self.guard]:
            if p is not None:
                if p.poll() is None:p.terminate()
                p.wait(timeout=3)
        self.audit.close();self.tmp.cleanup()

    def approved(self,action):
        o=self.controller.observe('owned-service')
        d=self.controller.diagnose('owned-service',o['evidence_id']);self.assertEqual(d['permitted_action'],action)
        p=self.controller.propose('owned-service',action,o['evidence_id'])
        a=self.controller.approve(p['request_id'],'test-operator-only')
        return p['request_id'],a['approval_id']

    def fail_service(self):
        r=self.controller.execute(*self.approved('test_failure'));self.assertEqual(r['status'],'VERIFIED');self.stub.wait(timeout=3)

    def test_actual_service_restored_with_verified_listener_same_credentials_and_expiry(self):
        original=dict(self.adapter.sealed);expiry=self.adapter.expires
        self.fail_service();r=self.controller.execute(*self.approved('restore'))
        self.assertEqual(r['status'],'VERIFIED');self.assertTrue(r['verification']['health_verified'])
        self.assertEqual(self.adapter.sealed,original);self.assertEqual(self.adapter.expires,expiry)
        self.assertEqual(self.controller.observe('owned-service')['observed'],'SERVICE_HEALTHY')
        self.assertEqual(self.audit._db.execute("SELECT COUNT(*) FROM events").fetchone()[0],13)

    def test_forged_approval_and_foreign_target_denied(self):
        request,_=self.approved('test_failure')
        with self.assertRaises(OperationsBlocked):self.controller.execute(request,'forged')
        with self.assertRaises(OperationsBlocked):self.controller.observe('foreign-service')
        self.assertIsNone(self.stub.poll())

    def test_consumed_start_cannot_replay_or_restore_healthy_service(self):
        self.fail_service();request,approval=self.approved('restore');self.controller.execute(request,approval)
        with self.assertRaises(OperationsBlocked):self.controller.execute(request,approval)
        observed=self.controller.observe('owned-service')
        with self.assertRaises(OperationsBlocked):self.controller.propose('owned-service','restore',observed['evidence_id'])

    def test_failed_real_start_truthfully_records_failure_and_consumes_attempt(self):
        self.fail_service();self.write('stub-count.json',{'stub_requests':257})
        r=self.controller.execute(*self.approved('restore'))
        self.assertEqual((r['status'],r['code']),('FAILED','ACTION_FAILED'))
        self.assertEqual(r['verification']['restore_attempts'],1)
        self.assertFalse(r['verification']['health_verified'])
        self.assertIsNone(self.controller.observe('owned-service')['facts']['permitted_action'])
        outcomes=[json.loads(row[0]) for row in self.audit._db.execute('SELECT event FROM events') if json.loads(row[0])['phase']=='outcome']
        self.assertEqual(outcomes[-1]['code'],'ACTION_FAILED')

    def test_audit_failure_prevents_start_and_monitoring_survives(self):
        self.fail_service();request,approval=self.approved('restore');path=self.state/'audit/tool-audit.sqlite';path.chmod(0o400)
        try:
            with self.assertRaises(OperationsBlocked) as e:self.controller.execute(request,approval)
            self.assertEqual(e.exception.code,'AUDIT_FAILED');self.assertIsNone(self.adapter.child)
            r=self.controller.observe('owned-service');self.assertEqual(r['observed'],'SERVICE_FAILED');self.assertFalse(r['audit_committed'])
        finally:path.chmod(0o600)

    def test_changed_credentials_dependencies_and_expiry_deny_renewal(self):
        self.fail_service();self.adapter.database_check=lambda:False
        self.assertIsNone(self.controller.observe('owned-service')['facts']['permitted_action'])
        self.adapter.database_check=lambda:True;self.adapter.expires=0
        self.assertIsNone(self.controller.observe('owned-service')['facts']['permitted_action'])
        self.write('operator.json',{'admin_key':'changed','stub_key':'changed'})
        with self.assertRaises(OperationsBlocked):self.controller.observe('owned-service')

    def test_quarantine_cannot_be_overridden_by_healthy_database(self):
        self.fail_service();self.write('database-quarantined.json',{'code':'DATABASE_UNAVAILABLE_PROXY_QUARANTINED'})
        self.assertIsNone(self.controller.observe('owned-service')['facts']['permitted_action'])

    def test_existing_stack_is_not_adopted_by_another_supervisor(self):
        with self.assertRaises(OperationsBlocked):OwnedServiceAdapter(self.state,'stub',python=sys.executable,port=self.port,database_check=lambda:True,supervisor=process_identity(self.guard.pid))

    def test_model_reservation_audit_failure_latches_mutations_but_not_monitoring(self):
        class FailedAccounting:
            broken=False
            def __call__(self,_):
                self.broken=True
                raise ControlFailure('audit','invalid_event')
            def budgets(self):
                if self.broken:raise ControlFailure('audit','invalid_event')
                return {'available':True}
        self.controller.model=FailedAccounting()
        response=self.controller.explain('owned-service')
        self.assertEqual(response['code'],'AUDIT_FAILED')
        observed=self.controller.observe('owned-service')
        self.assertEqual(observed['observed'],'SERVICE_HEALTHY')
        self.assertFalse(observed['audit_committed'])
        self.assertEqual(observed['budgets']['model_limits']['code'],'REQUIRED_MODEL_ACCOUNTING_UNAVAILABLE')
        with self.assertRaises(OperationsBlocked) as failure:self.controller.propose('owned-service','test_failure',observed['evidence_id'])
        self.assertEqual(failure.exception.code,'AUDIT_FAILED')
        self.assertIsNone(self.stub.poll())

    def test_shared_accounting_failure_after_approval_blocks_immediate_mutation(self):
        class Accounting:
            broken=False
            def budgets(self):
                if self.broken:raise ControlFailure('audit','invalid_event')
                return {'available':True}
        accounting=Accounting();self.controller.model=accounting
        request,approval=self.approved('test_failure');accounting.broken=True
        with self.assertRaises(OperationsBlocked) as failure:self.controller.execute(request,approval)
        self.assertEqual(failure.exception.code,'AUDIT_FAILED')
        self.assertIsNone(self.stub.poll())
        self.assertFalse((self.state/'fault-stub.json').exists())
        self.assertEqual(self.controller.observe('owned-service')['observed'],'SERVICE_HEALTHY')


class HealthDeadlineTests(unittest.TestCase):
    def test_thirty_two_checks_use_existing_twenty_second_deadline_without_retry(self):
        from unittest import mock
        for ready_at,successful in [(19,True),(21,False)]:
            with self.subTest(ready_at=ready_at):
                clock=[0.0];adapter=OwnedServiceAdapter.__new__(OwnedServiceAdapter)
                adapter.last={};adapter._owned=mock.Mock(return_value={'pid':1})
                adapter._health=mock.Mock(side_effect=lambda _:clock[0]>=ready_at)
                adapter._dependencies=mock.Mock(return_value=True)
                def sleep(seconds):clock[0]+=seconds
                with mock.patch('runtime.agents.service_restoration.time.monotonic',side_effect=lambda:clock[0]),mock.patch('runtime.agents.service_restoration.time.sleep',side_effect=sleep):
                    if successful:adapter._wait_for_outcome('restore',20)
                    else:
                        with self.assertRaises(OperationsBlocked):adapter._wait_for_outcome('restore',20)
                self.assertEqual(adapter.last['health_verified'],successful)
                self.assertLessEqual(adapter._health.call_count,32)
                self.assertLess(clock[0],20)
