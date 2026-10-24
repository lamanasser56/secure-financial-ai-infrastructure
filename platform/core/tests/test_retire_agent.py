"""`platform_secrets --retire-agent`: removes only one retired agent's key entries; idempotent; never prints values."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from agent_platform import platform_secrets

FAKE_KUBECTL = '''#!{python}
import base64, json, sys
store = {store!r}
data = json.load(open(store))
args = sys.argv[1:]
if 'get' in args:
    ns, name = args[args.index('-n') + 1], args[args.index('secret') + 1]
    item = data.get(ns + '/' + name)
    print(json.dumps(item) if item else '')
elif 'apply' in args:
    for item in json.load(sys.stdin)['items']:
        data[item['metadata']['namespace'] + '/' + item['metadata']['name']] = item
    json.dump(data, open(store, 'w'))
    open(store + '.applied', 'a').write('1\\n')
'''

SECRET_VALUE = 'sk-super-secret-value-123'


def secret(namespace, name, key, value):
    return platform_secrets.secret(namespace, name, {key: json.dumps(value)})


class RetireAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = root / 'store.json'
        bootstrap = {'boundary_contract': 2, 'master_key': 'master-' + SECRET_VALUE, 'virtual_keys': [
            {'alias': 'boundary-app-infrastructure', 'key': 'sk-a', 'max_budget': 2.5},
            {'alias': 'boundary-agent-financial', 'key': 'sk-f', 'max_budget': 5.0},
            {'alias': 'boundary-agent-hello', 'key': SECRET_VALUE, 'max_budget': 0.5}]}
        clients = {'app': 'a' * 64, 'ops': 'b' * 64, 'agent-financial': 'c' * 64, 'agent-hello': 'd' * 64}
        self.store.write_text(json.dumps({
            'platform/bootstrap': secret('platform', 'bootstrap', 'bootstrap.json', bootstrap),
            'platform/redactor': secret('platform', 'redactor', 'clients.json', clients),
            'platform/gateway-boundary': secret('platform','gateway-boundary','boundary.json', {'clients':{'agent-hello':{'external_key':'gw-'+SECRET_VALUE},'agent-financial':{'external_key':'kept'}}}),
            'apps/financial-frontdoor':secret('apps','financial-frontdoor','frontdoor.json',{'agent_name':'financial','broker_clients':{},'worker_keys':{}})}))
        self.kubectl = root / 'kubectl'
        self.kubectl.write_text(FAKE_KUBECTL.format(python=os.sys.executable, store=str(self.store)))
        self.kubectl.chmod(self.kubectl.stat().st_mode | stat.S_IEXEC)

        # In-process fake kubectl: tests never spawn a command or use a real kubeconfig.
        from unittest.mock import patch
        from types import SimpleNamespace
        def fake_run(command, **kwargs):
            data=json.loads(self.store.read_text())
            if 'get' in command:
                ns=command[command.index('-n')+1];name=command[command.index('secret')+1]
                return SimpleNamespace(stdout=json.dumps(data[ns+'/'+name]) if ns+'/'+name in data else '',returncode=0)
            for item in json.loads(kwargs['input'])['items']:
                data[item['metadata']['namespace']+'/'+item['metadata']['name']]=item
            self.store.write_text(json.dumps(data))
            applied=Path(str(self.store)+'.applied')
            with applied.open('a') as handle:handle.write('1\n')
            return SimpleNamespace(stdout='',returncode=0)
        self.fake=patch.object(platform_secrets.subprocess,'run',side_effect=fake_run)
        self.fake.start();self.addCleanup(self.fake.stop)

    def run_retire(self, name='hello'):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            platform_secrets.retire(str(self.kubectl), name)
        return out.getvalue()

    def decode(self, key, field):
        return json.loads(base64.b64decode(json.loads(self.store.read_text())[key]['data'][field]))

    def applies(self):
        path = Path(str(self.store) + '.applied')
        return len(path.read_text().split()) if path.exists() else 0

    def test_only_the_retired_agents_entries_are_removed(self):
        before_boot = self.decode('platform/bootstrap', 'bootstrap.json')
        before_clients = self.decode('platform/redactor', 'clients.json')
        output = self.run_retire()
        boot = self.decode('platform/bootstrap', 'bootstrap.json')
        clients = self.decode('platform/redactor', 'clients.json')
        self.assertEqual([k['alias'] for k in boot['virtual_keys']], ['boundary-app-infrastructure', 'boundary-agent-financial'])
        self.assertEqual(sorted(clients), ['agent-financial', 'app', 'ops'])
        self.assertEqual(boot['master_key'], before_boot['master_key'])  # nothing else is rotated or removed
        self.assertEqual(boot['virtual_keys'][:2], before_boot['virtual_keys'][:2])
        self.assertEqual({k: v for k, v in clients.items() if k != 'agent-hello'},
                         {k: v for k, v in before_clients.items() if k != 'agent-hello'})
        self.assertEqual(json.loads(output)['result'], 'RETIRED')

    def test_no_value_is_printed(self):
        output = self.run_retire()
        for value in (SECRET_VALUE, 'master-' + SECRET_VALUE, 'd' * 64):
            self.assertNotIn(value, output)

    def test_second_run_changes_nothing(self):
        self.run_retire()
        snapshot, applied = self.store.read_text(), self.applies()
        output = self.run_retire()
        self.assertEqual(json.loads(output)['result'], 'UNCHANGED')
        self.assertEqual((self.store.read_text(), self.applies()), (snapshot, applied))

    def test_a_declared_agent_cannot_be_retired(self):
        with self.assertRaisesRegex(SystemExit, 'agent_still_declared'):
            self.run_retire('financial')
        self.assertEqual(self.applies(), 0)

    def test_reserved_and_malformed_names_are_rejected(self):
        for name in ('platform', 'ops', 'app', 'X', '../x', 'a b'):
            with self.subTest(name), self.assertRaisesRegex(SystemExit, 'name_rejected'):
                self.run_retire(name)

    def test_missing_platform_secrets_fail_closed(self):
        self.store.write_text('{}')
        with self.assertRaisesRegex(SystemExit, 'platform_secrets_missing'):
            self.run_retire()


if __name__ == '__main__':
    unittest.main()
