"""Constructed canonical deployment/admission checks; no cloud or model calls."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('worker_services',ROOT/'scripts/render-worker-live-services.py')
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)


class WorkerServicesTests(unittest.TestCase):
    def test_no_worker_cloud_identity_application_or_unbounded_empty_peer(self):
        project='synthetic-project'
        prefix=f'us-east1-docker.pkg.dev/{project}/sdp-evaluation-images/'
        for phase in ['fixed_inputs_qualification','supervised_synthetic_free_text']:
            value=renderer.bundle(project,prefix+'agent-demo-gateway@sha256:'+'a'*64,
                prefix+'agent-demo-database@sha256:'+'b'*64,phase=phase)
            for item in value['items']:
                self.assertNotIn(item['metadata']['name'],{'catalog','application-network-preflight','google-agent-demo-application'})
                if item['kind']=='NetworkPolicy':
                    for direction,field in [('egress','to'),('ingress','from')]:
                        for rule in item['spec'].get(direction,[]):self.assertTrue(rule[field])
                if item['kind']=='Pod':
                    self.assertEqual(item['spec']['restartPolicy'],'Never')
                    self.assertFalse(item['spec']['automountServiceAccountToken'])

    def test_unknown_phase_and_unpinned_digest_denied(self):
        for phase in ['unknown','fixed_inputs_qualification']:
            with self.assertRaises(ValueError):renderer.bundle('synthetic-project','mutable','mutable',phase=phase)


if __name__=='__main__':unittest.main()
