#!/usr/bin/env python3
"""Once-only fixed current-app qualification. No free-text admission or rerun.

Talks only to the already admitted loopback UI. The operator capability remains
private; every controlled fault/restoration still passes code policy/approval.
All model/redaction requests use the application's existing enforced route.
"""
import argparse
import hashlib
import http.cookiejar
import json
import os
import sqlite3
from pathlib import Path
import time
import urllib.error
import urllib.request

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime.agents.isolated_application import FixedConversations
from runtime.agents.service_restoration import private_file
from runtime.agents.operations import private_directory


def run(state,port):
    state=private_directory(state)
    configuration=json.loads(private_file(state/'effective-admitted-configuration.json'))
    # Local source-overlay rehearsals cannot issue this live receipt.
    runtime=json.loads(private_file(state/'isolation-runtime.json'))
    if runtime['source_overlay_for_isolated_test'] or not configuration.get('live_enabled'):
        raise ValueError
    marker=state/'current-fixed-qualification-started'
    fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    os.fsync(fd);os.close(fd)
    origin=f'http://127.0.0.1:{port}'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with client.open(origin+'/api/bootstrap',timeout=2) as response:bootstrap=json.load(response)
    if bootstrap['admission_scope']!='fixed_inputs_qualification' or bootstrap['mode']!='gateway':raise ValueError
    csrf=bootstrap['csrf'];started=time.monotonic();checks={};usage=[]
    def post(value,path='/api/operations'):
        if time.monotonic()-started>=600:raise ValueError
        request=urllib.request.Request(origin+path,data=json.dumps(value).encode(),headers={
            'Content-Type':'application/json','Origin':origin,'X-Demo-CSRF':csrf})
        try:
            with client.open(request,timeout=30) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:return response.code,json.load(response)
    def op(name,**fields):
        status,value=post({'operation':name}|fields)
        if status!=200:raise ValueError
        return value
    def action(name):
        evidence=op('observe',target_id='test-gateway')
        diagnosis=op('diagnose',target_id='test-gateway',evidence_id=evidence['evidence_id'])
        if diagnosis['permitted_action']!=name:raise ValueError
        proposal=op('propose',target_id='test-gateway',action=name,evidence_id=evidence['evidence_id'])
        approval=op('approve',request_id=proposal['request_id'],operator_secret=private_file(state/'operator-approval.secret').decode().strip())
        outcome=op('execute',request_id=proposal['request_id'],approval_id=approval['approval_id'])
        if outcome['status']!='VERIFIED':raise ValueError
        return outcome
    conversation=None;seal={p.name:hashlib.sha256(private_file(p)).hexdigest() for p in [state/'operator.json',state/'effective-admitted-configuration.json',state/'gateway-config.yaml']}
    for index,(language,question) in enumerate(FixedConversations.questions):
        status,value=post({'agent':'financial','language':language,'question':question,'evidence_source':None,'conversation_id':conversation},'/api/conversation')
        report=value.get('report',{});facts=report.get('facts',[])
        if (status!=200 or report.get('status')!='completed' or report.get('model_requests')!=3
                or report.get('tool_executions')!=2 or len(facts)!=2
                or facts[0]['result']['total_minor_units']!=24000
                or any(x['result']['period']!='2026-01' or x['result']['source_id']!='synthetic-expenses-v1' for x in facts)
                or report['presentation']['usage']['external_provider_calls']!=3):raise ValueError
        conversation=value['conversation_id'];usage.append(report['presentation']['usage'])
        checks['financial_'+language+'_grounded']=True
        if index==0:
            if post({'operation':'observe','target_id':'user-stack'})[0]!=403:raise ValueError
            evidence=op('observe',target_id='test-gateway')
            proposal=op('propose',target_id='test-gateway',action='test_failure',evidence_id=evidence['evidence_id'])
            if post({'operation':'approve','request_id':proposal['request_id'],'operator_secret':'forged'})[0]!=403:raise ValueError
            checks['denials_verified']=True
            action('test_failure')
            if op('observe',target_id='test-gateway')['observed']!='SERVICE_FAILED':raise ValueError
            explanation=op('explain',target_id='test-gateway')
            if explanation['code']!='OK' or explanation['action_authority'] is not False:raise ValueError
            recovered=action('restore')
            if recovered['verification']['health_verified'] is not True:raise ValueError
            if op('explain',target_id='test-gateway')['code']!='OK':raise ValueError
            checks['owned_restoration_verified']=True
    if seal!={name:hashlib.sha256(private_file(state/name)).hexdigest() for name in seal}:raise ValueError
    checks['credentials_budgets_unchanged']=True
    with sqlite3.connect('file:'+str(state/'audit-live-turns/tool-audit.sqlite')+'?mode=ro',uri=True) as db:
        terminals=[json.loads(row[0]) for row in db.execute('SELECT event FROM events')]
    if len(terminals)!=2 or any(row.get('outcome')!='completed' or row.get('model_provider')!='vertex_gemini' for row in terminals):raise ValueError
    with sqlite3.connect('file:'+str(state/'trial-reservations/tool-audit.sqlite')+'?mode=ro',uri=True) as db:
        reservations=[json.loads(row[0]) for row in db.execute('SELECT event FROM events')]
    if sum(row['kind']=='model' for row in reservations)!=8 or sum(row['kind']=='tool' for row in reservations)!=4:raise ValueError
    result={'status':'PASS','scope':'fixed_inputs_qualification','all_required_tools_grounded':True,
        'actual_model_responses':True,'audit_preserved':True,**checks,'financial_usage':usage,
        'durable_terminal_events':2,'shared_model_reservations':8,'shared_tool_reservations':4,
        'source':configuration['admitted_source'],'automatic_free_text_admission':False,
        'provider_receipts':'SDK/HTTP attempts; not reconciled billing'}
    (state/'current-fixed-integration.json').write_text(json.dumps(result,sort_keys=True)+'\n')
    print(json.dumps({'status':'PASS','scope':result['scope'],'checks':checks,'free_text_admitted':False}))


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,required=True);parser.add_argument('--port',type=int,default=8771)
    args=parser.parse_args()
    try:run(args.state,args.port)
    except Exception:raise SystemExit('current_live_qualification:FAILED; no automatic rerun') from None
