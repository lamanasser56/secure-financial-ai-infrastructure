"""Cleanup requires a destroy-only plan and a full janitor receipt."""
import json
from pathlib import Path
import tempfile
import unittest

from operator_cleanup import destroy


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN}


class TerraformFixture:
    def __init__(self, actions):
        self.actions = actions
        self.commands = []

    def __call__(self, command, *, data_dir):
        self.commands.append(command[1])
        if command[1] == 'plan':
            Path(next(value[5:] for value in command if value.startswith('-out='))).write_bytes(b'plan')
        if command[1] == 'show':
            return json.dumps({'format_version': '1.2', 'resource_changes': [
                {'mode': 'managed', 'change': {'actions': self.actions}}]})
        return ''


class OperatorCleanupTest(unittest.TestCase):
    def private_state(self, directory):
        tf = directory / 'terraform'
        tf.mkdir()
        (tf / 'data').mkdir()
        (tf / 'terraform.tfstate').write_text('{}')

    def test_destroy_then_janitor(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.private_state(path)
            runner = TerraformFixture(['delete'])
            called = []
            result = destroy(MANIFEST, path, runner=runner,
                             cloud=lambda *args: called.append(('cloud', args)),
                             janitor=lambda *args, **kwargs: {'result': 'PASS'})
            self.assertEqual(result['terraform_destroyed_resources'], 1)
            self.assertEqual(runner.commands, ['plan', 'show', 'apply'])
            self.assertEqual(called, [('cloud', (PROJECT, RUN))])

    def test_update_in_destroy_plan_refuses_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.private_state(path)
            runner = TerraformFixture(['update'])
            with self.assertRaisesRegex(RuntimeError, 'nondelete'):
                destroy(MANIFEST, path, runner=runner, cloud=lambda *args: None,
                        janitor=lambda *args, **kwargs: self.fail('janitor called'))
            self.assertEqual(runner.commands, ['plan', 'show'])


if __name__ == '__main__':
    unittest.main()
