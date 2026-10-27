"""Cleanup requires a destroy-only plan, drained disks and a full janitor receipt."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from cloud_wait import Waiter
from operator_cleanup import destroy


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 26, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class TerraformFixture:
    def __init__(self, actions, *, data_read=False):
        self.actions = actions
        self.data_read = data_read
        self.commands = []

    def __call__(self, command, *, data_dir, cwd):
        self.commands.append(command[1])
        if command[1] == 'plan':
            Path(next(value[5:] for value in command if value.startswith('-out='))).write_bytes(b'plan')
        if command[1] == 'show':
            changes = [{'mode': 'managed', 'change': {'actions': self.actions}}]
            if self.data_read:
                changes.append({'mode': 'data', 'change': {'actions': ['delete']}})
            return json.dumps({'format_version': '1.2', 'resource_changes': changes})
        return ''


class CloudFixture:
    """Disks and forwarding rules disappear a few polls after the destroy."""

    def __init__(self, *, lingering_polls=2, claim_disk=False):
        self.lingering_polls = lingering_polls
        self.claim_disk = claim_disk
        self.commands = []

    def __call__(self, *args, timeout=None):
        self.commands.append(args)
        if args[:3] == ('compute', 'disks', 'delete'):
            self.claim_disk = False
            return {}
        if args[:3] == ('compute', 'disks', 'list') and self.claim_disk:
            return [{'name': 'pvc-1', 'zone': 'zones/us-east1-b',
                     'description': '{"kubernetes.io/created-for/pvc/name":"data-postgres-0"}'}]
        if args[:3] == ('compute', 'forwarding-rules', 'list') and self.lingering_polls:
            self.lingering_polls -= 1
            return [{'name': 'still-deleting'}]
        if 'list' in args:
            return []
        raise AssertionError(args)


class KubeFixture:
    def __init__(self, *, volume_polls=1):
        self.volume_polls = volume_polls
        self.commands = []

    def __call__(self, command):
        self.commands.append(command[2:])
        if command[2:4] == ['get', 'namespaces']:
            return 'namespace/platform\nnamespace/apps\n'
        if command[2:4] == ['get', 'persistentvolumes']:
            self.volume_polls -= 1
            return json.dumps({'items': [{}] if self.volume_polls > 0 else []})
        return ''


class OperatorCleanupTest(unittest.TestCase):
    def private_state(self, directory, *, kubeconfig=True):
        tf = directory / 'terraform'
        (tf / 'data').mkdir(parents=True)
        (tf / 'config' / 'root').mkdir(parents=True)
        (tf / 'terraform.tfstate').write_text('{}')
        if kubeconfig:
            (directory / 'kube').mkdir()
            (directory / 'kube' / 'kubeconfig').write_text('{}')

    def run_destroy(self, path, runner, *, call=None, kube=None, janitor=None):
        clock = Clock()
        return destroy(MANIFEST, path, runner=runner, cloud=lambda *args: None,
                       call=call or CloudFixture(), kube=kube or KubeFixture(),
                       waiter=Waiter(clock=clock, sleep=clock.sleep),
                       janitor=janitor or (lambda *args, **kwargs: {'result': 'PASS'}))

    def test_drain_destroy_wait_for_absence_then_janitor(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.private_state(path)
            runner, cloud, kube = TerraformFixture(['delete']), CloudFixture(), KubeFixture(volume_polls=2)
            order = []
            result = self.run_destroy(path, runner, call=cloud, kube=kube,
                                      janitor=lambda *args, **kwargs: order.append(len(cloud.commands)) or
                                      {'result': 'PASS'})
            self.assertEqual(result['terraform_destroyed_resources'], 1)
            self.assertEqual(result['volumes'], 'drained')
            self.assertEqual(runner.commands, ['plan', 'show', 'apply'])
            self.assertIn(['delete', 'namespace/platform', 'namespace/apps', '--wait=false'], kube.commands)
            self.assertEqual(sum(1 for args in kube.commands if args[:2] == ['get', 'persistentvolumes']), 2)
            forwarding = [args for args in cloud.commands if args[:3] == ('compute', 'forwarding-rules', 'list')]
            self.assertEqual(len(forwarding), 3)  # Polled until the lingering rule was gone.
            self.assertEqual(order, [len(cloud.commands)])

    def test_orphan_claim_disk_is_deleted_when_the_cluster_was_unreachable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.private_state(path, kubeconfig=False)
            cloud = CloudFixture(claim_disk=True)
            result = self.run_destroy(path, TerraformFixture(['delete']), call=cloud)
            self.assertEqual(result['volumes'], 'no_cluster_access')
            self.assertEqual(result['orphan_claim_disks_deleted'], 1)
            self.assertIn(('compute', 'disks', 'delete', 'pvc-1', '--zone=us-east1-b',
                           '--project=' + PROJECT, '--quiet'), cloud.commands)

    def test_data_sources_leaving_state_do_not_block_the_destroy(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.private_state(path)
            result = self.run_destroy(path, TerraformFixture(['delete'], data_read=True))
            self.assertEqual(result['terraform_destroyed_resources'], 1)

    def test_update_in_destroy_plan_refuses_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.private_state(path)
            runner = TerraformFixture(['update'])
            with self.assertRaisesRegex(RuntimeError, 'nondelete'):
                self.run_destroy(path, runner, janitor=lambda *args, **kwargs: self.fail('janitor called'))
            self.assertEqual(runner.commands, ['plan', 'show'])


if __name__ == '__main__':
    unittest.main()
