import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from runtime.agents.operations import OperationsAudit, OperationsController
from runtime.agents.operations_local import fixture_identity, sandbox_targets, ProcVisibility
from runtime.agents.operations_service import OperationsService
from runtime.agents.web import DemoServer


class OperationsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.root.chmod(0o700)
        (self.root/'audit').mkdir(mode=0o700);self.audit=OperationsAudit(self.root/'audit')
        identity,auth,tenant=fixture_identity();targets,self.child=sandbox_targets(self.root,tenant)
        controller=OperationsController(self.audit,identity,auth,targets,
            approval_secret='local-human-confirmation',visibility=ProcVisibility())
        self.server=DemoServer(('127.0.0.1',0),operations=OperationsService(controller))
        self.origin=self.server.origin
        self.client=urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _, body = self.round_trip(self.origin+'/api/bootstrap')
        self.csrf=json.loads(body)['csrf']

    def tearDown(self):
        self.server.server_close();self.audit.close()
        if self.child.poll() is None:self.child.terminate()
        self.child.wait(timeout=3);self.temp.cleanup()

    def round_trip(self,request):
        outcomes=[]
        def client():
            try:
                with self.client.open(request,timeout=10) as response:outcomes.append((response.status,response.read()))
            except urllib.error.HTTPError as error:outcomes.append((error.code,error.read()))
        thread=threading.Thread(target=client);thread.start()
        # The actual server runs on its main thread: existing deadline controls
        # must remain available to the financial runtime.
        self.server.handle_request();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertEqual(len(outcomes),1)
        return outcomes[0]

    def post(self,body,path='/api/operations',csrf=None):
        request=urllib.request.Request(self.origin+path,data=json.dumps(body).encode(),
            headers={'Origin':self.origin,'Content-Type':'application/json','X-Demo-CSRF':self.csrf if csrf is None else csrf})
        status,body=self.round_trip(request)
        return status,json.loads(body)

    def test_actual_http_workflow_and_financial_agent_preserved(self):
        for asset in ('/operations.html','/operations.js','/style.css'):
            status,_=self.round_trip(self.origin+asset);self.assertEqual(status,200)
        status,value=self.post({'operation':'overview'});self.assertEqual(status,200)
        self.assertEqual(len(value['targets']),2)
        _,observed=self.post({'operation':'observe','target_id':'sandbox-demo'})
        _,proposal=self.post({'operation':'propose','target_id':'sandbox-demo','action':'recover','evidence_id':observed['evidence_id']})
        status,_=self.post({'operation':'approve','request_id':proposal['request_id'],'operator_secret':'forged'})
        self.assertEqual(status,403)
        _,approval=self.post({'operation':'approve','request_id':proposal['request_id'],'operator_secret':'local-human-confirmation'})
        _,result=self.post({'operation':'execute','request_id':proposal['request_id'],'approval_id':approval['approval_id']})
        self.assertEqual(result['status'],'VERIFIED')
        status,frame=self.post({'agent':'financial','language':'ar','question':'ما إجمالي مصاريفي في يناير 2026؟',
            'evidence_source':None,'conversation_id':None},path='/api/conversation')
        self.assertEqual(status,200);self.assertEqual(frame['report']['status'],'completed')
        self.assertEqual(frame['report']['facts'][0]['result']['total_minor_units'],24000)

    def test_csrf_selectors_security_and_rtl_ltr(self):
        status,_=self.post({'operation':'overview'},csrf='wrong');self.assertEqual(status,403)
        status,_=self.post({'operation':'observe','target_id':'sandbox-demo','command':'shell'});self.assertEqual(status,403)
        _,value=self.post({'operation':'security'});self.assertFalse(value['allow_decision'])
        _,body=self.round_trip(self.origin+'/operations.js');script=body.decode()
        self.assertIn("lang === 'ar' ? 'rtl' : 'ltr'",script)
        self.assertIn('الموافقة على المقترح',script)
        self.assertNotIn('innerHTML',script)
