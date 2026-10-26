"""Current API projections and a synthetic worker report for browser presentation tests."""
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root),str(root/'platform/core/src'),str(root/'platform/core/tests'),str(root/'platform/agents/financial')]
from agent_platform.masking_scope import scope
from test_console import make

console=make()
agents=console.agents()
endpoints={'/api/console/agents':agents,'/api/console/topology':console.topology(),
           '/api/console/activity?limit=3':console.activity(3), '/api/console/example':console.example()}
for agent in agents['agents']:
    endpoints['/api/console/onboarding/'+agent['name']]=console.onboarding(agent['name'])
for topic in ('redactor','gateway-boundary','gateway','audit','network','private-link','internet','financial-frontdoor','ops-executor'):
    endpoints['/api/console/explain/'+topic]=console.explain(topic)
profile={'name':'Demo','csrf':'fixture','expires_at':1893456000,'limits':{},'masking_scope':scope()}
request='00000000-0000-4000-8000-000000000001'
trace={'request_id':request,'user_ref':'a'*16,'outcome':'answered','reason':None,'model_calls':1,'tokens':100,
       'model':{'alias':'secure-financial-chat','resolved':None},'cost_usd':None,'cost_source':'unavailable',
       'tool_calls':[{'tool_id':'find_transactions','rows_returned':1}],
       'data_access':{'role':'finance_data_broker','scoped_to':'a'*16},'grounding_result':'grounded',
       'redaction':{'calls':1,'categories':{'EMAIL_ADDRESS':1}},'injection_result':None}
reply={'status':'answered','answer':'7-Eleven: 15.00 SAR.','request_id':request,'trace':trace}
print(json.dumps({'endpoints':endpoints,'profile':profile,'reply':reply}))
