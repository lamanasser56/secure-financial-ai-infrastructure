"""One owned process restoration in an existing local LiteLLM/PostgreSQL run.

The application, credentials, database and ledgers are never bootstrapped again.
No request can supply a command, environment, PID, endpoint or resource name.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import sys
import threading
import urllib.request

from runtime.agents.operations import (OperationsBlocked, digest, listeners,
                                      private_directory, process_identity)


def private_file(path):
    path = Path(path)
    s = path.lstat()
    if (path.is_symlink() or not path.is_file() or s.st_uid != os.getuid()
            or s.st_nlink != 1 or s.st_mode & 0o777 != 0o600 or s.st_size > 65536):
        raise OperationsBlocked('UNSAFE_FILE')
    return path.read_bytes()


def service_lock(state):
    path = state / 'service-control.lock'
    private_file(path)
    return path.open('r+b')


class ForkChild:
    def __init__(self,pid):self.pid,self.returncode=pid,None
    def poll(self):
        if self.returncode is None:
            pid,status=os.waitpid(self.pid,os.WNOHANG)
            if pid:self.returncode=os.waitstatus_to_exitcode(status)
        return self.returncode
    def terminate(self):os.kill(self.pid,signal.SIGTERM)
    def wait(self,timeout):
        until=time.monotonic()+timeout
        while self.poll() is None:
            if time.monotonic()>=until:raise subprocess.TimeoutExpired('owned_warm_child',timeout)
            time.sleep(.05)
        return self.returncode


def warm_proxy_child(argv,environment,cwd,log):
    # The trusted creating process is single-threaded. No audit/DB/socket FD
    # enters the service; only its private standard log descriptors survive.
    if threading.active_count()!=1:raise OperationsBlocked('ACTION_FAILED')
    pid=os.fork()
    if pid:return ForkChild(pid)
    try:
        os.setsid();os.chdir(cwd)
        os.environ.clear();os.environ.update(environment);sys.argv=argv[1:]
        os.dup2(log.fileno(),1);os.dup2(log.fileno(),2)
        null=os.open('/dev/null',os.O_RDONLY);os.dup2(null,0)
        for fd in list(Path('/proc/self/fd').iterdir()):
            if int(fd.name)>2:
                try:os.close(int(fd.name))
                except OSError:pass
        for name in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(name,signal.SIG_DFL)
        from litellm.proxy.proxy_cli import run_server
        run_server()
    except SystemExit as e:os._exit(e.code if type(e.code) is int else 1)
    except BaseException:os.write(2,b'OWNED_PROXY_START_FAILED\n');os._exit(1)
    os._exit(0)


class OwnedServiceAdapter:
    """Only the creating supervisor can register its live children.

    Health checks are read-only; one approved test failure and one restoration per
    service. A consumed exclusive marker survives a failed start. No key issuance,
    expiry extension, model budget reset, database restart or signal escalation.
    """
    def __init__(self, state, service, *, python, port, database_check, supervisor=None):
        self.state = private_directory(state)
        if service not in {'gateway', 'stub'} or type(port) is not int or not 1024 <= port <= 65535 or port in {4001,8765,8767,8768,8769}:
            raise OperationsBlocked('TARGET_DENIED')
        self.service, self.port, self.python = service, port, str(python)
        self.supervisor = supervisor or process_identity(os.getpid())
        if self.supervisor != process_identity(os.getpid()):
            raise OperationsBlocked('OWNER_CHANGED')
        records = json.loads(private_file(self.state / 'processes.json'))
        row = [r for r in records if r['name'] == service]
        if len(row) != 1:
            raise OperationsBlocked('OWNER_CHANGED')
        self.record = row[0]
        self.current = process_identity(self.record['pid'])
        if self.current is None or self.current['start_ticks'] != self.record['start_ticks'] or self.current['uid'] != os.getuid():
            raise OperationsBlocked('OWNER_CHANGED')
        proc = Path('/proc') / str(self.record['pid'])
        fields = (proc / 'stat').read_text().split(') ', 1)[1].split()
        if int(fields[1]) != os.getpid():
            raise OperationsBlocked('OWNER_CHANGED')
        self.argv = [os.fsdecode(x) for x in (proc / 'cmdline').read_bytes().split(b'\0') if x]
        self.cwd = (proc / 'cwd').resolve()
        root = Path(__file__).resolve().parents[2]
        expected_script = root / 'scripts' / ('local-agent-proxy.py' if service == 'gateway' else 'local-agent-upstream.py')
        if self.argv[:2] != [self.python, str(expected_script)] or self.cwd != root:
            raise OperationsBlocked('OWNER_CHANGED')
        recipe=json.loads(private_file(self.state/(service+'-launch.json')))
        if (set(recipe)!={'argv','environment','cwd'} or recipe['argv']!=self.argv
                or recipe['cwd']!=str(self.cwd) or type(recipe['environment']) is not dict
                or any(type(k) is not str or type(v) is not str for k,v in recipe['environment'].items())):
            raise OperationsBlocked('OWNER_CHANGED')
        self.environment = recipe['environment']
        self.engine=None
        if service=='gateway' and 'PRISMA_QUERY_ENGINE_BINARY' in self.environment:
            self.engine=Path(self.environment['PRISMA_QUERY_ENGINE_BINARY'])
            if self.engine!=root/'.qualified/query-engine' or self.engine.is_symlink() or not self.engine.is_file():
                raise OperationsBlocked('EVIDENCE_CHANGED')
            self.engine_integrity=hashlib.sha256(self.engine.read_bytes()).hexdigest()
        self.script_integrity = hashlib.sha256(expected_script.read_bytes()).hexdigest()
        self.script = expected_script
        self.sealed = {name: hashlib.sha256(private_file(self.state / name)).hexdigest()
                       for name in ['operator.json', 'application-alpha.json', 'application-beta.json', 'gateway-config.yaml',service+'-launch.json']}
        self.expires = min(json.loads(private_file(self.state / ('application-'+u+'.json')))['expires_at'] for u in ['alpha','beta'])
        self.database_check = database_check
        if service=='gateway':
            os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
            os.environ['LITELLM_TELEMETRY']='False'
            # Imports precede UI/action readiness, never a recovery-time cold
            # start or external model call. Service code/recipe remain pinned.
            from litellm.proxy.proxy_cli import run_server
            # The CLI imports this module inside run_server. Preload the pinned
            # server before action readiness as well, so a restore does not pay
            # its cold import cost within the unchanged health deadline.
            from litellm.proxy.proxy_server import app
            self.warm_proxy=run_server
            self.warm_server=app
        self.child = None
        self.last = {'health_verified': False, 'restore_attempts': 0, 'attempt_limit': 1,
                     'credentials_renewed': False, 'application_restarted': False,
                     'database_recreated': False, 'request_replayed': False}

    def _owned(self, *, waiting_for_exit=False):
        if self.engine and (self.engine.is_symlink() or hashlib.sha256(self.engine.read_bytes()).hexdigest()!=self.engine_integrity):
            raise OperationsBlocked('EVIDENCE_CHANGED')
        if process_identity(self.supervisor['pid']) != self.supervisor:
            raise OperationsBlocked('OWNER_CHANGED')
        if any(hashlib.sha256(private_file(self.state/name)).hexdigest() != expected for name,expected in self.sealed.items()) or hashlib.sha256(self.script.read_bytes()).hexdigest() != self.script_integrity:
            raise OperationsBlocked('EVIDENCE_CHANGED')
        actual = process_identity(self.current['pid'])
        if actual is not None and actual != self.current:
            # During exit Linux can clear cmdline before reporting Z. After the
            # already-authorized signal, treat the same PID/start/UID as still
            # alive and keep waiting. This never admits another mutation or
            # reports successful exit until the process is actually gone/Z.
            if not (waiting_for_exit and actual['command_integrity']==hashlib.sha256(b'').hexdigest()
                    and all(actual[k]==self.current[k] for k in ['pid','start_ticks','uid'])):
                raise OperationsBlocked('OWNER_CHANGED')
            actual=self.current
        rows=json.loads(private_file(self.state/'processes.json'))
        if [r for r in rows if r['name']==self.service] != [self.record]:
            raise OperationsBlocked('OWNER_CHANGED')
        return actual

    def _dependencies(self):
        if (self.state/'database-quarantined.json').exists():
            return False
        rows=json.loads(private_file(self.state/'processes.json'))
        guards=[r for r in rows if r['name']=='database-guard']
        if len(guards)!=1:
            return False
        guard=process_identity(guards[0]['pid'])
        if guard is None or guard['start_ticks']!=guards[0]['start_ticks'] or guard['uid']!=os.getuid():
            return False
        try:
            return self.database_check() is True
        except Exception:
            return False

    def _health(self, actual):
        if actual is None or self.port not in listeners(actual['pid']):
            return False
        # Stub listener proof plus gateway request-path verification in acceptance.
        if self.service=='stub':
            return True
        operator=json.loads(private_file(self.state/'operator.json'))
        client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            request=urllib.request.Request('http://127.0.0.1:'+str(self.port)+'/health/readiness',
                    headers={'Authorization':'Bearer '+operator['admin_key']})
            with client.open(request,timeout=.5) as response:
                return response.status==200 and len(response.read(65537))<=65536
        except Exception:
            return False

    def snapshot(self):
        actual=self._owned(); healthy=self._health(actual); deps=self._dependencies()
        fresh=time.time()<self.expires
        consumed=(self.state/('restore-'+self.service+'.json')).exists()
        faulted=(self.state/('fault-'+self.service+'.json')).exists()
        action=('test_failure' if healthy and deps and fresh and not faulted
                else 'restore' if actual is None and deps and fresh and not consumed else None)
        return {'kind':'service','condition':'SERVICE_HEALTHY' if healthy else 'SERVICE_FAILED' if actual is None else 'SERVICE_UNHEALTHY',
                'service':self.service,'ownership_verified':True,'listener_owned': bool(actual and self.port in listeners(actual['pid'])),
                'health_verified':healthy,'dependencies_healthy':deps,'original_client_expiry_epoch':self.expires,
                'credential_files_unchanged':True,'restore_attempts_used':int(consumed),'restore_attempts_limit':1,
                'fault_attempts_used':int(faulted),'fault_attempts_limit':1,'permitted_action':action,
                'resource_scope':'owned_composition_service'}

    def verification(self):
        return dict(self.last)

    def execute(self, action, expected, deadline, admit):
        with service_lock(self.state) as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if self.snapshot()!=expected or expected.get('permitted_action')!=action:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            if time.monotonic()>=deadline or time.time()>=self.expires:
                raise OperationsBlocked('BUDGET_EXHAUSTED')
            self._owned()
            if not self._dependencies():
                raise OperationsBlocked('ACTION_FAILED')
            admit()  # Durable step; expiry/identity checked again immediately.
            if time.monotonic()>=deadline or time.time()>=self.expires:
                raise OperationsBlocked('BUDGET_EXHAUSTED')
            actual=self._owned()
            marker=self.state/(('restore-' if action=='restore' else 'fault-')+self.service+'.json')
            fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as stream:
                stream.write(json.dumps({'attempt':1,'action':action,'service':self.service,'automatic_retry':False})+'\n');stream.flush();os.fsync(stream.fileno())
            directory=os.open(self.state,os.O_DIRECTORY|os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
            if action=='test_failure':
                if actual is None or not self._health(actual):
                    raise OperationsBlocked('EVIDENCE_CHANGED')
                fd=os.pidfd_open(actual['pid'])
                try:
                    if self._owned()!=actual:
                        raise OperationsBlocked('OWNER_CHANGED')
                    signal.pidfd_send_signal(fd,signal.SIGTERM)
                finally:os.close(fd)
            elif action=='restore':
                self.last['restore_attempts']=1
                if actual is not None:
                    raise OperationsBlocked('OWNER_CHANGED')
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:probe.bind(('127.0.0.1',self.port))
                    except OSError:raise OperationsBlocked('OWNER_CHANGED') from None
                log=(self.state/(self.service+'.log')).open('ab')
                try:
                    self.child=(warm_proxy_child(self.argv,self.environment,self.cwd,log) if self.service=='gateway'
                        else subprocess.Popen(self.argv,cwd=self.cwd,env=self.environment,
                            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True))
                finally:log.close()
                self.current=process_identity(self.child.pid)
                if self.current is None:
                    raise OperationsBlocked('ACTION_FAILED')
                self.record={'pid':self.child.pid,'start_ticks':self.current['start_ticks'],'name':self.service}
                rows=json.loads(private_file(self.state/'processes.json'))
                rows=[self.record if row['name']==self.service else row for row in rows]
                tmp=self.state/'processes-restored.json'
                fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'w') as stream:
                    stream.write(json.dumps(rows)+'\n');stream.flush();os.fsync(stream.fileno())
                os.replace(tmp,self.state/'processes.json')
                self.last['restore_attempts']=1
            else:
                raise OperationsBlocked('TARGET_DENIED')
        self._wait_for_outcome(action,deadline)

    def _wait_for_outcome(self, action, deadline):
        # Health polls are bounded observations, not start retries or model calls.
        checks=0
        while time.monotonic()<deadline and checks<32:
            checks+=1
            actual=self._owned(waiting_for_exit=action=='test_failure')
            if action=='test_failure' and actual is None:
                self.last['health_verified']=False;self.last['controlled_failure_verified']=True;return
            if action=='restore' and self._health(actual) and self._dependencies():
                self.last.update(health_verified=True,health_checks=checks,credentials_unchanged=True);return
            if action=='restore' and actual is None:
                break
            remaining=deadline-time.monotonic()
            if remaining>0 and checks<32:
                # Use the existing deadline instead of ending early after 32
                # fixed sleeps. A slow admitted start still gets a final check.
                time.sleep(remaining/(33-checks))
        self.last.update(health_verified=False,health_checks=checks)
        raise OperationsBlocked('ACTION_FAILED')
