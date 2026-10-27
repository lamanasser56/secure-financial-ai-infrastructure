"""The disposable Terraform plan cannot update or destroy an existing resource."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from cloud_wait import Waiter
from operator_cluster import TERRAFORM_SOURCE, allowed_plan, create_cluster, private_config
from render_live_bundle import ROOT


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN,
            'source_commit': 'a' * 40, 'deadline_at': '2026-10-27T00:00:00+00:00'}


class TerraformFixture:
    def __init__(self, *, actions=None, plans=None, apply_failures=0):
        self.actions = actions or ['create']
        self.plans = plans
        self.apply_failures = apply_failures
        self.commands = []

    def __call__(self, command, *, data_dir, cwd, timeout=None):
        self.commands.append(command)
        if command[1] == 'plan':
            Path(next(value[5:] for value in command if value.startswith('-out='))).write_bytes(b'plan')
        if command[1] == 'show':
            changes = self.plans.pop(0) if self.plans else [
                {'mode': 'managed', 'change': {'actions': self.actions}}]
            return json.dumps({'format_version': '1.2', 'resource_changes': changes})
        if command[1] == 'apply' and self.apply_failures:
            self.apply_failures -= 1
            raise RuntimeError('assessment:terraform_failed:apply')
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


def create(run_dir, runner):
    (run_dir / 'initial-manifest.json').write_text(json.dumps(MANIFEST))
    (run_dir / 'evidence').mkdir()
    (run_dir / 'evidence/project-setup.json').write_text(json.dumps({
        'run_id': RUN, 'billing_linked': True}))
    (run_dir / 'evidence/janitor-armed.json').write_text(json.dumps({
        'run_id': RUN, 'watch_step_in_progress': True}))
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    return create_cluster(MANIFEST, run_dir, gke_version='1.35.1-gke.100', cloud=cloud, runner=runner,
                          now=now, waiter=Waiter(MANIFEST['deadline_at'], clock=lambda: now,
                                                 sleep=lambda seconds: None),
                          configure=lambda tf_dir: tf_dir)


CREATE = {'mode': 'managed', 'change': {'actions': ['create']}}
NOOP = {'mode': 'managed', 'change': {'actions': ['no-op']}}
DEFERRED_READ = {'mode': 'data', 'change': {'actions': ['read']}}


class OperatorClusterTest(unittest.TestCase):
    def test_create_only_private_plan_and_exact_project(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            runner = TerraformFixture()
            receipt = create(run_dir, runner)
            self.assertEqual(receipt['created_resource_count'], 1)
            self.assertEqual(receipt['apply_attempts'], 1)
            self.assertEqual([command[1] for command in runner.commands],
                             ['init', 'plan', 'show', 'apply', 'output'])
            self.assertIn('-var=assessment_mode=true', runner.commands[1])
            self.assertIn('-var=deletion_protection=false', runner.commands[1])
            self.assertFalse([command for command in runner.commands if '-backend=false' in command])
            self.assertTrue((run_dir / 'evidence/cluster-setup.json').exists())

    def test_deferred_data_read_is_not_a_mutation(self):
        self.assertEqual(allowed_plan({'format_version': '1.2',
                                       'resource_changes': [CREATE, CREATE, DEFERRED_READ]}), 2)
        with self.assertRaisesRegex(RuntimeError, 'empty'):
            allowed_plan({'format_version': '1.2', 'resource_changes': [DEFERRED_READ]})

    def test_failed_apply_resumes_with_a_create_only_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = TerraformFixture(plans=[[CREATE, CREATE, DEFERRED_READ], [NOOP, CREATE, DEFERRED_READ]],
                                      apply_failures=1)
            receipt = create(Path(temp), runner)
            self.assertEqual(receipt['created_resource_count'], 2)
            self.assertEqual(receipt['apply_attempts'], 2)
            self.assertEqual([command[1] for command in runner.commands],
                             ['init', 'plan', 'show', 'apply', 'plan', 'show', 'apply', 'output'])

    def test_resume_stops_when_nothing_is_left_to_create(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = TerraformFixture(plans=[[CREATE], [NOOP]], apply_failures=1)
            receipt = create(Path(temp), runner)
            self.assertEqual([command[1] for command in runner.commands],
                             ['init', 'plan', 'show', 'apply', 'plan', 'show', 'output'])
            self.assertEqual(receipt['apply_attempts'], 2)

    def test_resume_still_refuses_replacement_and_attempts_are_bounded(self):
        replace = {'mode': 'managed', 'change': {'actions': ['delete', 'create']}}
        with tempfile.TemporaryDirectory() as temp:
            runner = TerraformFixture(plans=[[CREATE], [replace]], apply_failures=1)
            with self.assertRaisesRegex(RuntimeError, 'noncreate'):
                create(Path(temp), runner)
        with tempfile.TemporaryDirectory() as temp:
            runner = TerraformFixture(apply_failures=5)
            with self.assertRaisesRegex(RuntimeError, 'terraform_failed:apply'):
                create(Path(temp), runner)
            self.assertEqual([command[1] for command in runner.commands].count('apply'), 3)

    def test_private_config_copies_tracked_terraform_and_overrides_only_the_backend(self):
        with tempfile.TemporaryDirectory() as temp:
            tf_dir = Path(temp)
            root = private_config(tf_dir)
            for name in ('root/backend.tf', 'root/main.tf', 'root/.terraform.lock.hcl', 'module/main.tf'):
                self.assertEqual((tf_dir / 'config' / name).read_bytes(),
                                 (ROOT / TERRAFORM_SOURCE / name).read_bytes())
            override = (root / 'backend_override.tf').read_text()
            self.assertIn('backend "local"', override)
            self.assertIn(json.dumps(str(tf_dir / 'terraform.tfstate')), override)
            self.assertFalse((ROOT / TERRAFORM_SOURCE / 'root/backend_override.tf').exists())

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
                               now=datetime(2026, 10, 26, tzinfo=timezone.utc),
                               configure=lambda tf_dir: tf_dir)
            self.assertEqual(runner.commands, [])


if __name__ == '__main__':
    unittest.main()
