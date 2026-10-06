"""Owned Docker containment and fixed Unix-channel UI forwarding.

Uses only the supervisor's private daemon and exact image configuration. No host
network, privilege, Docker socket, host filesystem or audit mount enters the app.
The trusted controller and owner remain outside this containment boundary.
"""
import gzip
import hashlib
import json
import stat
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tarfile
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer

from runtime.agents.control_channel import ControlServer, peer
from runtime.agents.isolation_controller import IsolationController
from runtime.agents.operations import process_identity

APP_UID = 65532


def namespace(pid):
    # Peer PID comes from the kernel, never a browser/model selector.
    return subprocess.check_output(['sudo', '/usr/bin/readlink', f'/proc/{int(pid)}/ns/pid'],
                                   timeout=1, stderr=subprocess.DEVNULL).decode().strip()


class UnixHTTP(HTTPConnection):
    def __init__(self, path, verify=None):
        super().__init__('localhost', timeout=25)
        self.path, self.verify = str(path), verify

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(25)
        self.sock.connect(self.path)
        if self.verify and not self.verify(*peer(self.sock)):
            self.sock.close()
            raise PermissionError


class FrontHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def handle_request(self):
        if self.path not in {'/', '/app.js', '/style.css', '/i18n.json', '/operations.html',
                             '/operations.js', '/api/bootstrap', '/api/conversation', '/api/reset', '/api/operations'}:
            self.send_error(404)
            return
        try:
            lengths = self.headers.get_all('Content-Length', [])
            if (self.command == 'POST' and (len(lengths) != 1 or not lengths[0].isdigit()
                    or not 1 <= int(lengths[0]) <= 4096) or self.headers.get_all('Transfer-Encoding')):
                raise ValueError
            body = self.rfile.read(int(lengths[0])) if self.command == 'POST' else None
            if len(self.headers) > 32 or any(len(k)+len(v) > 2048 for k, v in self.headers.items()):
                raise ValueError
            headers = dict(self.headers.items())
            # Duplicate auth/boundary fields must reach a denial, not collapse.
            if any(len(self.headers.get_all(k, [])) > 1 for k in self.headers.keys()):
                raise ValueError
            config = self.server.configuration
            def verify(pid, uid, gid):
                return uid == APP_UID and namespace(pid) == config['namespace']
            connection = UnixHTTP(config['socket'], verify)
            connection.request(self.command, self.path, body, headers)
            response = connection.getresponse()
            data = response.read(131073)
            if len(data) > 131072:
                raise ValueError
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {'server', 'date', 'connection', 'content-length'}:
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data)
            connection.close()
        except Exception:
            data = b'{"error":"isolated_application_unavailable"}'
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        self.close_connection = True

    do_GET = do_POST = handle_request


def front(path):
    configuration = json.loads(Path(path).read_text())
    if set(configuration) != {'port', 'socket', 'namespace'}:
        raise ValueError
    with HTTPServer(('127.0.0.1', configuration['port']), FrontHandler) as server:
        server.configuration = configuration
        server.serve_forever()


def run_isolated(stack, state, args, config, agents, budget, redactor, tools, terminal, operations, ledger, *, source_overlay=None):
    from runtime.agents.service_restoration import private_file
    if source_overlay and args.trial_admission:
        raise ValueError('isolation:live_overlay_denied')
    image_record = json.loads(private_file(args.isolation_record))
    configuration = image_record['subjects']['application']['configuration_id']
    archive = args.application_archive
    if archive.is_symlink() or not archive.is_file():
        raise ValueError
    with tarfile.open(archive, 'r:gz') as stream:
        manifest = json.load(stream.extractfile('manifest.json'))
        matched = []
        for entry in manifest:
            member = stream.getmember(entry['Config'])
            if not member.isfile() or member.size > 2_097_152:
                raise ValueError
            raw = stream.extractfile(member).read()
            if 'sha256:'+hashlib.sha256(raw).hexdigest() == configuration:
                matched.append((entry, json.loads(raw)))
        if len(matched) != 1 or matched[0][0]['RepoTags'] != ['portfolio-agent-application:qualified']:
            raise ValueError('isolation:configuration_absent')
        expected = matched[0][1]
    log = (state/'isolation-private.log').open('xb')
    docker = stack.DOCKER_COMMAND
    def checked(parts, timeout=120):
        value = subprocess.run(docker+parts, stdout=log, stderr=log, timeout=timeout)
        if value.returncode:
            raise ValueError('isolation:docker_step_failed')
    checked(['load', '--input', str(archive)])
    # Docker's legacy store uses config IDs. The caller admits only this exact ID.
    info = json.loads(subprocess.check_output(docker+['image', 'inspect', 'portfolio-agent-application:qualified'], stderr=log))[0]
    if (info['RootFS']['Layers'] != expected['rootfs']['diff_ids']
            or info['Architecture'] != expected['architecture']
            or any(info['Config'].get(k) != expected['config'].get(k) for k in ['User','Env','Entrypoint','WorkingDir','Cmd'])):
        raise ValueError
    image_id = info['Id']
    shared, ui, admission = state/'control-channel', state/'ui-channel', state/'isolated-admission'
    for p in (shared, ui, admission):
        p.mkdir(mode=0o700)
    for p, mode in [(shared, '710'), (ui, '770')]:
        subprocess.run(['sudo', 'chown', f'{os.getuid()}:{APP_UID}', str(p)], check=True, stdout=log, stderr=log)
        subprocess.run(['sudo', 'chmod', mode, str(p)], check=True, stdout=log, stderr=log)
    app = {k: config[k] for k in ['subject', 'tenant', 'certificates', 'token', 'tenant_reference_key', 'client_keys', 'expires_at']}
    token = os.urandom(32).hex()
    app.update(simulation=not bool(args.trial_admission), channel_token=token,
               controller_uid=os.getuid(), controller_gid=os.getgid(), ui_port=args.port,
               admission_scope=args.admission['scope'] if args.trial_admission else 'offline_free_text')
    file = admission/'application.json'
    file.write_text(json.dumps(app)+'\n')
    subprocess.run(['sudo', 'chown', f'{APP_UID}:{APP_UID}', str(file)], check=True, stdout=log, stderr=log)
    # Bind only the individual config file; parent directory remains owner-private.
    broker = IsolationController(config, agents, budget, redactor, tools, terminal, operations, ledger)
    selected = {}
    def verify(pid, uid, gid):
        try:
            return uid == APP_UID and selected.get('namespace') == namespace(pid)
        except Exception:
            return False
    server = ControlServer(shared/'control.sock', token, broker.dispatch, verify)
    subprocess.run(['sudo', 'chown', f'{os.getuid()}:{APP_UID}', str(shared/'control.sock')], check=True, stdout=log, stderr=log)
    os.chmod(shared/'control.sock', 0o660)
    name = 'portfolio-isolated-'+json.loads(private_file(state/'operator.json'))['run_id'][:16]
    relay = None
    relay_identity = None
    created = False
    file_identity = (file.stat().st_dev,file.stat().st_ino,hashlib.sha256((json.dumps(app)+'\n').encode()).hexdigest())
    try:
        mounts = ['--mount', f'type=bind,src={shared},dst=/channels,readonly',
                  '--mount', f'type=bind,src={ui},dst=/ui',
                  '--mount', f'type=bind,src={file},dst=/admission/application.json,readonly']
        if source_overlay:
            for directory in ('runtime', 'contracts', 'demo'):
                mounts += ['--mount', f'type=bind,src={source_overlay/directory},dst=/app/{directory},readonly']
        checked(['create', '--name', name, '--label', 'portfolio.run='+name,
            '--network', 'none', '--read-only', '--user', '65532:65532', '--group-add', str(os.getgid()),
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '64',
            '--cpus', '0.5', '--memory', '512m', '--restart', 'no',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m,mode=0700,uid=65532,gid=65532',
            *mounts, '--entrypoint', '/usr/local/bin/python3.12', image_id,
            '-m', 'runtime.agents.isolated_application'])
        created = True
        checked(['start', name])
        actual = json.loads(subprocess.check_output(docker+['inspect', name], stderr=log))[0]
        selected.update(namespace=namespace(actual['State']['Pid']), container=actual['Id'])
        (shared/'ready').write_text('READY\n')
        subprocess.run(['sudo', 'chown', f'{os.getuid()}:{APP_UID}', str(shared/'ready')], check=True, stdout=log, stderr=log)
        os.chmod(shared/'ready', 0o640)
        until = time.monotonic()+15
        while not (ui/'ui.sock').exists():
            if time.monotonic() >= until:
                raise ValueError('isolation:ui_not_ready')
            time.sleep(.1)
        front_config = state/'ui-forwarder.json'
        front_config.write_text(json.dumps({'port': args.port, 'socket': str(ui/'ui.sock'), 'namespace': selected['namespace']})+'\n')
        relay = subprocess.Popen([str(args.python), '-m', 'runtime.agents.isolation_runtime', str(front_config)],
            stdout=log, stderr=log, cwd=Path(__file__).resolve().parents[2], start_new_session=True)
        relay_identity = process_identity(relay.pid)
        (state/'isolation-runtime.json').write_text(json.dumps({'container': selected['container'],
            'name': name, 'namespace': selected['namespace'], 'configuration': configuration,'local_store_image_id':image_id,
            'relay_pid': relay.pid, 'controller_pid': os.getpid(), 'controller_start_ticks': process_identity(os.getpid())['start_ticks'],
            'model_http_attempts': 0, 'source_overlay_for_isolated_test': bool(source_overlay)})+'\n')
        print(json.dumps({'ui':f'http://127.0.0.1:{args.port}','isolation':'network_none_peer_checked_controller',
            'live_enabled':bool(args.trial_admission),'redaction':'google_sdp_candidate' if args.trial_admission else 'simulated'}),flush=True)
        server.serve_forever(poll_interval=.1)
    finally:
        failures = []
        def cleanup(label, operation):
            try:
                operation()
            except Exception:
                failures.append(label)
        cleanup('control_socket', server.server_close)
        def stop_relay():
            if relay is not None and relay.poll() is None:
                if process_identity(relay.pid) != relay_identity:
                    raise ValueError
                fd = os.pidfd_open(relay.pid)
                try:
                    if process_identity(relay.pid) != relay_identity:
                        raise ValueError
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
                finally:
                    os.close(fd)
                relay.wait(timeout=5)
        cleanup('ui_forwarder', stop_relay)
        if created:
            cleanup('application_stop', lambda: checked(['stop', '--time', '5', name]))
            cleanup('application_remove', lambda: checked(['rm', name]))
        def clear_admission():
            metadata = file.lstat()
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != APP_UID or metadata.st_mode & 0o077
                    or (metadata.st_dev,metadata.st_ino,subprocess.check_output(['sudo','sha256sum','--',str(file)],stderr=log).decode().split()[0]) != file_identity):
                raise ValueError
            subprocess.run(['sudo','rm','--',str(file)],check=True,stdout=log,stderr=log)
        cleanup('application_admission', clear_admission)
        (state/'isolation-outcome.json').write_text(json.dumps({'owned_container_removed': not any(
            x in failures for x in ['application_stop','application_remove']),
            'cleanup_failures': failures,
            'model_http_attempts': broker.http_attempts, 'model_http_responses': broker.http_responses,
            'transport_failures': broker.transport_failures,
            'channel_frames': server.frames, 'credentials_renewed': False})+'\n')
        log.close()
        if failures:
            raise ValueError('isolation:owned_cleanup_incomplete')


if __name__ == '__main__':
    try:
        front(sys.argv[1])
    except Exception:
        raise SystemExit('isolated_ui:blocked') from None
