"""A complete mandatory case inventory, closed evidence and a cleanup circuit breaker."""
from dataclasses import dataclass
import datetime
import json
import math
import re

from attack_runtime import NotExercised, RestoreFailed

SECRET_PATTERNS = tuple(re.compile(p) for p in (
    r'sk-[A-Za-z0-9]{20,}', r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'ya29[.][0-9A-Za-z_-]{20,}',
    r'postgresql://[^:\s]+:[^@\s]{8,}@', r'[$]argon2id[$]v=19[$]m=', r'"password"\s*:\s*"[^"]+"'))


@dataclass
class Case:
    name: str
    kind: str
    run: object
    requires: tuple = ()
    always: bool = False


def safe_evidence(value, private=(), depth=0):
    if depth > 10:
        raise ValueError('evidence_depth')
    if type(value) is int and (str(value) in {str(p) for p in private if p} or abs(value)>=1_000_000_000):
        raise ValueError('sensitive_number')
    if value is None or type(value) in (bool,int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value,str):
        if (len(value)>300 or any(str(p) in value for p in private if p)
                or any(p.search(value) for p in SECRET_PATTERNS) or re.search(r'\b[0-9]{10,13}\b',value)):
            raise ValueError('sensitive_evidence')
        return value
    if type(value) is list and len(value)<=128:
        return [safe_evidence(v,private,depth+1) for v in value]
    if type(value) is dict and len(value)<=128 and all(type(k) is str for k in value):
        if any(type(v) is str and (k.lower() in ('password','token','capability','authorization','cookie','csrf')
                or k.lower().endswith(('_password','_private_key','_token','_secret','_key')))
                for k,v in value.items()):
            raise ValueError('credential_field')
        return {safe_evidence(k,private,depth+1):safe_evidence(v,private,depth+1) for k,v in value.items()}
    raise ValueError('evidence_shape')


DETAIL = re.compile(r'[a-z][a-z0-9_]{2,60}')


def detail(error):
    """The case's own closed reason (NotExercised('dns_or_target_failure')), or the exception type: never free text."""
    text = str(error) if isinstance(error, (NotExercised, RestoreFailed)) else ''
    if DETAIL.fullmatch(text):
        return text
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', type(error).__name__).lower()
    return name if DETAIL.fullmatch(name) else 'unspecified'


def nested_verdict(value, verdict='NOT_EXERCISED'):
    if isinstance(value,dict):
        return value.get('verdict')==verdict or any(nested_verdict(v,verdict) for v in value.values())
    return isinstance(value,list) and any(nested_verdict(v,verdict) for v in value)


def run(cases, *, private=(), emit=print):
    names=[c.name for c in cases]
    if not names or len(names)!=len(set(names)) or any(c.kind not in ('attack','control') or not re.fullmatch('[a-z][a-z0-9_]{2,80}',c.name) for c in cases):
        raise ValueError('case_inventory')
    rows=[]; seen={}; stopped=False
    for case in cases:
        at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        missing=[name for name in case.requires if seen.get(name)!='PASS']
        verdict,evidence='NOT_EXERCISED',{'reason':'DEPENDENCY_UNAVAILABLE','detail':'cleanup_failed_earlier' if stopped and not missing
                                          else ('requires_'+missing[0])[:61] if missing else 'unspecified'}
        if case.always or (not stopped and all(seen.get(name)=='PASS' for name in case.requires)):
            try:
                ok,evidence=case.run()
                if type(ok) is not bool or type(evidence) is not dict: raise ValueError('case_reply')
                evidence=safe_evidence(evidence,private)
                verdict='FAIL' if nested_verdict(evidence,'FAIL') else 'NOT_EXERCISED' if nested_verdict(evidence) else 'PASS' if ok else 'FAIL'
            except RestoreFailed as error:
                verdict,evidence='FAIL',{'reason':'CLEANUP_INCOMPLETE','detail':detail(error)}
                stopped=True
            except NotExercised as error:
                verdict,evidence='NOT_EXERCISED',{'reason':'CONTROL_UNAVAILABLE','detail':detail(error)}
            except KeyboardInterrupt as error:
                verdict,evidence='NOT_EXERCISED',{'reason':'INTERRUPTED','detail':detail(error)}
                stopped=True
            except (Exception,SystemExit) as error:
                verdict,evidence='NOT_EXERCISED',{'reason':'CASE_UNAVAILABLE','detail':detail(error)}
        row={'case':case.name,'kind':case.kind,'result':'PASS' if verdict=='PASS' else 'FAIL',
             'verdict':verdict,'at':at,'evidence':evidence}
        rows.append(row); seen[case.name]=verdict
        if case.always and verdict!='PASS': stopped=True
        emit(verdict+'  '+case.name)
    return rows
