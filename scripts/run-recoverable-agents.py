#!/usr/bin/env python3
"""Combined financial/operations UI with one separately owned local test stack.

The default uses actual LiteLLM/PostgreSQL with simulated model/redaction.
Candidate external reasoning requires separately verified private admissions.
There is no current-user-stack mutation or cloud credential entry point.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.composition import BoundaryBudget, compose_local
from runtime.agents.gateway_budget import RunAttemptBudget
from runtime.agents.operations import OperationsAudit, OperationsController, ServiceTarget, CacheTarget, cache_inventory, private_directory, process_identity
from runtime.agents.operations_local import fixture_identity, ProcVisibility
from runtime.agents.operations_model import OperationsExplainer
from runtime.agents.operations_service import OperationsService
from runtime.agents.service_restoration import OwnedServiceAdapter, private_file
from runtime.agents.terminal_audit import TerminalAudit
from runtime.agents.web import DemoServer


def combined(stack,state,args):
    import psycopg
    config=json.loads(private_file(state/('application-'+args.user+'.json')))
    tool=DurableToolAudit(state/('audit-tools-'+args.user));terminal=TerminalAudit(state/('audit-turns-'+args.user))
    ops_path=state/'operations-audit';ops_path.mkdir(mode=0o700)
    audit=OperationsAudit(ops_path)
    ledger=None
    try:
        budget=RunAttemptBudget(total=32,per_subject=16,lifetime=900)
        boundary=BoundaryBudget()
        if args.trial_admission:
            from runtime.agents.trial_composition import TrialLedger,TrialTerminal,TrialExplainer,compose_trial,read_json
            overlay=read_json(args.trial_configuration)
            if (set(overlay)!={'scope','gateway_url','redactor_key','client_keys','expires_at','subject'}
                    or overlay['scope']!=args.admission['scope'] or overlay['subject']!=config['subject']
                    or set(overlay['client_keys'])!={'financial','infrastructure'}
                    or not time.time()<overlay['expires_at']<=min(config['expires_at'],args.admission['expires_at'])):
                raise ValueError('trial:configuration_rejected')
            config=config|{k:v for k,v in overlay.items() if k!='scope'}|{'mode':'admitted_synthetic_trial','live_enabled':True}
            (state/'trial-reservations').mkdir(mode=0o700);(state/'audit-live-turns').mkdir(mode=0o700)
            ledger=TrialLedger(state/'trial-reservations');ledger.expires=args.admission['expires_at']
            terminal.close();terminal=TrialTerminal(state/'audit-live-turns')
            agents,budget,redactor=compose_trial(config,admission=args.admission,ledger=ledger,terminal=terminal,
                    tools_audit=tool,connect=lambda:psycopg.connect(config['tenant_database_url'],connect_timeout=1))
            explainer=TrialExplainer(config,budget,redactor)
        else:
            agents,_,_=compose_local(config,connect=lambda:psycopg.connect(config['tenant_database_url'],connect_timeout=1),
                    terminal_sink=terminal,tool_sink=tool,model_budget=budget,redaction_budget=boundary)
            explainer=OperationsExplainer(config,model_budget=budget,redactor=agents['financial'][0].redactor)
        # Exercise the model-shaped wording path while retaining explicit stub
        # runtime, simulated redaction and truthful reporting.
        agents['financial'][0].language_model_scope = True
        identity,auth,tenant=fixture_identity()
        operator=json.loads(private_file(state/'operator.json'))
        inspected=json.loads(__import__('subprocess').check_output(stack.DOCKER_COMMAND+['inspect',stack.NAME]))[0]
        container_id=inspected['Id']
        def database_check():
            # Exact immutable container/run subject and read-only tenant role.
            current=json.loads(__import__('subprocess').check_output(stack.DOCKER_COMMAND+['inspect',container_id],timeout=1,stderr=__import__('subprocess').DEVNULL))[0]
            if (current['Id']!=container_id or current['Config']['Labels'].get('portfolio.run')!=operator['run_id']
                    or current['Image']!=inspected['Image'] or not current['State']['Running']):return False
            with psycopg.connect(config['tenant_database_url'],connect_timeout=1,options='-c statement_timeout=1000',autocommit=True) as db:
                return db.execute('SELECT 1').fetchone()==(1,)
        targets={}
        for name,port in [('gateway',args.gateway_port),('stub',args.stub_port)]:
            adapter=OwnedServiceAdapter(state,name,python=args.python,port=port,database_check=database_check)
            targets['test-'+name]=ServiceTarget(tenant,adapter)
        if args.registered_disposable_cache:
            path=private_directory(args.registered_disposable_cache)
            targets['registered-cache']=CacheTarget(tenant,path,cache_inventory(path),True)
        secret=secrets.token_urlsafe(32)
        (state/'operator-approval.secret').write_text(secret+'\n')
        controller=OperationsController(audit,identity,auth,targets,approval_secret=secret,model=explainer,
                   visibility=ProcVisibility() if args.registered_disposable_cache else None,
                   lifetime=max(1,min(900,config['expires_at']-time.time())))
        operations=OperationsService(controller,json.loads(private_file(args.security_config)) if args.security_config else None,
                    financial_url='http://127.0.0.1:'+str(args.port))
        composition='supervised_candidate_live' if args.trial_admission else 'local_proxy_stub'
        with DemoServer(('127.0.0.1',args.port),agents=agents,operations=operations,composition=composition) as server:
            print(json.dumps({'ui':server.origin,'operations':server.origin+'/operations.html','mode':composition,
                 'live_enabled':bool(args.trial_admission),'recovery':'one_owned_service_start','clients_and_budgets_renewed':False}),flush=True)
            server.serve_forever()
    finally:
        audit.close();tool.close();terminal.close()
        if ledger:ledger.close()


def stop(state):
    state=private_directory(state)
    owner=json.loads(private_file(state/'launcher-owner.json'))
    current=process_identity(owner['pid'])
    if current is None:
        status=json.loads(private_file(state/'launcher-status.json'))
        if status.get('cleanup_complete') is not True:raise ValueError
        return
    if current['start_ticks']!=owner['start_ticks'] or current['uid']!=os.getuid() or current['pid']==os.getpid():raise ValueError
    proc=Path('/proc')/str(current['pid']);argv=(proc/'cmdline').read_bytes().split(b'\0');cwd=(proc/'cwd').resolve()
    script=next((cwd/os.fsdecode(x) for x in argv if x.endswith(b'/run-recoverable-agents.py')),None)
    if script is None or script.resolve()!=Path(__file__).resolve() or b'--state' not in argv:raise ValueError
    if (cwd/os.fsdecode(argv[argv.index(b'--state')+1])).resolve()!=state:raise ValueError
    fd=os.pidfd_open(current['pid'])
    try:
        if process_identity(current['pid'])!=current:raise ValueError
        signal.pidfd_send_signal(fd,signal.SIGTERM)
    finally:os.close(fd)
    until=time.monotonic()+60
    while time.monotonic()<until:
        if process_identity(current['pid']) is None and json.loads(private_file(state/'launcher-status.json')).get('cleanup_complete') is True:return
        time.sleep(.1)
    raise ValueError


def main():
    os.umask(0o077);parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--python',type=Path,default=Path(sys.executable))
    parser.add_argument('--database-archive',type=Path);parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--gateway-port',type=int,default=14004);parser.add_argument('--stub-port',type=int,default=18772)
    parser.add_argument('--user',choices=['alpha','beta'],default='alpha');parser.add_argument('--stop',action='store_true')
    parser.add_argument('--security-config',type=Path)
    parser.add_argument('--registered-disposable-cache',type=Path)
    parser.add_argument('--trial-admission',type=Path);parser.add_argument('--trial-configuration',type=Path)
    args=parser.parse_args();args.state=args.state.absolute()
    if args.stop:stop(args.state);print(json.dumps({'owned_stack_stopped':True,'audit_retained':True}));return
    if bool(args.trial_admission)!=bool(args.trial_configuration):raise ValueError('trial:missing_admission')
    if args.trial_admission:
        from runtime.agents.trial_composition import ACK,admit,consume_admission
        import subprocess
        if os.environ.get('PORTFOLIO_SUPERVISED_TRIAL_ACK')!=ACK:raise ValueError('trial:acknowledgement_missing')
        source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise ValueError('trial:source_changed')
        args.admission=admit(args.trial_admission,scope='supervised_synthetic_free_text',source=source,
                    program_integrity=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        if args.admission['subject']!='local-fixture-'+args.user:raise ValueError('trial:subject_changed')
        consume_admission(args.trial_admission,args.admission)
    if args.database_archive is None or len({args.port,args.gateway_port,args.stub_port})!=3 or any(x in {4001,8765,8767,8768,8769} or not 1024<=x<=65535 for x in [args.port,args.gateway_port,args.stub_port]):raise ValueError
    spec=importlib.util.spec_from_file_location('qualified_local',ROOT/'scripts/run-qualified-local-agents.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    args.check=args.rehearse=False;args.application_runner=lambda stack,state:combined(stack,state,args)
    launcher.install_interrupt_handlers();launcher.run(args)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception:raise SystemExit('recoverable_application:blocked; inspect private state') from None
