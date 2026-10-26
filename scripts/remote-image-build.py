#!/usr/bin/env python3
"""Run one source-bound OCI build and the unchanged qualification gate on secure-infra-worker.

The trusted main workflow sends a git archive of S and its SHA-256. This program never
accepts Dockerfile, target, or runtime code outside the declared image catalog.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILDKIT = 'moby/buildkit@sha256:99368f3e46177c6405b9740e4461d91cee004128daeecca78d4ceac50ec1da5c'
WORKER = 'secure-infra-worker'


def execute(*args, stdout=None):
    subprocess.run(args, check=True, cwd=ROOT, stdout=stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--archive-sha256', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.source) or not re.fullmatch(r'[0-9a-f]{64}', args.archive_sha256):
        raise SystemExit('invalid source or archive digest')
    entries = json.loads((ROOT / 'platform/image-targets.json').read_text())['images']
    match = [item for item in entries if item['image'] == args.image]
    if len(match) != 1:
        raise SystemExit('image absent or ambiguous in image target inventory')
    item = match[0]
    if any('/' in item[k] or '..' in item[k] for k in ('image', 'target')):
        raise SystemExit('unsafe target')
    path = ROOT / item['dockerfile']
    if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit('Dockerfile outside source archive')
    out = args.out.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if out.is_relative_to(ROOT.resolve()):
        raise SystemExit('evidence must live outside source archive')
    current = subprocess.check_output(['hostname'], text=True).strip()
    if current != WORKER:
        raise SystemExit('image build attempted off designated worker')
    builder = subprocess.run(['sudo', 'docker', 'buildx', 'inspect', 'sfai-pinned'], capture_output=True, text=True)
    if builder.returncode:
        execute('sudo', 'docker', 'buildx', 'create', '--name', 'sfai-pinned', '--driver', 'docker-container',
                '--driver-opt', 'image=' + BUILDKIT)
    execute('sudo', 'docker', 'buildx', 'inspect', 'sfai-pinned', '--bootstrap')
    material = subprocess.check_output(['sudo', 'docker', 'inspect', 'buildx_buildkit_sfai-pinned0',
                                        '--format', '{{.Config.Image}}'], text=True).strip()
    if material != BUILDKIT:
        raise SystemExit('worker builder material is not the declared pinned digest')
    local = f'local/{args.image}:{args.source}'
    build = ['sudo', 'docker', 'buildx', 'build', '--builder', 'sfai-pinned', '--platform', 'linux/amd64',
             '--target', item['target'], '--file', str(path), '--provenance=false', '--sbom=false',
             '--tag', local, '--load']
    if item['source_argument']:
        build.extend(['--build-arg', item['source_argument'] + '=' + args.source])
    build.append(str(ROOT))
    execute(*build)
    execute('sudo', '/srv/sfai/tools/trivy', 'image', '--exit-code', '0', '--ignore-unfixed=false',
            '--format', 'json', '--output', str(out / 'trivy.json'), local)
    execute('curl', '--fail', '--silent', '--show-error', '--location', '--proto', '=https', '--tlsv1.2',
            '--max-time', '60', '--output', str(out / 'kev.json'),
            'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json')
    execute('python3', 'scripts/reviewed-image-exception-gate.py', str(out / 'trivy.json'), local,
            args.image, str(out / 'kev.json'), 'policy/reviewed-image-exceptions.json',
            str(out / 'trivy-prepush-gate.json'))
    with (out / 'sbom.cdx.json').open('wb') as stream:
        execute('sudo', '/srv/sfai/tools/syft', local, '-o', 'cyclonedx-json', stdout=stream)
    bom = json.loads((out / 'sbom.cdx.json').read_text())
    if bom.get('bomFormat') != 'CycloneDX' or not bom.get('components'):
        raise SystemExit('SBOM empty')
    image_archive = out / 'image.tar.gz'
    with image_archive.open('wb') as stream:
        docker = subprocess.Popen(['sudo', 'docker', 'save', local], stdout=subprocess.PIPE)
        gzip = subprocess.run(['gzip', '-1'], stdin=docker.stdout, stdout=stream)
        docker.stdout.close()
        if docker.wait() or gzip.returncode:
            raise SystemExit('image archive export failed')
    digest = hashlib.sha256()
    with image_archive.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    manifest = {'schema': 1, 'worker': WORKER, 'source_commit': args.source,
                'git_archive_sha256': args.archive_sha256, 'image': args.image,
                'image_archive_sha256': digest.hexdigest()}
    (out / 'build.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
    execute('sudo', 'chown', '-R', str(out.stat().st_uid) + ':' + str(out.stat().st_gid), str(out))
    print(json.dumps({'worker': WORKER, 'image': args.image, 'source_commit': args.source,
                      'qualification': 'prepush-gate-passed', 'archive_sha256': manifest['image_archive_sha256']}))


if __name__ == '__main__':
    main()
