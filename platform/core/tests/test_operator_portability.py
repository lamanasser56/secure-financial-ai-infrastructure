"""The operator path starts from a clean checkout and rejects untrusted ADC."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lifecycle = load('portable_lifecycle', ROOT / 'platform/clouds/gke/lifecycle.py')
guard = load('portable_token_guard', ROOT / 'platform/clouds/gke/token_guard.py')


class OperatorPortabilityTests(unittest.TestCase):
    def test_tools_and_state_default_to_checkout(self):
        self.assertEqual(lifecycle.TOOLS, ROOT / '.cache/platform-tools')
        self.assertEqual(lifecycle.STATE, (ROOT / '.cache/operator-state').resolve())
        self.assertEqual(lifecycle.TF_SHA256, json.loads((ROOT / 'scripts/platform-tools.lock.json').read_text())['terraform']['binary_sha256'])

    def test_make_tools_provides_the_cosign_demo_check_runs(self):
        """A fresh checkout's `make demo-check` verifies signatures with cosign from `make tools`, not the host."""
        import re
        lock = json.loads((ROOT / 'scripts/platform-tools.lock.json').read_text())['cosign']
        qualification = (ROOT / 'scripts/install-qualification-tools.sh').read_text()
        pinned = re.search(r"'(https://github\.com/sigstore/cosign/releases/download/[^']+)' \\\n\s+'([0-9a-f]{64})'",
                           qualification)
        self.assertEqual((lock['url'], lock['binary_sha256']), pinned.groups())
        self.assertIn('v' + lock['version'] + '/', lock['url'])
        installer = (ROOT / 'scripts/install-platform-tools.py').read_text()
        self.assertIn("TOOLS / 'cosign'", installer)
        self.assertIn("LOCK['cosign']['binary_sha256']", installer)
        makefile = (ROOT / 'Makefile').read_text()
        self.assertRegex(makefile, r'(?m)^demo-check: tools operator-env$')
        self.assertIn('PATH="$(TOOLS):$$PATH"', makefile.split('demo-check:', 1)[1].split('\n\n', 1)[0])

    def test_settings_can_come_from_environment_without_a_machine_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'AGENT_PLATFORM_SETTINGS_FILE': str(Path(tmp) / 'absent.json'),
            'AGENT_PLATFORM_PROJECT_ID': 'fixture-project',
            'AGENT_PLATFORM_PROJECT_NUMBER': '12345',
            'AGENT_PLATFORM_GKE_VERSION': '1.35.0',
            'AGENT_PLATFORM_STATE_BUCKET': 'fixture-bucket',
        }):
            self.assertEqual(lifecycle.settings('project_id', 'project_number', 'gke_version', 'state_bucket'), {
                'project_id': 'fixture-project', 'project_number': '12345',
                'gke_version': '1.35.0', 'state_bucket': 'fixture-bucket'})

    def test_settings_fail_closed_when_required_input_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'AGENT_PLATFORM_SETTINGS_FILE': str(Path(tmp) / 'absent.json'),
        }, clear=True):
            with self.assertRaisesRegex(SystemExit, 'lifecycle:missing_settings:project_id'):
                lifecycle.settings()

    def workload(self, directory, *, kind='external_account', target='operator@example.invalid'):
        source = directory / 'oidc-token'
        source.write_text('fixture')
        config = directory / 'adc.json'
        config.write_text(json.dumps({
            'type': kind,
            'audience': '//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/example/providers/ci',
            'token_url': 'https://sts.googleapis.com/v1/token',
            'credential_source': {'file': str(source)},
            'service_account_impersonation_url':
                'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/' + target + ':generateAccessToken',
        }))
        config.chmod(0o600)
        return config

    def test_workload_adc_keeps_only_verified_refreshable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.workload(Path(tmp))
            environ = {'GOOGLE_APPLICATION_CREDENTIALS': str(config),
                       'AGENT_PLATFORM_OPERATOR': 'operator@example.invalid',
                       'GOOGLE_OAUTH_ACCESS_TOKEN': 'static-token'}
            child = guard.workload_adc_env(environ, info=lambda _: {
                'email': 'operator@example.invalid', 'scope': guard.CLOUD_PLATFORM, 'expires_in': '300'},
                adc_token=lambda _: 'fixture-token')
            self.assertEqual(child['GOOGLE_APPLICATION_CREDENTIALS'], str(config))
            self.assertNotIn('GOOGLE_OAUTH_ACCESS_TOKEN', child)

    def test_workload_adc_rejects_key_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = self.workload(directory, kind='service_account')
            environ = {'GOOGLE_APPLICATION_CREDENTIALS': str(config),
                       'AGENT_PLATFORM_OPERATOR': 'operator@example.invalid'}
            with self.assertRaisesRegex(guard.CredentialRefused, 'WORKLOAD_NOT_EXTERNAL_ACCOUNT'):
                guard.workload_adc_env(environ)
            config = self.workload(directory, target='other@example.invalid')
            with self.assertRaisesRegex(guard.CredentialRefused, 'ADC_IDENTITY_MISMATCH'):
                guard.workload_adc_env(environ)

    def test_github_oidc_source_is_bound_to_this_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.workload(Path(tmp))
            data = json.loads(config.read_text())
            data['credential_source'] = {
                'url': 'https://token.actions.githubusercontent.com/request?audience=fixture',
                'headers': {'Authorization': 'Bearer job-token'},
                'format': {'type': 'json', 'subject_token_field_name': 'value'},
            }
            config.write_text(json.dumps(data))
            environ = {
                'GOOGLE_APPLICATION_CREDENTIALS': str(config),
                'AGENT_PLATFORM_OPERATOR': 'operator@example.invalid',
                'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://token.actions.githubusercontent.com/request',
                'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'job-token',
            }
            details = lambda _: {'email': 'operator@example.invalid', 'scope': guard.CLOUD_PLATFORM, 'expires_in': '300'}
            guard.workload_adc_env(environ, info=details, adc_token=lambda _: 'fixture-token')
            data['credential_source']['url'] = 'https://elsewhere.invalid/request'
            config.write_text(json.dumps(data))
            with self.assertRaisesRegex(guard.CredentialRefused, 'WORKLOAD_SOURCE_URL'):
                guard.workload_adc_env(environ, info=details, adc_token=lambda _: 'fixture-token')

    def test_kubeconfig_uses_the_same_refreshable_adc(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(lifecycle, 'STATE', Path(tmp) / 'state'), \
                patch.object(lifecycle, 'settings', return_value={'project_id': 'fixture-project'}), \
                patch.object(lifecycle, 'run') as run:
            run.return_value.stdout = json.dumps({
                'controlPlaneEndpointsConfig': {'dnsEndpointConfig': {'endpoint': 'fixture.invalid'}}})
            path = lifecycle.kubeconfig()
            self.assertTrue(path.is_file())
            helper = (lifecycle.STATE / 'gcloud-token-exec.sh').read_text()
            self.assertIn('gcloud auth application-default print-access-token', helper)


if __name__ == '__main__':
    unittest.main()
