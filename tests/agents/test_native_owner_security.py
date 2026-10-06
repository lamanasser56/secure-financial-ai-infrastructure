"""Retained owner-receipt schema tests; do not perform cryptographic verification."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from runtime.agents.operations import OperationsBlocked
from runtime.agents.operations_security import read_subject


class OwnerReceiptTests(unittest.TestCase):
    def test_owner_source_annotation_cannot_be_relabelled_as_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);subject='us-east1-docker.pkg.dev/synthetic-project/sdp-evaluation-images/agent-demo-gateway@sha256:'+'a'*64
            config={'subject':subject,'source':'b'*40,'signer':'synthetic-test@example.invalid','issuer':'https://oauth2.sigstore.dev/auth','signing_mode':'native_owner','files':{}}
            def write(name,value):
                p=root/(name+'.json');p.write_text(json.dumps(value));config['files'][name]={'path':str(p),'integrity':hashlib.sha256(p.read_bytes()).hexdigest()}
            write('scan',{'SchemaVersion':2,'ArtifactType':'container_image','ArtifactName':subject,'Results':[{'Target':'test','Vulnerabilities':[]}]})
            write('kev',{'vulnerabilities':[{'cveID':'CVE-2026-10001'}]})
            write('exceptions',{'schema_version':1,'exceptions':[]})
            write('signature',[{'critical':{'image':{'docker-manifest-digest':'sha256:'+'a'*64},'identity':{'docker-reference':subject.split('@')[0]}},'optional':{'Issuer':config['issuer'],'Subject':config['signer'],'source':config['source']}}])
            write('release',{'result':'PASS','registry_digest_reference':subject,'source_commit':config['source'],'evidence_sha256':{'trivy.json':config['files']['scan']['integrity'],'cosign-verification.json':config['files']['signature']['integrity']}})
            write('verification',{'result':'PASS','registry_digest_reference':subject,'source_commit':config['source'],'native_cosign_verification':'PASS exact issuer/owner/source/digest','reviewed_release_subject_receipt_sha256':config['files']['release']['integrity'],'verified_at':'2026-10-06T00:00:00Z'})
            value=read_subject(config)
            self.assertEqual(value['vulnerability_policy'],'allow')
            self.assertFalse(value['current_application_qualified']);self.assertFalse(value['fresh_signature_verification'])
            for change in [{'signing_mode':'github_workflow'},{'source':'c'*40},{'issuer':'https://accounts.google.com'}]:
                with self.assertRaises(OperationsBlocked):read_subject(config|change)


if __name__=='__main__':unittest.main()
