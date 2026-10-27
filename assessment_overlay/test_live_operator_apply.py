"""The seed completes before redactor deployment and the schema before rollouts."""
from datetime import datetime, timedelta, timezone
import unittest

from cloud_wait import Waiter
from operator_apply import run_apply, runtime_digests


def waiter():
    now = [datetime(2026, 10, 26, tzinfo=timezone.utc)]

    def sleep(seconds):
        now[0] += timedelta(seconds=seconds)
    return Waiter(None, clock=lambda: now[0], sleep=sleep)


class OperatorApplyTest(unittest.TestCase):
    def test_dependency_order_and_addon_apply(self):
        stages = [[] for _ in range(7)]
        stages[0] = [{'kind': 'Namespace', 'metadata': {'name': 'platform'}}]
        stages[1] = [{'kind': 'NetworkLogging', 'metadata': {'name': 'default'}},
                     {'kind': 'ConfigMap', 'metadata': {'name': 'settings', 'namespace': 'platform'}}]
        stages[4] = [{'kind': 'StatefulSet', 'metadata': {'name': 'postgres', 'namespace': 'platform'}}]
        stages[5] = [{'kind': 'Job', 'metadata': {'name': 'assessment-sdp-seed', 'namespace': 'platform'}}]
        stages[6] = [{'kind': 'Deployment', 'metadata': {'name': 'redactor', 'namespace': 'platform'},
                      'spec': {'replicas': 1}}]
        commands = []

        def run(command, *, input=None):
            commands.append((command, input))
            return ''

        count = run_apply('/private/kubeconfig', stages, kubectl_path='/pin/kubectl', run=run,
                          waiter=waiter())
        self.assertEqual(count, 6)
        self.assertEqual(commands[0][0][2:], ['get', '--raw=/readyz'])
        strings = [' '.join(command) for command, _ in commands]
        seed = next(i for i, command in enumerate(strings) if 'job/assessment-sdp-seed' in command)
        redactor = next(i for i, (_, data) in enumerate(commands) if data and 'name: redactor' in data)
        schema = next(i for i, command in enumerate(strings) if 'job/schema' in command)
        rollout = next(i for i, command in enumerate(strings) if 'deployment/redactor' in command)
        self.assertLess(seed, redactor)
        self.assertLess(redactor, schema)
        self.assertLess(schema, rollout)
        self.assertEqual(len([command for command, _ in commands if '--server-side' not in command
                              and 'apply' in command]), 1)

    def test_unready_api_and_transient_apply_failures_are_retried(self):
        stages = [[] for _ in range(7)]
        stages[0] = [{'kind': 'Namespace', 'metadata': {'name': 'platform'}}]
        failures = {'readyz': 2, 'apply': 1}
        commands = []

        def run(command, *, input=None):
            commands.append(command[2])
            kind = 'readyz' if command[2:] == ['get', '--raw=/readyz'] else command[2]
            if failures.get(kind):
                failures[kind] -= 1
                raise RuntimeError('assessment:kubectl_failed:' + command[2])
            return ''

        run_apply('/private/kubeconfig', stages, kubectl_path='/pin/kubectl', run=run, waiter=waiter())
        self.assertEqual(commands[:5], ['get', 'get', 'get', 'apply', 'apply'])

    def test_running_images_must_match_every_disposable_digest(self):
        registry = 'us-east1-docker.pkg.dev/sfai-assess-example/sdp-evaluation-images/'
        manifest = {'runtime_registry': registry,
                    'image_digests': {'app': 'app@sha256:' + 'a' * 64,
                                      'redactor': 'redactor@sha256:' + 'b' * 64}}
        def pod(name, image, image_id):
            return {'metadata': {'namespace': 'platform'},
                    'spec': {'containers': [{'name': name, 'image': image}]},
                    'status': {'phase': 'Running', 'containerStatuses': [
                        {'name': name, 'imageID': image_id}]}}
        app = registry + manifest['image_digests']['app']
        redactor = registry + manifest['image_digests']['redactor']
        pods = {'items': [pod('app', app, 'docker-pullable://' + app),
                          pod('redactor', redactor, 'docker-pullable://' + redactor)]}
        self.assertEqual(runtime_digests(pods, manifest, {'platform'}), ['app', 'redactor'])
        with self.assertRaisesRegex(RuntimeError, 'inventory_incomplete'):
            runtime_digests({'items': pods['items'][:1]}, manifest, {'platform'})
        pods['items'][1]['status']['containerStatuses'][0]['imageID'] = 'docker-pullable://wrong@sha256:' + 'c' * 64
        with self.assertRaisesRegex(RuntimeError, 'digest_mismatch'):
            runtime_digests(pods, manifest, {'platform'})
        pods['items'][1]['spec']['containers'][0]['image'] = 'external.example/redactor@sha256:' + 'b' * 64
        with self.assertRaisesRegex(RuntimeError, 'non_disposable_runtime_image'):
            runtime_digests(pods, manifest, {'platform'})


if __name__ == '__main__':
    unittest.main()
