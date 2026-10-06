"""Constructed provisioning transport, never native issuance or model calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('scoped_bootstrap',ROOT/'scripts/bootstrap-synthetic-demo.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name)
        self.config={'master_key':'fixture-administrator-not-an-application-key','expires_at':time.time()+120}
    def tearDown(self):self.tmp.cleanup()
    def response(self,key):
        response=mock.MagicMock();response.__enter__.return_value=response
        response.status=200;response.read.return_value=json.dumps({'key':key}).encode()
        return response
    def test_probe_is_revoked_and_all_four_clients_are_distinct_and_scoped(self):
        opener=mock.Mock();opener.open.side_effect=[self.response('sk-probe'),self.response(None)]+[self.response('sk-fixture-'+str(n)) for n in range(4)]
        with mock.patch.object(bootstrap.urllib.request,'build_opener',return_value=opener):
            clients,counts=bootstrap.issue_clients(self.config,self.state)
        self.assertEqual(counts,{'client_issuance_attempts':5,'client_revocation_attempts':1})
        self.assertEqual(set(clients),{'alpha','beta'})
        requests=[call.args[0] for call in opener.open.call_args_list]
        self.assertTrue(requests[1].full_url.endswith('/key/delete'))
        self.assertEqual(json.loads(requests[1].data),{'keys':['sk-probe']})
        for request in requests[:1]+requests[2:]:
            body=json.loads(request.data)
            self.assertEqual(body['models'],['secure-financial-chat'])
            self.assertEqual(body['allowed_routes'],['/chat/completions'])
            self.assertEqual(body['max_parallel_requests'],1)
        self.assertEqual(len((self.state/'client-admissions.jsonl').read_text().splitlines()),6)
    def test_failed_issuance_is_retained_before_transport_and_not_retried(self):
        opener=mock.Mock();opener.open.side_effect=OSError('untrusted raw authentication error')
        with mock.patch.object(bootstrap.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(OSError):bootstrap.issue_clients(self.config,self.state)
        self.assertEqual(opener.open.call_count,1)
        self.assertEqual(json.loads((self.state/'client-admissions.jsonl').read_text()),{'client_issuance_attempts':1,'client_revocation_attempts':0})
    def test_admission_journal_failure_prevents_network_work(self):
        opener=mock.Mock();(self.state/'client-admissions.jsonl').mkdir()
        with mock.patch.object(bootstrap.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(OSError):bootstrap.issue_clients(self.config,self.state)
        opener.open.assert_not_called()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name)
        (self.state/'private-application-configurations.json').write_text('{}')
    def tearDown(self):self.tmp.cleanup()
    def test_acknowledged_handoff_removes_private_file(self):
        clock=[1000.0]
        def sleep(seconds):
            clock[0]+=seconds
            if clock[0]>=1003:(self.state/'handoff-acknowledged').touch()
        self.assertEqual(bootstrap.await_handoff(self.state,2000,now=lambda:clock[0],sleep=sleep),'ACKNOWLEDGED')
        self.assertFalse((self.state/'private-application-configurations.json').exists())
        self.assertLessEqual(clock[0],1003)
    def test_unacknowledged_handoff_fails_closed_within_bound(self):
        clock=[1000.0]
        def sleep(seconds):clock[0]+=seconds
        with self.assertRaisesRegex(ValueError,'handoff_unacknowledged'):
            bootstrap.await_handoff(self.state,5000,now=lambda:clock[0],sleep=sleep)
        self.assertEqual(clock[0],1000+bootstrap.HANDOFF_SECONDS)
        self.assertFalse((self.state/'private-application-configurations.json').exists())
    def test_hold_never_exceeds_admission_expiry(self):
        clock=[1000.0]
        def sleep(seconds):clock[0]+=seconds
        with self.assertRaises(ValueError):
            bootstrap.await_handoff(self.state,1010,now=lambda:clock[0],sleep=sleep)
        self.assertEqual(clock[0],1010)
