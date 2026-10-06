#!/usr/bin/env python3
"""Canonical remote services for the isolated worker app; offline rendering only.

The worker app stays network-none. Authenticated operator port-forwards carry
only scoped chat/redactor requests. No cloud identity is installed on the worker.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def bundle(project,gateway,database,*,phase):
    if phase not in {'fixed_inputs_qualification','supervised_synthetic_free_text'}:
        raise ValueError
    spec=importlib.util.spec_from_file_location('base',ROOT/'scripts/render-synthetic-demo-bundle.py')
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    placeholder=f'us-east1-docker.pkg.dev/{project}/sdp-evaluation-images/agent-demo-application@sha256:'+('0'*64)
    value=copy.deepcopy(base.bundle(project,gateway,placeholder,database))
    remove={'catalog','application-network-preflight','google-agent-demo-application'}
    value['items']=[x for x in value['items'] if x['metadata']['name'] not in remove]
    for item in value['items']:
        if item['kind'] in {'Pod','Job'}:
            pod=item['spec']['template']['spec'] if item['kind']=='Job' else item['spec']
            for c in pod.get('initContainers',[])+pod.get('containers',[]):
                if c['image']==placeholder:c['image']=gateway
                for env in c.get('env',[]):
                    if env['name']=='PORTFOLIO_SYNTHETIC_LIVE_DEMO_ACK':
                        env['value']='I_ACKNOWLEDGE_ONE_FIXED_CURRENT_APPLICATION_QUALIFICATION' if phase=='fixed_inputs_qualification' else base.ACK
                if phase=='supervised_synthetic_free_text' and item['metadata']['name']=='redactor' and c['name']=='redactor':
                    c['env'].append({'name':'PORTFOLIO_SUPERVISED_TRIAL_ACK','value':'I_ACKNOWLEDGE_SUPERVISED_SYNTHETIC_FREE_TEXT_NOT_FIXED_QUALIFICATION'})
        if item['kind']=='NetworkPolicy':
            for direction in ['ingress','egress']:
                for rule in item['spec'].get(direction,[]):
                    field='from' if direction=='ingress' else 'to'
                    rule[field]=[x for x in rule.get(field,[]) if x.get('podSelector',{}).get('matchLabels',{}).get('app')!='catalog']
                    if field in rule and not rule[field]:
                        # Empty peer list means ALL peers. Remove the rule.
                        rule['_remove']=True
                item['spec'][direction]=[r for r in item['spec'].get(direction,[]) if not r.pop('_remove',False)]
    assert placeholder not in json.dumps(value)
    return value


def main():
    p=argparse.ArgumentParser()
    for name in ['project','gateway','database','phase']:p.add_argument('--'+name,required=True)
    p.add_argument('--validate',type=Path);args=p.parse_args()
    expected=bundle(args.project,args.gateway,args.database,phase=args.phase)
    if args.validate:
        actual=json.loads(args.validate.read_text())
        if actual!=expected:raise ValueError
        print('PASS: canonical worker service proposal; no native admission inferred')
    else:print(json.dumps(expected,indent=2))


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('worker_live_services:blocked') from None
