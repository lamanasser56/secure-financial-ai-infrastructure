"""Security-sensitive channel admission and trusted broker regressions."""
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import threading
import unittest
from unittest.mock import Mock, patch

from runtime.agents.control_channel import ControlClient, ControlServer, decode, encode, receive, send
from runtime.agents.isolation_controller import IsolationController
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure
from runtime.phase3.trusted_runtime import ControlFailure, RedactionResult


class ChannelTests(unittest.TestCase):
    def test_duplicate_invalid_utf8_and_byte_bounds(self):
        for raw in [b'{"key":1,"key":2}',b'{"key":NaN}',b'\xff']:
            with self.assertRaises(Exception):decode(raw)
        with self.assertRaises(ControlFailure):encode({'value':'x'*32768})

    def test_peer_token_sequence_and_closed_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'channel';token='1'*64;calls=[]
            def dispatch(operation,value):
                calls.append(operation)
                if operation=='budget':raise BudgetAdmissionFailure('subject_attempt_budget_exhausted')
                if operation=='unknown':raise ValueError('private must never escape')
                return {'observed':True}
            server=ControlServer(path,token,dispatch,lambda pid,uid,gid:uid==os.getuid())
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                client=ControlClient(path,token,controller_uid=os.getuid())
                self.assertTrue(client.call('monitor',{})['observed'])
                with self.assertRaises(BudgetAdmissionFailure):client.call('budget',{})
                with self.assertRaises(ControlFailure) as caught:client.call('unknown',{})
                self.assertNotIn('private',str(caught.exception))
                for supplied,sequence in [('2'*64,4),(token,3),(token,999)]:
                    with socket.socket(socket.AF_UNIX) as sock:
                        sock.connect(str(path));send(sock,{'schema_version':1,'token':supplied,'sequence':sequence,'operation':'monitor','value':{}})
                        self.assertEqual(receive(sock)['failure']['reason'],'denied')
                self.assertEqual(calls,['monitor','budget','unknown'])
                self.assertTrue(client.call('monitor',{})['observed'])
            finally:server.shutdown();thread.join();server.server_close()

    def test_foreign_peer_denied_even_with_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            server=ControlServer(Path(directory)/'channel','1'*64,Mock(),lambda *_:False)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                with self.assertRaises(ControlFailure):ControlClient(Path(directory)/'channel','1'*64,controller_uid=os.getuid()).call('monitor',{})
                server.dispatch.assert_not_called()
            finally:server.shutdown();thread.join();server.server_close()


class BrokerTests(unittest.TestCase):
    def broker(self):
        config={'subject':'local-fixture-alpha','gateway_url':'http://127.0.0.1:14012','client_keys':{'financial':'scoped'},'expires_at':time.time()+60}
        ledger=Mock();budget=Mock();operations=Mock()
        broker=IsolationController(config,{},budget,Mock(),Mock(),Mock(),operations,ledger)
        return broker

    def test_no_command_query_path_or_external_destination_operation(self):
        broker=self.broker()
        for operation in ['shell','query','http','credentials','register','read_file']:
            with self.assertRaises(ControlFailure):broker.dispatch(operation,{})
        broker.ledger.append.assert_not_called()

    def test_model_requires_one_consumed_reservation(self):
        broker=self.broker();permit=broker.dispatch('model_reserve',{'subject':'local-fixture-alpha'})
        with self.assertRaises(ControlFailure):broker.dispatch('model_reserve',{'subject':'local-fixture-alpha'})
        with self.assertRaises(ControlFailure):broker.dispatch('model',{'permit':permit,'authorization':'Bearer admin','body':{}})
        self.assertIsNone(broker.permit);self.assertEqual(broker.http_attempts,0)
        with self.assertRaises(ControlFailure):broker.dispatch('model',{'permit':permit,'authorization':'Bearer scoped','body':{}})

    def test_audit_failure_latches_mutations_but_keeps_monitoring(self):
        broker=self.broker();broker.ledger._check_files.side_effect=ControlFailure('audit','invalid_event')
        with self.assertRaises(ControlFailure):broker.dispatch('model_reserve',{'subject':'local-fixture-alpha'})
        self.assertTrue(broker.poisoned);self.assertTrue(broker.operations.controller.poisoned)
        broker.operations.handle.return_value={'observed':'SERVICE_FAILED'}
        self.assertEqual(broker.dispatch('operations',{'operation':'observe','target_id':'test-gateway'})['observed'],'SERVICE_FAILED')

    def test_unredacted_model_prompt_never_reaches_transport(self):
        broker=self.broker();permit=broker.dispatch('model_reserve',{'subject':'local-fixture-alpha'})
        system='Return only the canonical JSON envelope: summary is the JSON decision string; classification is informational or action_required. Follow the provided tool schemas.'
        body={'model':'secure-financial-chat','messages':[{'role':'system','content':system},{'role':'user','content':'unredacted'}],
              'response_format':{'type':'json_object'},'max_tokens':1024,'stream':False,'temperature':0,'metadata':{}}
        with self.assertRaises(ControlFailure) as caught:broker.dispatch('model',{'permit':permit,'authorization':'Bearer scoped','body':body})
        self.assertEqual(caught.exception.stage,'redaction');self.assertEqual(broker.http_attempts,0)

    def test_runtime_model_suffix_and_redacted_prompt_reach_only_pinned_route(self):
        broker=self.broker();broker.redactor.redact.return_value=RedactionResult('safe',())
        broker.dispatch('redact',{'text':'original'})
        permit=broker.dispatch('model_reserve',{'subject':'local-fixture-alpha'})
        system='Return only the canonical JSON envelope: summary is the JSON decision string; classification is informational or action_required. Follow the provided tool schemas.'
        body={'model':'secure-financial-chat','messages':[{'role':'system','content':system},{'role':'user','content':'safe'}],
              'response_format':{'type':'json_object'},'max_tokens':1024,'stream':False,'temperature':0,
              'metadata':{'correlation_id':'12345678-1234-1234-1234-123456789012:model:1','tenant_ref':'a'*16}}
        with patch('runtime.agents.isolation_controller._post_json',return_value={'accepted':True}) as transport:
            self.assertTrue(broker.dispatch('model',{'permit':permit,'authorization':'Bearer scoped','body':body})['accepted'])
            self.assertEqual(transport.call_args.args[0],'http://127.0.0.1:14012/chat/completions')
        self.assertEqual((broker.http_attempts,broker.http_responses),(1,1))


class FixedScopeTests(unittest.TestCase):
    def test_live_scope_does_not_admit_legacy_infrastructure_chat(self):
        from runtime.agents.isolated_application import FinancialConversations
        from runtime.agents.conversations import ConversationRejected
        delegate=Mock();gate=FinancialConversations(delegate)
        for method in [gate.turn,gate.reset]:
            with self.assertRaises(ConversationRejected):method('session',{'agent':'infrastructure'})
        delegate.turn.assert_not_called();delegate.reset.assert_not_called()
        gate.turn('session',{'agent':'financial','question':'own wording'})
        gate.reset('session',{'agent':'financial'})
        self.assertEqual(delegate.turn.call_count,1);self.assertEqual(delegate.reset.call_count,1)

    def test_fixed_scope_consumes_failed_question_and_never_opens_free_text(self):
        from runtime.agents.isolated_application import FixedConversations
        from runtime.agents.conversations import ConversationRejected
        delegate=Mock();delegate.turn.side_effect=ValueError('failed once')
        gate=FixedConversations(delegate)
        with self.assertRaises(ConversationRejected):gate.turn('session',{'agent':'financial','language':'en','question':'different wording'})
        first={'agent':'financial','language':'en','question':gate.questions[0][1]}
        with self.assertRaises(ValueError):gate.turn('session',first)
        with self.assertRaises(ConversationRejected):gate.turn('session',first)
        with self.assertRaises(ConversationRejected):gate.reset('session',{})
        self.assertEqual(delegate.turn.call_count,1)

    def test_fixed_ledger_has_smaller_shared_caps_without_budget_renewal(self):
        from runtime.agents.trial_composition import TrialLedger,DurableModelBudget
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).chmod(0o700)
            ledger=TrialLedger(Path(tmp),scope='fixed_inputs_qualification');ledger.expires=time.time()+60
            budget=DurableModelBudget(ledger)
            for _ in range(8):budget.reserve('local-fixture-alpha')
            with self.assertRaises(BudgetAdmissionFailure):budget.reserve('local-fixture-alpha')
            self.assertEqual(budget.snapshot('local-fixture-alpha')['subject_used'],8)
            ledger.close()


if __name__=='__main__' :unittest.main()
