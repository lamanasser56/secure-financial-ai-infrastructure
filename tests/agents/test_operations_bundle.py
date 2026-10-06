import copy
import importlib.util
import json
import contextlib
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


class OperationsBundleTests(unittest.TestCase):
    def test_once_only_revoked_probe_then_catalog_client_admissions(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('bootstrap',root/'scripts/bootstrap-operations-reasoning.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'admission').mkdir();(base/'state').mkdir()
            (base/'admission/bootstrap.json').write_text(json.dumps({'owner_database_url':'unused',
                'gateway_password':'unused','master_key':'fixture-admin-only','expires_at':time.time()+800}))
            keys=['sk-'+('a'*48),'sk-'+('b'*48)]
            replies=[{'key':keys[0]},{'deleted_keys':[keys[0]]},{'key':keys[1]}]
            requests=[]
            class Response:
                status=200
                def __init__(self,value):self.value=value
                def __enter__(self):return self
                def __exit__(self,*_):pass
                def read(self,_):return json.dumps(self.value).encode()
            def opened(request,timeout):
                self.assertEqual(timeout,8);requests.append(request)
                return Response(replies[len(requests)-1])
            client=mock.Mock();client.open.side_effect=opened
            with mock.patch.object(module,'Path',side_effect=lambda p:base/str(p).lstrip('/')), \
                    mock.patch.object(module.urllib.request,'build_opener',return_value=client), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                module.run('--clients')
                with self.assertRaises(FileExistsError):module.run('--clients')
            self.assertEqual([r.full_url.rsplit('/',2)[-1] for r in requests],['generate','delete','generate'])
            self.assertEqual(json.loads(requests[1].data),{'keys':[keys[0]]})
            for request in (requests[0],requests[2]):
                value=json.loads(request.data)
                self.assertEqual(value['models'],['secure-financial-chat'])
                self.assertEqual(value['allowed_routes'],['/chat/completions'])
                self.assertEqual(value['max_parallel_requests'],1)
            self.assertEqual(json.loads((base/'state/gateway.json').read_text())['client_key'],keys[1])
            admissions=[json.loads(x) for x in (base/'state/client-admissions.jsonl').read_text().splitlines()]
            self.assertEqual(admissions[-1],{'client_issuance_attempts':2,'client_revocation_attempts':1,'model_attempts':0})
            self.assertNotIn(keys[0],output.getvalue());self.assertNotIn(keys[1],output.getvalue())

    def test_fresh_qualification_gate_rejects_changed_inputs_and_archive(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('gate',root/'scripts/verify-operations-image-qualification.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        record=json.loads((root/'evaluation/operations/restoration-qualification.json').read_text())
        expected=sum(len(gate.required_inputs(name)) for name in record['subjects'])
        self.assertEqual(gate.verify(record)['references'],expected)
        altered=copy.deepcopy(record);altered['subjects']['application']['source_inputs'].pop()
        with self.assertRaises(ValueError):gate.verify(altered)
        altered=copy.deepcopy(record);altered['subjects']['application']['archive_sha256'][1]='b'*64
        with self.assertRaises(ValueError):gate.verify(altered)
        altered=copy.deepcopy(record)
        row=next(x for x in altered['subjects']['application']['source_inputs'] if x[1]=='runtime/agents/operations.py')
        row[0]='0'*64
        with self.assertRaises(ValueError):gate.verify(altered)

    def test_complete_dedicated_render_and_mutation_rejection(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('renderer',root/'scripts/render-operations-reasoning-bundle.py')
        renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
        prefix='us-east1-docker.pkg.dev/portfolio-evaluation/sdp-evaluation-images/'
        images=[prefix+n+'@sha256:'+'a'*64 for n in ('agent-demo-gateway','agent-demo-application','agent-demo-database')]
        value=renderer.bundle('portfolio-evaluation',*images,'a'*40)
        self.assertFalse(any('redactor' in x['metadata']['name'] for x in value['items']))
        job=next(x for x in value['items'] if x['kind']=='Job' and x['metadata']['name']=='catalog')
        self.assertEqual(job['spec']['activeDeadlineSeconds'],120)
        self.assertEqual(job['spec']['backoffLimit'],0)
        container=job['spec']['template']['spec']['containers'][0]
        self.assertIn('/app/scripts/rehearse-operations-reasoning.py',container['args'])
        self.assertNotIn('-c',container['args'])
        for path,value2 in (('suspend',False),('backoffLimit',1),('activeDeadlineSeconds',900)):
            altered=copy.deepcopy(value);row=next(x for x in altered['items'] if x['kind']=='Job' and x['metadata']['name']=='catalog')
            row['spec'][path]=value2
            with self.assertRaises(ValueError):renderer.validate_document(altered,value)
        with self.assertRaises(ValueError):renderer.bundle('portfolio-evaluation',*images,'arbitrary')
