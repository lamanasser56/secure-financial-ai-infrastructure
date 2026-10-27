#!/usr/bin/env python3
"""Install and verify repo-pinned Kubernetes, Terraform and cosign tools in .cache."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'scripts/platform-tools.lock.json').read_text())
CACHE = ROOT / '.cache'
ENVTEST = CACHE / ('envtest-' + LOCK['envtest']['version'])
TOOLS = CACHE / 'platform-tools'


def digest(path, algorithm):
    value = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1 << 20), b''):
            value.update(part)
    return value.hexdigest()


def obtain(url, destination, algorithm, expected):
    if not url.startswith('https://'):
        raise ValueError('HTTPS tool source required')
    request = urllib.request.Request(url, headers={'User-Agent': 'secure-financial-ai-tool-bootstrap'})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open('wb') as output:
        shutil.copyfileobj(response, output)
    if digest(destination, algorithm) != expected:
        raise ValueError('tool archive checksum mismatch')


def verify(path, expected):
    if path.exists() and digest(path, 'sha256') != expected:
        raise ValueError('pinned tool checksum mismatch: ' + path.name)
    return path.exists()


def install():
    if os.name != 'posix' or os.uname().machine != 'x86_64':
        raise ValueError('locked tool platform is linux-amd64')
    if LOCK['schema'] != 1 or LOCK['platform'] != 'linux-amd64':
        raise ValueError('tool lock schema/platform')
    CACHE.mkdir(exist_ok=True)
    TOOLS.mkdir(exist_ok=True)
    envtest_binaries = {
        'kubectl': LOCK['envtest']['kubectl_sha256'],
        'kube-apiserver': LOCK['envtest']['kube_server_sha256'],
        'etcd': LOCK['envtest']['etcd_sha256'],
    }
    kube = ENVTEST / 'kubectl'
    terraform = TOOLS / 'terraform'
    if not all(verify(ENVTEST / name, expected) for name, expected in envtest_binaries.items()):
        with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
            archive = Path(temporary) / 'envtest.tar.gz'
            obtain(LOCK['envtest']['url'], archive, 'sha256', LOCK['envtest']['archive_sha256'])
            ENVTEST.mkdir(exist_ok=True)
            with tarfile.open(archive, 'r:gz') as bundle:
                for member in bundle.getmembers():
                    if not member.isfile():
                        continue
                    name = Path(member.name).name
                    if name not in ('kubectl', 'kube-apiserver', 'etcd'):
                        continue
                    source = bundle.extractfile(member)
                    if source is None:
                        raise ValueError('envtest member missing')
                    with (ENVTEST / name).open('wb') as output:
                        shutil.copyfileobj(source, output)
                    (ENVTEST / name).chmod(0o755)
        if not all(verify(ENVTEST / name, expected) for name, expected in envtest_binaries.items()):
            raise ValueError('envtest checksum mismatch after extraction')
    if not verify(terraform, LOCK['terraform']['binary_sha256']):
        with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
            archive = Path(temporary) / 'terraform.zip'
            obtain(LOCK['terraform']['url'], archive, 'sha256', LOCK['terraform']['archive_sha256'])
            with zipfile.ZipFile(archive) as bundle:
                if bundle.namelist().count('terraform') != 1:
                    raise ValueError('terraform archive shape')
                with bundle.open('terraform') as source, terraform.open('wb') as output:
                    shutil.copyfileobj(source, output)
        terraform.chmod(0o755)
        if not verify(terraform, LOCK['terraform']['binary_sha256']):
            raise ValueError('terraform checksum mismatch after extraction')
    # make demo-check verifies keyless signatures and signed predicates with cosign; same pin as the image workflow.
    cosign = TOOLS / 'cosign'
    if not verify(cosign, LOCK['cosign']['binary_sha256']):
        with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
            download = Path(temporary) / 'cosign'
            obtain(LOCK['cosign']['url'], download, 'sha256', LOCK['cosign']['binary_sha256'])
            download.chmod(0o755)
            download.replace(cosign)
    linked = TOOLS / 'kubectl'
    if linked.is_symlink() and linked.resolve() != kube.resolve():
        raise ValueError('kubectl link points outside pinned envtest')
    if linked.exists() and not linked.is_symlink():
        verify(linked, LOCK['envtest']['kubectl_sha256'])
    elif not linked.exists():
        linked.symlink_to(kube)
    print('repo-pinned kubectl, envtest, Terraform and cosign verified')


if __name__ == '__main__':
    install()
