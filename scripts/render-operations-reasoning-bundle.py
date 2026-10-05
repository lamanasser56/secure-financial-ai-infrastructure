#!/usr/bin/env python3
"""Dedicated canonical three-fact bundle; never applies or admits external calls."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def bundle(project, gateway, application, database, source):
    if not re.fullmatch('[a-f0-9]{40}',source):
        raise ValueError
    spec=importlib.util.spec_from_file_location('previous',ROOT/'scripts/render-synthetic-demo-bundle.py')
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    value=previous.bundle(project,gateway,application,database)
    items=[]
    for item in value['items']:
        name=item['metadata']['name']
        if 'redactor' in name:
            continue
        if item['kind']=='ConfigMap':
            item['data']={k:v for k,v in item['data'].items() if k in {'litellm-schema.sql','litellm-vertex.yaml'}}
            item['data']['litellm-vertex.yaml']=item['data']['litellm-vertex.yaml'].replace('max_tokens: 1024','max_tokens: 256')
        if item['kind']=='NetworkPolicy':
            policy=item['spec']
            policy['egress']=[r for r in policy.get('egress',[]) if all(x.get('podSelector',{}).get('matchLabels',{}).get('app')!='redactor' for x in r.get('to',[]))]
            if name=='catalog':
                policy['egress']=[r for r in policy['egress'] if all(x.get('podSelector',{}).get('matchLabels',{}).get('app')!='database' for x in r.get('to',[]))]
        if item['kind']=='Job' and name in {'bootstrap-database','bootstrap-clients'}:
            container=item['spec']['template']['spec']['containers'][0]
            container['args'][1]=previous.code('bootstrap-operations-reasoning.py')
            item['spec']['template']['metadata']['annotations']['portfolio.example/program-sha256']=hashlib.sha256(container['args'][1].encode()).hexdigest()
        if item['kind']=='Job' and name=='gateway-network-preflight':
            item['spec']['template']['spec']['containers'][0]['image']=gateway
        if item['kind']=='Job' and name=='catalog':
            pod=item['spec']['template']['spec'];container=pod['containers'][0]
            container['args']=['/app/scripts/rehearse-operations-reasoning.py','--live','--source',source,
                '--state','/state/run','--admission','/admission/run.json','--gateway-config','/admission/gateway.json']
            container['env']=[{'name':'PORTFOLIO_OPERATIONS_SYNTHETIC_ACK','value':'I_ACKNOWLEDGE_THREE_FIXED_SYNTHETIC_OPERATIONS_REQUESTS'}]
            item['spec']['activeDeadlineSeconds']=120;pod['activeDeadlineSeconds']=120
            item['spec']['template']['metadata']['annotations']={'portfolio.example/source':source,
                'portfolio.example/catalog-sha256':hashlib.sha256((ROOT/'evaluation/operations/synthetic-reasoning.json').read_bytes()).hexdigest()}
        items.append(item)
    return value | {'items':items}


def validate_document(actual, expected):
    if actual != expected:
        raise ValueError('operations_bundle:noncanonical_objects')


def main():
    p=argparse.ArgumentParser()
    for name in ('project','gateway','application','database','source'):p.add_argument('--'+name,required=True)
    p.add_argument('--validate',type=Path);a=p.parse_args()
    expected=bundle(a.project,a.gateway,a.application,a.database,a.source)
    if a.validate:
        if a.validate.is_symlink() or not a.validate.is_file() or a.validate.stat().st_size>262144:
            raise ValueError
        def unique(pairs):
            result={}
            for k,v in pairs:
                if k in result:raise ValueError
                result[k]=v
            return result
        actual=json.loads(a.validate.read_text(),object_pairs_hook=unique)
        validate_document(actual,expected)
        print('{"canonical":true,"model_attempt_limit":3,"actions":0,"sdp_attempts":0}')
    else:
        print(json.dumps(expected,indent=2))

if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('operations_bundle:noncanonical; execution blocked') from None
