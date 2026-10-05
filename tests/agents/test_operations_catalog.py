import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from runtime.agents.operations_catalog import ACK, CATALOG, cases, run, validate_answer


class CatalogTests(unittest.TestCase):
    def configuration(self):
        return {'gateway_url': 'http://gateway.google-agent-demo.svc.cluster.local:4000',
            'client_key': 'sk-' + 'a' * 48, 'expires_at': time.time() + 600,
            'model_alias': 'secure-financial-chat', 'route': 'vertex_ai/gemini-2.5-flash@us-east1'}

    def admission(self):
        return {'source': 'a'*40, 'catalog_integrity': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
            'owner_approved': True, 'fixed_nonpersonal_boundary_accepted': True,
            'processor_location_reviewed': True, 'native_provenance_and_network_passed': True,
            'fixture_identity_scope_accepted': True, 'requests': 3, 'retries': 0}

    def test_offline_fixed_catalog_and_exclusive_state(self):
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp)/'run'
            result=run(state=state,source='a'*40)
            self.assertEqual(result['model_attempts'],0)
            self.assertEqual(len(result['results']),3)
            with self.assertRaises(FileExistsError):run(state=state,source='a'*40)

    def test_admission_route_arbitrary_output_and_no_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp)/'run'
            with self.assertRaises(ValueError):
                run(state=state,source='a'*40,config=self.configuration(),admission=self.admission())
            self.assertFalse(state.exists())
            def failing(*args,**kwargs):raise OSError('secret raw provider message')
            result=run(state=state,source='a'*40,config=self.configuration(),admission=self.admission(),
                       acknowledgement=ACK,transport=failing)
            self.assertEqual(result['model_attempts'],1);self.assertEqual(len(result['results']),1)
            self.assertNotIn('secret',json.dumps(result))
            self.assertEqual(result['actions'],0)
        with self.assertRaises(ValueError):validate_answer({'shell':'anything'},cases()[0])

    def test_three_constructed_protocol_responses_and_audit_failure(self):
        responses=[]
        for case in cases():
            answer={'observed':case['observed'],'recommendation':case['admitted_recommendation'],
                    'cause':'UNKNOWN' if case['unknowns'] else 'NOT_ESTABLISHED'}
            responses.append({'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(answer)},'finish_reason':'stop'}]})
        with tempfile.TemporaryDirectory() as temp:
            result=run(state=Path(temp)/'run',source='a'*40,config=self.configuration(),admission=self.admission(),
                acknowledgement=ACK,transport=lambda *a,**k:responses.pop(0))
            self.assertEqual(result['model_attempts'],3)
            self.assertTrue(all(x['status']=='PASS' for x in result['results']))
        with tempfile.TemporaryDirectory() as temp:
            calls=[]
            # Marker can commit, but a subsequent admission failure blocks HTTP.
            real_open=Path.open
            def opened(path,*a,**k):
                if path.name=='audit.jsonl':raise OSError('private failure')
                return real_open(path,*a,**k)
            with mock.patch.object(Path,'open',opened):
                result=run(state=Path(temp)/'run',source='a'*40,config=self.configuration(),admission=self.admission(),
                    acknowledgement=ACK,transport=lambda *a,**k:calls.append(1))
            self.assertEqual(calls,[]);self.assertEqual(result['model_attempts'],0)
