"""Make a deterministic source candidate and an external runtime input lock locally."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
PRIOR = Path('/home/lama/security-assessments/2026-10-22-independent-live/live-recovery-2026-10-24/rc1-financial-fixed-source.tar.gz')
NEW = 'platform/core/src/agent_platform/programs/phone_guard.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


with tarfile.open(PRIOR, 'r:gz') as previous:
    members = {m.name: m for m in previous.getmembers() if m.isfile()}
assert len(members) == 506 and NEW not in members
names = sorted([*members, NEW])
tar_stream = io.BytesIO()
lock = {}
with tarfile.open(fileobj=tar_stream, mode='w', format=tarfile.GNU_FORMAT) as output:
    for name in names:
        raw = (ROOT / name).read_bytes()
        info = tarfile.TarInfo(name)
        info.size = len(raw)
        info.mode = members[name].mode if name in members else 0o644
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        output.addfile(info, io.BytesIO(raw))
        lock[name] = sha(raw)
plain = tar_stream.getvalue()
archive = HERE / 'rc1-followup-source.tar.gz'
with archive.open('wb') as file:
    with gzip.GzipFile(filename='', fileobj=file, mode='wb', mtime=0) as zipped:
        zipped.write(plain)
external = [
    'assessment_overlay/sdp_guard.py',
    'assessment_overlay/seed_sdp.py',
    'assessment_overlay/redactor_server.py',
    'assessment_overlay/ops_server_assessment.py',
    'platform/core/src/agent_platform/programs/phone_guard.py',
]
result = {
    'source_files': len(lock), 'source_archive_sha256': sha(archive.read_bytes()),
    'source_tar_sha256': sha(plain), 'source_file_sha256': lock,
    'external_runtime_sha256': {name: sha((ROOT / name).read_bytes()) for name in external},
    'historical_image_or_signature_reused_as_new': False,
    'cloud_build_or_signature_created': False,
}
(HERE / 'candidate-inputs.lock.json').write_text(json.dumps(result, indent=2) + '\n')
print('CANDIDATE INPUTS',len(lock),result['source_archive_sha256'])
