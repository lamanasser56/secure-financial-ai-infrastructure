#!/usr/bin/env python3
"""Exact current local image inputs. No registry/signature or live admission claim."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def required_inputs(service):
    common={'docker/agent-composition/Dockerfile','docker/agent-composition/Dockerfile.dockerignore',
            'evaluation/agent-composition/generated-inputs.json','requirements-agent-composition.txt','requirements-litellm-candidate.txt'}
    if service=='gateway':return common|{'scripts/local-agent-proxy.py'}
    copied={p.relative_to(ROOT).as_posix() for directory in ['runtime','contracts','demo']
            for p in (ROOT/directory).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='.env'}
    return common|copied|{'scripts/serve-integrated-agents.py','scripts/run-local-operations.py',
            'scripts/inspect-operations-active-path.py','scripts/evaluate-container-vulnerability-policy.py',
            'scripts/rehearse-operations-reasoning.py','evaluation/operations/synthetic-reasoning.json'}


def verify(record):
    if record['scope'] != 'fresh_local_security_operations_service_images' or record['external_model_calls'] != 0 or record['sdp_attempts'] != 0 or record['registry_manifests'] is not None or record['signatures'] is not None:
        raise ValueError
    if set(record['subjects']) != {'gateway','application'} or record['zero_exception_policy'] is not True:
        raise ValueError
    count=0
    for name,subject in record['subjects'].items():
        paths=[p for _,p in subject['source_inputs']]
        if len(paths)!=len(set(paths)) or set(paths)!=required_inputs(name):raise ValueError
        archives=subject['archive_sha256']
        if (len(archives)!=2 or archives[0]!=archives[1] or not re.fullmatch('[a-f0-9]{64}',archives[0])
                or not re.fullmatch('sha256:[a-f0-9]{64}',subject['configuration_id'])
                or subject['reproducible'] is not True or subject['secret_scan_exit']!=0
                or subject['high_critical_gate'] is not True
                or any(subject['vulnerabilities'].get(k,0)!=0 for k in ('HIGH','CRITICAL'))
                or subject['policy']['allowed'] is not True
                or subject['policy']['subject']!='local-docker-archive-'+name+'@sha256:'+archives[0]):
            raise ValueError
        for expected,name in subject['source_inputs']:
            relative=Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError
            path=ROOT/relative
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError
            count+=1
    return {'local_image_inputs':'PASS','references':count,'registry_verified':False,'live_admitted':False}


if __name__=='__main__':
    try:
        print(json.dumps(verify(json.loads((ROOT/'evaluation/operations/restoration-qualification.json').read_text()))))
    except Exception:
        raise SystemExit('operations_qualification:changed_or_invalid; fresh qualification required') from None
