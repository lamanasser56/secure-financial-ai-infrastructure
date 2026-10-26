"""The disposable Terraform plan cannot update or destroy an existing resource."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from operator_cluster import allowed_plan, create_cluster


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN,
            'source_commit': 'a' * 40, 'deadline_at': '2026-10-27T00:00:00+00:00'}


class TerraformFixture:
    def __init__(self, *, actions=None):
        self.actions = actions or ['create']
        self.commands = []

    def __call__(self, command, *, data_dir):
        self.commands.append(command)
        if command[1] == 'plan':
            Path(next(value[5:] for value in command if value.startswith('-out='))).write_bytes(b'plan')
        if command[1] == 'show':
            return json.dumps({'format_version': '1.2', 'resource_changes': [
                {'mode': 'managed', 'change': {'actions': self.actions}}]})
        if command[1] == 'output':
            return json.dumps({'platform': {'value': {
                'node_service_account': 'node@' + PROJECT + '.iam.gserviceaccount.com',
                'cluster_name': 'agent-platform', 'cluster_location': 'us-east1-b',
                'attestor': 'projects/fixture/attestors/assessment',
                'attestor_key_version': 'projects/fixture/cryptoKeyVersions/1'}}})
        return ''


def cloud(*args):
    if args[:2] == ('projects', 'describe'):
        return {'projectId': PROJECT, 'projectNumber': '123456789012',
                'labels': {'assessment_run': RUN}, 'lifecycleState': 'ACTIVE'}
    raise AssertionError(args)


class OperatorClusterTest(unittest.TestCase):
    def test_create_only_private_plan_and_exact_project(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / 'initial-manifest.json').write_text(json.dumps(MANIFEST))
            (run_dir / 'evidence').mkdir()
            (run_dir / 'evidence/project-setup.json').write_text(json.dumps({
                'run_id': RUN, 'billing_linked': True}))
            (run_dir / 'evidence/janitor-armed.json').write_text(json.dumps({
                'run_id': RUN, 'watch_step_in_progress': True}))
            runner = TerraformFixture()
            receipt = create_cluster(MANIFEST, run_dir, gke_version='1.35.1-gke.100',
                                     cloud=cloud, runner=runner,
                                     now=datetime(2026, 10, 26, tzinfo=timezone.utc))
            self.assertEqual(receipt['created_resource_count'], 1)
            self.assertEqual([command[1] for command in runner.commands],
                             ['init', 'plan', 'show', 'apply', 'output'])
            self.assertIn('-var=assessment_mode=true', runner.commands[1])
            self.assertIn('-var=deletion_protection=false', runner.commands[1])
            self.assertTrue((run_dir / 'evidence/cluster-setup.json').exists())

    def test_noncreate_plan_refuses_apply(self):
        for actions in (['update'], ['delete'], ['create', 'delete'], ['no-op']):
            with self.subTest(actions=actions):
                with self.assertRaisesRegex(RuntimeError, 'noncreate'):
                    allowed_plan({'format_version': '1.2', 'resource_changes': [
                        {'mode': 'managed', 'change': {'actions': actions}}]})

    def test_unarmed_janitor_refuses_terraform(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / 'initial-manifest.json').write_text(json.dumps(MANIFEST))
            runner = TerraformFixture()
            with self.assertRaisesRegex(ValueError, 'janitor_must_be_armed'):
                create_cluster(MANIFEST, run_dir, gke_version='1.35.1-gke.100',
                               cloud=cloud, runner=runner,
                               now=datetime(2026, 10, 26, tzinfo=timezone.utc))
            self.assertEqual(runner.commands, [])


if __name__ == '__main__':
    unittest.main()
