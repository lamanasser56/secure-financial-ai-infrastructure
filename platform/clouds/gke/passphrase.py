#!/usr/bin/env python3
"""`make passphrase-check` / `make passphrase`: the owner's operations-approval passphrase, nothing else. Owner only.

  check     type the passphrase once; it is compared with operator_secret_scrypt in Secret apps/app.
            Prints only {"match": true|false}.
  replace   type a new passphrase twice (at least 12 characters, no leading/trailing spaces, both the same). Only
            operator_secret_scrypt in Secret apps/app is replaced (new random salt, same scrypt n=2**14 r=8 p=1);
            every other byte of the Secret's data stays as it was. Applied with `kubectl apply -f -` on stdin. If the
            front door (apps/app) has at least one ready replica, it is rolled out so it loads the new hash; otherwise
            nothing is restarted (a rollout would wait on Pods that cannot start) and the new hash loads on its next start.
            Prints only {"result": "PASSPHRASE_REPLACED", "values_printed": false, "front_door": "restarted" | "not_ready",
            "note": ...}.

Both refuse unless stdin is a terminal. The Secret travels only through kubectl pipes and this process's memory: it is
never printed, logged or written to disk. Nothing else is generated or rotated (this is not `make secrets --rotate`).
"""
import base64
import getpass
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sys

HERE = Path(__file__).resolve().parent
NAMESPACE, NAME, KEY, FIELD = 'apps', 'app', 'app.json', 'operator_secret_scrypt'
MIN_LENGTH = 12
LAST_APPLIED = 'kubectl.kubernetes.io/last-applied-configuration'


class Refused(SystemExit):
    pass


def scrypt(passphrase, salt):
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def matches(passphrase, stored):
    """The same comparison the front door makes on approve (app.py)."""
    return hmac.compare_digest(scrypt(passphrase, bytes.fromhex(stored['salt'])), stored['hash'])


def replaced_secret(live, passphrase):
    """The live Secret object -> a manifest identical in data except FIELD inside app.json, proven byte-for-byte."""
    old_text = base64.b64decode(live['data'][KEY]).decode()
    config = json.loads(old_text)
    old_value = config[FIELD]
    salt = secrets.token_bytes(16)
    config[FIELD] = {'salt': salt.hex(), 'hash': scrypt(passphrase, salt)}
    new_text = json.dumps(config)
    if new_text.replace(json.dumps(config[FIELD]), json.dumps(old_value), 1) != old_text:
        raise Refused('passphrase: refused: app.json would change beyond ' + FIELD + ' (nothing applied)')
    meta = live['metadata']
    annotations = {k: v for k, v in (meta.get('annotations') or {}).items() if k != LAST_APPLIED}
    metadata = dict({'name': NAME, 'namespace': NAMESPACE}, **({'labels': meta['labels']} if meta.get('labels') else {}),
                    **({'annotations': annotations} if annotations else {}))
    data = dict(live['data'], **{KEY: base64.b64encode(new_text.encode()).decode()})
    return {'apiVersion': 'v1', 'kind': 'Secret', 'type': live.get('type', 'Opaque'), 'metadata': metadata, 'data': data}


class Passphrase:
    def __init__(self, *, kubectl, isatty=sys.stdin.isatty, ask=getpass.getpass, out=print):
        """kubectl(*args, input=None) -> (returncode, stdout); its stderr is never shown (it may echo the object)."""
        self.kubectl, self.isatty, self.ask, self.out = kubectl, isatty, ask, out

    def require_tty(self):
        if not self.isatty():
            raise Refused('passphrase: refused: stdin is not a terminal (run it yourself in a terminal; nothing was read)')

    def live(self):
        rc, out = self.kubectl('-n', NAMESPACE, 'get', 'secret', NAME, '-o', 'json')
        if rc != 0 or not out.strip():
            raise Refused('passphrase: refused: cannot read Secret apps/app (is the cluster reachable? run make secrets once)')
        live = json.loads(out)
        if KEY not in (live.get('data') or {}) or FIELD not in json.loads(base64.b64decode(live['data'][KEY])):
            raise Refused('passphrase: refused: Secret apps/app has no ' + FIELD)
        return live

    def check(self):
        self.require_tty()
        typed = self.ask('Approval passphrase: ')
        stored = json.loads(base64.b64decode(self.live()['data'][KEY]))[FIELD]
        self.out(json.dumps({'match': matches(typed, stored)}))
        return 0

    def replace(self):
        self.require_tty()
        first = self.ask('New approval passphrase: ')
        if len(first) < MIN_LENGTH:
            raise Refused('passphrase: refused: shorter than %d characters (nothing changed)' % MIN_LENGTH)
        if first != first.strip():
            raise Refused('passphrase: refused: leading or trailing spaces (nothing changed)')
        if self.ask('Type it again: ') != first:
            raise Refused('passphrase: refused: the two entries differ (nothing changed)')
        manifest = replaced_secret(self.live(), first)
        rc, _ = self.kubectl('apply', '-f', '-', input=json.dumps(manifest))
        if rc != 0:
            raise Refused('passphrase: refused: kubectl apply failed (Secret unchanged)')
        # Roll out only a front door that is serving: with no ready replica (scaled to 0, still starting, crash-looping)
        # `rollout status` would wait out its timeout and report a failure for a Secret change that already succeeded.
        rc, ready = self.kubectl('-n', NAMESPACE, 'get', 'deployment', NAME, '-o', 'jsonpath={.status.readyReplicas}')
        if rc == 0 and ready.strip().isdigit() and int(ready.strip()) >= 1:
            for args in (('rollout', 'restart', 'deployment/' + NAME), ('rollout', 'status', 'deployment/' + NAME, '--timeout=300s')):
                if self.kubectl('-n', NAMESPACE, *args)[0] != 0:
                    raise Refused('passphrase: the Secret was replaced, but the apps/app rollout failed; run '
                                  'kubectl -n apps rollout restart deployment/app')
            front_door, note = 'restarted', 'apps/app was restarted and now uses the new passphrase'
        else:
            front_door, note = 'not_ready', 'apps/app has no ready replica, so it was not restarted; the new hash loads on its next start'
        self.out(json.dumps({'result': 'PASSPHRASE_REPLACED', 'values_printed': False, 'front_door': front_door, 'note': note}))
        return 0


def main(argv):
    if argv not in (['check'], ['replace']):
        raise SystemExit('usage: passphrase.py check|replace')
    sys.path.insert(0, str(HERE))
    import lifecycle

    def kubectl(*args, input=None):
        result = lifecycle.kubectl(*args, check=False, capture=True, input=input)
        return result.returncode, result.stdout

    tool = Passphrase(kubectl=kubectl)
    tool.require_tty()  # before any cloud call
    lifecycle.kubeconfig()
    try:
        code = tool.check() if argv == ['check'] else tool.replace()
    except Refused as refused:
        print(refused.code)
        code = 2
    raise SystemExit(code)


if __name__ == '__main__':
    main(sys.argv[1:])
