#!/usr/bin/env python3
"""Prepared private synthetic-demo redaction bridge, separately hashed program.

No new image/adapter or provider selection. No request-selected project/endpoint/
policy exists. A future approval must bind this exact program separately from
its historical SDK image signature. No current entry point starts this server.
"""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

ROOT = Path('/app') if '__file__' not in globals() else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.phase3.google_sdp_adapter import ContentAttemptBudget, GoogleSDPFailure
from runtime.phase3.sdp_context_policy import GoogleSDPContextRedactor
ACK = 'I_ACKNOWLEDGE_ONE_FIXED_SYNTHETIC_CATALOG_NO_AGENT_PROMOTION'
POLICY_HASH = 'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db'
TRIAL_ACK='I_ACKNOWLEDGE_SUPERVISED_SYNTHETIC_FREE_TEXT_NOT_FIXED_QUALIFICATION'


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def private(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 32768):
        raise ValueError
    return json.loads(path.read_bytes().decode('utf-8'), object_pairs_hook=unique)


class Journal:
    """Reserve both possible SDK operations and fsync before each redaction.

    Unused slots are never refunded in this stricter outer ledger. Actual SDK
    attempts are independently measured by the unchanged adapter. One sequential
    HTTPServer owns the journal; any partial/corrupt record blocks admission.
    """
    def __init__(self, directory, expires):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError
        self.path, self.expires = directory / 'sdk-reservations', expires
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    def reserved(self):
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 174):
            raise GoogleSDPFailure('BUDGET_EXHAUSTED', 'budget')
        raw = self.path.read_bytes()
        if raw != b'2\n' * (len(raw) // 2):
            raise GoogleSDPFailure('BUDGET_EXHAUSTED', 'budget')
        return len(raw)
    def reserve(self):
        if time.time() >= self.expires or self.reserved() + 2 > 174:
            raise GoogleSDPFailure('BUDGET_EXHAUSTED', 'budget')
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            if os.write(fd, b'2\n') != 2:
                raise ValueError
            os.fsync(fd)
        finally:
            os.close(fd)


class Server(HTTPServer):
    def handle_error(self, request, client_address):
        # Suppress raw exception/socket/provider content. A bad request never
        # triggers another provider invocation or tool/model operation.
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def setup(self):
        super().setup()
        self.connection.settimeout(1)
    def reply(self, status, value):
        raw = json.dumps(value, separators=(',', ':')).encode()
        if len(raw) > 16384:
            status, raw = 503, b'{"code":"OUTPUT_LIMIT","stage":"output"}'
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        self.reply(405, {'code': 'METHOD_REJECTED'})
    def do_POST(self):
        try:
            if (self.path != '/redact' or self.headers.get('Transfer-Encoding') is not None
                    or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.key)
                    or self.headers.get('Content-Type') != 'application/json'):
                self.reply(403, {'code': 'ADMISSION_REJECTED'}); return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16384:
                raise ValueError
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
            if (type(value) is not dict or set(value) != {'text'} or type(value['text']) is not str
                    or not 0 < len(value['text'].encode('utf-8')) <= 4096):
                raise ValueError
            self.server.journal.reserve()
            result = self.server.redactor.redact(value['text'])
            self.reply(200, {'text': result.text, 'categories': list(result.categories)})
        except GoogleSDPFailure as error:
            self.server.failed = True
            self.server.diagnostic = error.diagnostic
            self.reply(503, error.diagnostic)
        except Exception:
            self.server.failed = True
            self.server.diagnostic = {'code': 'UNKNOWN', 'stage': 'input'}
            self.reply(503, self.server.diagnostic)


def admit_bridge(admission):
    fields = {'approved', 'program_sha256', 'project_id', 'key', 'expires_at', 'policy_sha256', 'redaction_qualification'}
    current_fixed=set(admission)==fields|{'scope','campaign_evidence_sha256'}
    if current_fixed:
        if (admission['scope']!='fixed_inputs_qualification' or admission['redaction_qualification']!='QUALIFIED_FOR_FIXED_CURRENT_APPLICATION'
                or len(admission['campaign_evidence_sha256'])!=64 or any(c not in '0123456789abcdef' for c in admission['campaign_evidence_sha256'])):raise ValueError
        fields=fields|{'scope','campaign_evidence_sha256'}
    trial=set(admission)==fields|{'scope','campaign_evidence_sha256','fixed_integration_evidence_sha256'}
    if trial:
        if (admission['scope']!='supervised_synthetic_free_text'
                or any(type(admission[k]) is not str or len(admission[k])!=64
                       or any(c not in '0123456789abcdef' for c in admission[k])
                       for k in ['campaign_evidence_sha256','fixed_integration_evidence_sha256'])):
            raise ValueError
        fields=fields|{'scope','campaign_evidence_sha256','fixed_integration_evidence_sha256'}
    acknowledgement=(os.environ.get('PORTFOLIO_SUPERVISED_TRIAL_ACK')==TRIAL_ACK if trial
                     else os.environ.get('PORTFOLIO_SYNTHETIC_LIVE_DEMO_ACK')==('I_ACKNOWLEDGE_ONE_FIXED_CURRENT_APPLICATION_QUALIFICATION' if current_fixed else ACK))
    if (set(admission) != fields or admission['approved'] is not True
            or not acknowledgement
            or admission['policy_sha256'] != POLICY_HASH
            or type(admission['expires_at']) not in (int, float)
            or not time.time() < admission['expires_at'] <= time.time() + 900
            or admission['redaction_qualification'] != ('QUALIFIED_FOR_SUPERVISED_SYNTHETIC_SCOPE' if trial else 'QUALIFIED_FOR_FIXED_CURRENT_APPLICATION' if current_fixed else 'QUALIFIED_FOR_THIS_SYNTHETIC_CATALOG')
            or not isinstance(admission['key'], str) or len(admission['key']) != 64
            or any(c not in '0123456789abcdef' for c in admission['key'])):
        raise ValueError
    return 'supervised_synthetic_free_text' if trial else 'fixed_inputs_qualification'


def run():
    admission = private(Path('/admission/redactor-server.json'))
    scope=admit_bridge(admission)
    code = (Path(__file__).read_bytes() if '__file__' in globals()
            else Path('/proc/self/cmdline').read_bytes().split(b'\x00')[2])
    if hashlib.sha256(code).hexdigest() != admission['program_sha256']:
        raise ValueError
    if hashlib.sha256((ROOT / 'evaluation/google-sdp-context/policy.json').read_bytes()).hexdigest() != POLICY_HASH:
        raise ValueError
    journal = Journal(Path('/state'), admission['expires_at'])
    # The unchanged adapter validates trusted project/deployment, endpoint,
    # 4096-byte/3-second/8-second limits, exact response guards and retry=None.
    redactor = GoogleSDPContextRedactor(admission['project_id'], budget=ContentAttemptBudget(174))
    with Server(('0.0.0.0', 4003), Handler) as server:
        server.key, server.journal, server.redactor = admission['key'], journal, redactor
        server.timeout, server.failed, server.diagnostic = 1, False, None
        stop = [False]
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
        while not stop[0] and not server.failed and time.time() < admission['expires_at']:
            server.handle_request()
    print(json.dumps({'scope': scope, 'reserved_sdk_slots': journal.reserved(),
                      'sdk_attempts': sum(redactor.operation_counts.values()), 'metadata_sdk_attempts': 0,
                      'retries': 0, 'authority_changed': False, 'diagnostic': server.diagnostic}))
    if server.failed:
        raise SystemExit(1)


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 1:
        raise SystemExit('demo:arguments_rejected')
    try:
        run()
    except Exception:
        print('{"status":"BLOCKED","code":"REDACTOR_BRIDGE_ADMISSION_FAILURE","automatic_retry":false}')
        raise SystemExit(1) from None
