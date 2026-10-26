"""Trusted baseline transport and workflow integration; no GitHub/cloud/network calls."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('image_planner', ROOT / 'scripts/plan-image-builds.py')
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)
REPO = 'example/current-source'


def successful_run(**changes):
    return {'id': 7, 'status': 'completed', 'conclusion': 'success', 'head_branch': 'main',
            'event': 'workflow_run', 'path': '.github/workflows/agent-platform-images.yml',
            'repository': {'full_name': REPO}, 'head_repository': {'full_name': REPO}, **changes}


def archive(value=b'{"schema":1}', name='input-plan.json'):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        zipped.writestr(name, value)
    return output.getvalue()


def reader(*, runs=None, artifacts=None, raw=None):
    def read(route, *, binary=False):
        if '/workflows/' in route:
            return {'workflow_runs': [successful_run()] if runs is None else runs}
        if '/runs/' in route:
            return {'total_count': 1, 'artifacts': [{'id': 19, 'name': 'image-input-plan', 'expired': False, 'size_in_bytes': 500}]} if artifacts is None else artifacts
        if '/artifacts/19/zip' in route and binary:
            return archive() if raw is None else raw
        raise AssertionError('unexpected API route')
    return Mock(side_effect=read)


class BaselineTransport(unittest.TestCase):
    def test_only_successful_same_repository_image_workflow_runs_are_trusted(self):
        self.assertTrue(planner.trusted_run(successful_run(), REPO, '99'))
        for changes in [dict(id=99), dict(id='7'), dict(status='in_progress'), dict(conclusion='failure'),
                        dict(head_branch='topic'), dict(event='pull_request'), dict(path='.github/workflows/ci.yml'),
                        dict(repository=None), dict(head_repository={'full_name': 'other/fork'})]:
            self.assertFalse(planner.trusted_run(successful_run(**changes), REPO, '99'), changes)

    def test_complete_plan_is_read_only_from_the_expected_artifact(self):
        read = reader()
        self.assertEqual(planner.previous_plan(REPO, '99', read=read), b'{"schema":1}')
        self.assertEqual(len(read.call_args_list), 3)
        self.assertTrue(read.call_args_list[-1].kwargs['binary'])

    def test_expired_ambiguous_truncated_and_missing_artifacts_do_not_advance_baseline(self):
        for artifacts in [{'total_count': 0, 'artifacts': []}, {'total_count': 3, 'artifacts': []},
                          {'total_count': 1, 'artifacts': [{'id': 19, 'name': 'image-input-plan', 'expired': True, 'size_in_bytes': 500}]},
                          {'total_count': 2, 'artifacts': [{'id': i, 'name': 'image-input-plan', 'expired': False, 'size_in_bytes': 500} for i in [19, 20]]},
                          {'total_count': 1, 'artifacts': [None]}]:
            self.assertIsNone(planner.previous_plan(REPO, '99', read=reader(artifacts=artifacts)))

    def test_failed_ci_only_fork_and_current_runs_cannot_supply_a_baseline(self):
        for changes in [dict(conclusion='failure'), dict(path='.github/workflows/ci.yml'), dict(event='pull_request'),
                        dict(id=99), dict(head_repository={'full_name': 'other/fork'})]:
            read = reader(runs=[successful_run(**changes)])
            self.assertIsNone(planner.previous_plan(REPO, '99', read=read))
            self.assertEqual(read.call_count, 1)

    def test_bad_archives_and_paths_are_never_extracted_or_executed(self):
        for raw in [b'not a zip', archive(name='../input-plan.json'), archive(name='plan.py'), archive(b'[]'), archive(b'{')]:
            self.assertIsNone(planner.previous_plan(REPO, '99', read=reader(raw=raw)))
        with self.assertRaises(ValueError):
            planner.archive_plan(archive(b'{}', name='../../escape'))

    def test_network_failure_or_unknown_repository_rebuilds_instead_of_skipping(self):
        self.assertIsNone(planner.previous_plan(REPO, '99', read=Mock(side_effect=subprocess.CalledProcessError(1, 'gh'))))
        read = Mock()
        self.assertIsNone(planner.previous_plan('../outside', '99', read=read))
        read.assert_not_called()


class Invocation(unittest.TestCase):
    def test_force_never_reads_a_baseline_and_passes_exact_source_without_a_shell(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(planner.subprocess, 'check_output', return_value='a'*40), patch.object(planner.subprocess, 'run', return_value=Mock(stdout='{"include":[]}')) as run:
            read = Mock(side_effect=AssertionError('force must not fetch'))
            output = Path(temp) / 'input-plan.json'
            value = planner.make_plan(Path('/synthetic/tool'), 'a'*40, output, force=True, read=read)
            self.assertEqual(value, {'include': []})
            read.assert_not_called()
            args = run.call_args.args[0]
            self.assertIn('--force', args)
            self.assertEqual(args[args.index('--revision')+1], 'a'*40)
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_absent_baseline_cannot_reuse_a_stale_file(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(planner.subprocess, 'check_output', return_value='a'*40), patch.object(planner.subprocess, 'run', return_value=Mock(stdout='{"include":[]}')) as run, patch.object(planner, 'previous_plan', return_value=None):
            output = Path(temp) / 'input-plan.json'
            stale = output.with_name('baseline-input-plan.json'); stale.write_text('{}')
            planner.make_plan(Path('/synthetic/tool'), 'a'*40, output)
            self.assertFalse(stale.exists())
            self.assertNotIn('--baseline', run.call_args.args[0])

    def test_a_different_checkout_or_unbound_reference_never_reaches_the_builder(self):
        for source in ['main', 'a'*40]:
            with patch.object(planner.subprocess, 'check_output', return_value='b'*40), patch.object(planner.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    planner.make_plan(Path('/synthetic/tool'), source, Path('/synthetic/plan'))
                run.assert_not_called()




class WorkflowContract(unittest.TestCase):
    def test_workflow_uses_the_derived_matrix_and_closed_source_export(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/agent-platform-images.yml').read_text())
        jobs = workflow['jobs']
        image = jobs['image']
        self.assertEqual(image['strategy']['matrix'], '${{ fromJSON(needs.ci-gate.outputs.matrix) }}')
        self.assertEqual(image['if'], "needs.ci-gate.outputs.build == 'true'")
        self.assertEqual(jobs['ci-gate']['outputs']['matrix'], '${{ steps.plan.outputs.matrix }}')
        build = next(step for step in image['steps'] if step.get('name') == 'Build (no credentials yet)')['run']
        self.assertIn('git archive --format=tar "$SHA"', build)
        self.assertIn('--load "$build_context"', build)
        self.assertIn('"$build_context/$DOCKERFILE"', build)
        self.assertNotIn('--load .', build)
        gate_text = '\n'.join(step.get('run', '') for step in jobs['ci-gate']['steps'])
        self.assertIn('scripts/plan-image-builds.py', gate_text)
        self.assertIn('workflow_dispatch', gate_text)
        self.assertNotIn('/compare/', gate_text)
        self.assertNotIn('grep -qvE', gate_text)
        self.assertTrue(any(step.get('with', {}).get('name') == 'image-input-plan' for step in jobs['ci-gate']['steps']))

    def test_ci_runs_current_graph_and_baseline_transport_checks_with_pinned_compiler(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
        setup = next(step for step in workflow['jobs']['checks']['steps'] if step.get('name') == 'Set up the pinned image-input tooling compiler')
        self.assertEqual(setup['uses'], 'actions/setup-go@924ae3a1cded613372ab5595356fb5720e22ba16')
        self.assertEqual(setup['with']['go-version-file'], 'tools/image-inputs/go.mod')
        check = (ROOT / 'scripts/check.sh').read_text()
        self.assertIn('go -C tools/image-inputs test -count=1 ./...', check)
        self.assertIn("unittest discover -s tools/image-inputs", check)


if __name__ == '__main__':
    unittest.main()
