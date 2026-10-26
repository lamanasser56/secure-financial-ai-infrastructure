"""Packet probes for current security roles. Destination failures cannot stand in for policy denial."""
import json
import socket

from attack_runtime import NotExercised

PYTHON = """import errno,json,socket
out={}
for name,host,port in TARGETS:
 try:
  with socket.create_connection((host,port),timeout=3): out[name]='CONNECTED'
 except socket.gaierror: out[name]='DNS_ERROR'
 except TimeoutError: out[name]='DENIED'
 except OSError as error:
  out[name]='DENIED' if error.errno in (errno.EACCES,errno.EPERM,errno.EHOSTUNREACH,errno.ENETUNREACH) else 'TARGET_ERROR'
print(json.dumps(out))
"""
NODE = """const net=require('node:net'), out={}, T=TARGETS;
Promise.all(T.map(([name,host,port])=>new Promise(resolve=>{
 let done=false; const socket=net.connect({host,port});
 const finish=value=>{if(done)return;done=true;out[name]=value;socket.destroy();resolve();};
 socket.setTimeout(3000,()=>finish('DENIED'));
 socket.on('connect',()=>finish('CONNECTED'));
 socket.on('error',e=>finish(['EACCES','EPERM','EHOSTUNREACH','ENETUNREACH','ETIMEDOUT'].includes(e.code)?'DENIED':e.code.startsWith('EAI_')||e.code==='ENOTFOUND'?'DNS_ERROR':'TARGET_ERROR'));
}))).then(()=>console.log(JSON.stringify(out)));
"""


def probe_source(namespace, name, container):
    # Packet probes invoke the installed runtime, independent of an image-owned entrypoint or workload command.
    runtime = 'node' if namespace == 'agent-platform-guide' else 'python'
    program = '/nodejs/bin/node' if runtime == 'node' else '/usr/local/bin/python3.12'
    return namespace, name, container['name'], runtime, program


def inventory(docs):
    services = {(d['metadata']['namespace'], d['metadata']['name']): d for d in docs if d['kind'] == 'Service'}
    deployments = {(d['metadata']['namespace'], d['metadata']['name']): d for d in docs if d['kind'] == 'Deployment'}
    targets = {'internet': ('1.1.1.1', 443), 'metadata': ('169.254.169.254', 80),
               'api': ('kubernetes.default.svc.cluster.local', 443)}
    def service(label, namespace, name, port):
        if not any(p['port'] == port for p in services.get((namespace, name), {}).get('spec', {}).get('ports', [])):
            raise NotExercised('current_service_inventory_incomplete')
        targets[label] = (name + '.' + namespace + '.svc.cluster.local', port)
    for label, namespace, name, port in (
        ('boundary','platform','gateway-boundary',4000), ('redactor','platform','redactor',4003),
        ('provider','platform','gateway-provider',4001), ('database','platform','postgres',5432),
        ('broker','apps','financial-frontdoor',8082), ('observer','ops','ops-agent',8090),
        ('executor','ops','ops-executor',8091), ('guide','agent-platform-guide','agent',8082)):
        service(label, namespace, name, port)
    workers = sorted(name for ns, name in deployments if ns == 'agent-financial')
    if not workers:
        raise NotExercised('current_workers_missing')
    for worker in workers:
        service('worker_' + worker.replace('-', '_'), 'agent-financial', worker, 8081)
    # Expectations are the security roles, independently of the NetworkPolicy allow rules.
    roles = [(('apps','app'), {'boundary','redactor','database','observer'}),
             (('apps','financial-frontdoor'), {'database'} | {k for k in targets if k.startswith('worker_')}),
             (('ops','ops-agent'), {'boundary','redactor','executor','api'}),
             (('ops','ops-executor'), {'provider','api'}),
             (('platform','gateway-boundary'), {'provider','redactor'}),
             (('agent-platform-guide','agent'), {'boundary','redactor'})]
    roles += [(('agent-financial', worker), {'boundary','redactor','broker'}) for worker in workers]
    matrix = []
    for (namespace, name), allowed in roles:
        doc = deployments.get((namespace, name))
        if doc is None:
            raise NotExercised('current_role_workload_missing')
        container = doc['spec']['template']['spec']['containers'][0]
        wanted = {}
        for label in targets:
            # Pod-to-self traffic is outside NetworkPolicy's isolation contract.
            if label == 'worker_' + name.replace('-', '_') or (label == 'guide' and namespace == 'agent-platform-guide'):
                continue
            if (namespace, name) in (('ops','ops-executor'), ('ops','ops-agent'), ('apps','financial-frontdoor'), ('platform','gateway-boundary')):
                if label == {('ops','ops-executor'):'executor', ('ops','ops-agent'):'observer',
                             ('apps','financial-frontdoor'):'broker', ('platform','gateway-boundary'):'boundary'}[(namespace,name)]:
                    continue
            wanted[label] = 'CONNECTED' if label in allowed else 'DENIED'
        matrix.append((probe_source(namespace, name, container), wanted))
    redactor = deployments.get(('platform','redactor'))
    if redactor is None:
        raise NotExercised('metadata_control_missing')
    c = redactor['spec']['template']['spec']['containers'][0]
    metadata_control = probe_source('platform', 'redactor', c)
    return targets, matrix, metadata_control


def execute(targets, source, wanted, python, node):
    namespace, name, container, runtime, program = source
    endpoints = [(label, *targets[label]) for label in wanted]
    code = (NODE if runtime == 'node' else PYTHON).replace('TARGETS', json.dumps(endpoints))
    result = (node if runtime == 'node' else python)(namespace, name, code, container, interpreter=program)
    if result.returncode:
        raise NotExercised('packet_probe_unavailable')
    try:
        observed = json.loads(result.stdout)
    except ValueError:
        raise NotExercised('packet_probe_invalid_reply') from None
    if set(observed) != set(wanted) or any(v not in ('CONNECTED','DENIED') for v in observed.values()):
        raise NotExercised('dns_or_target_failure')
    return observed


def internet_ready():
    try:
        with socket.create_connection(('1.1.1.1',443), timeout=3):
            return True
    except OSError:
        return False


def check(docs, python, node, *, external_control=internet_ready):
    targets, matrix, metadata_control = inventory(docs)
    controls = {'metadata':metadata_control, 'guide':next(s for s,_ in matrix if s[0] == 'agent-platform-guide')}
    for label in targets:
        if label in ('internet','metadata','guide'):
            continue
        source = next((s for s,wanted in matrix if wanted.get(label) == 'CONNECTED'), None)
        if source is None:
            raise NotExercised('healthy_destination_control_missing')
        controls[label] = source
    def healthy():
        if not external_control():
            raise NotExercised('internet_destination_control_failed')
        for label, source in controls.items():
            if execute(targets, source, {label:'CONNECTED'}, python, node) != {label:'CONNECTED'}:
                raise NotExercised('positive_destination_control_failed')
    healthy()
    failures, probes = 0, 0
    for source, wanted in matrix:
        observed = execute(targets, source, wanted, python, node)
        probes += len(wanted)
        failures += sum(observed[label] != expected for label, expected in wanted.items())
    healthy()
    return not failures, {'sources':len(matrix), 'packet_probes':probes, 'unexpected_paths':failures,
                          'positive_controls':len(controls), 'verdict':'FAIL' if failures else 'PASS'}
