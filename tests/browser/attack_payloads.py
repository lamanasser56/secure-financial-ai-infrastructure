"""Synthetic protocol examples generated from the real shared case inventory, never archived evidence."""
from copy import deepcopy
import json

from agent_platform import attack_results

at='2026-10-25T12:00:00+00:00'
release={'id':'a'*64,'source_commit':'b'*40,'images':['sha256:'+'c'*64]}
report={'schema_version':attack_results.VERSION,'suite':attack_results.SUITE,'run_id':'d'*32,
        'runner_commit':'e'*40,'release':release,'completed_at':at,'results':[
            {'case':name,'kind':meta[0],'verdict':'PASS','result':'PASS','at':at}
            for name,meta in attack_results.CASES.items()]}
payloads={'passed':attack_results.view(report,release)}
for name,verdict,evidence in (('failed','FAIL',{'reason':'CONTROL_UNAVAILABLE'}),
                              ('incomplete','NOT_EXERCISED',{'reason':'CONTROL_UNAVAILABLE','detail':'active_turn_not_established'})):
    changed=deepcopy(report)
    next(r for r in changed['results'] if r['kind']=='attack').update(verdict=verdict,result='FAIL',evidence=evidence)
    payloads[name]=attack_results.view(changed,release)
held=deepcopy(report)
next(r for r in held['results'] if r['case']=='financial_cross_user_api_and_forged_session')['evidence']={
    'forged_session_cookie':401,'insert_naming_other_user':400,'lama_sees_sara_rows':False}
payloads['facts']=attack_results.view(held,release)
different=deepcopy(release);different['images']=['sha256:'+'f'*64]
payloads['different']=attack_results.view(report,different)
payloads['unbound']=attack_results.view(dict(report,release=None),release)
payloads['historical']=attack_results.view({'suite':attack_results.SUITE,'completed_at':at,
    'results':[{'case':'retired_check','result':'PASS','at':at}]},release)
for name in ('missing','invalid','unavailable'):
    payloads[name]={'available':False,'status':name,'results':[],'file':'ConfigMap apps/attack-results'}
print(json.dumps(payloads))
