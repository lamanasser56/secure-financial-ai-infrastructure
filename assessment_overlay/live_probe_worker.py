"""D04: current worker rejects malformed/wrong-key calls and has no DB path."""
from live_probe_kube import one_pod, python_probe


FRONTDOOR = r'''
import json, urllib.error, urllib.request
from pathlib import Path
c = json.loads(Path('/secrets/frontdoor/frontdoor.json').read_text())
route = next(item for item in c['routes'].values() if item['agent'] == 'financial-u1')
def status(key, body):
    request = urllib.request.Request(route['url'], data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
body = {'capability':'invalid', 'question':'synthetic assessment', 'language':'en'}
print(json.dumps({'wrong_worker_key_denied':status('wrong-key', body) == 403,
                  'extra_user_id_rejected':status(route['key'], dict(body, user_id='other')) == 400}))
'''

WORKER = r'''
import json, socket
from pathlib import Path
c = json.loads(Path('/secrets/agent/agent.json').read_text())
try:
    connection = socket.create_connection(('postgres.platform.svc.cluster.local', 5432), timeout=3)
    connection.close()
    connected = True
except OSError:
    connected = False
print(json.dumps({'worker_exact_credentials':set(c) == {'gateway_key','redactor_key','agent_name',
    'broker_key','worker_key','capability_public_key','user_id'},
    'no_db_or_session_key':not any('db' in key or 'session' in key or 'private' in key for key in c),
    'direct_database_denied':not connected}))
'''


def probe_d04(kubeconfig, *, executable='kubectl', pod=one_pod, execute=python_probe):
    frontdoor = pod(kubeconfig, 'apps', 'app.kubernetes.io/name=financial-frontdoor',
                    executable=executable)
    worker = pod(kubeconfig, 'agent-financial', 'agent-platform/user-slot=u1', executable=executable)
    checks = execute(kubeconfig, 'apps', frontdoor, FRONTDOOR, executable=executable)
    checks.update(execute(kubeconfig, 'agent-financial', worker, WORKER, executable=executable))
    return checks
