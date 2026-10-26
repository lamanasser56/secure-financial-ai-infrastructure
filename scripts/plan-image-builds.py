#!/usr/bin/env python3
"""Select consumers against a successful image-workflow input plan, never a CI-only push.

This artifact is a comparison plan, not image/source provenance or a release receipt.
Missing, expired, malformed or untrusted baselines rebuild every current target.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

WORKFLOW = 'agent-platform-images.yml'
ARTIFACT = 'image-input-plan'
MAX_JSON = 8 << 20


def api(route, *, binary=False):
    result = subprocess.run(['gh', 'api', route], check=True, capture_output=True)
    if len(result.stdout) > MAX_JSON:
        raise ValueError('oversized baseline response')
    return result.stdout if binary else json.loads(result.stdout)


def trusted_run(run, repository, current_run):
    return (isinstance(run, dict) and type(run.get('id')) is int and run['id'] > 0
            and str(run['id']) != str(current_run) and run.get('status') == 'completed'
            and run.get('conclusion') == 'success' and run.get('head_branch') == 'main'
            and run.get('event') in ('workflow_run', 'workflow_dispatch')
            and run.get('path') == '.github/workflows/' + WORKFLOW
            and isinstance(run.get('repository'), dict) and isinstance(run.get('head_repository'), dict)
            and run.get('repository', {}).get('full_name') == repository
            and run.get('head_repository', {}).get('full_name') == repository)


def archive_plan(raw):
    if len(raw) > MAX_JSON:
        raise ValueError('oversized artifact')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        items = archive.infolist()
        if len(items) != 1 or items[0].filename != 'input-plan.json' or items[0].file_size > MAX_JSON:
            raise ValueError('unexpected artifact shape')
        value = archive.read(items[0])
    # The Go owner validates the complete schema and recomputes every fingerprint.
    if not isinstance(json.loads(value), dict):
        raise ValueError('invalid plan')
    return value


def previous_plan(repository, current_run, *, read=api):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', repository) or repository.rsplit('/', 1)[-1] in ('.', '..'):
        return None
    try:
        listing = read(f'repos/{repository}/actions/workflows/{WORKFLOW}/runs?status=success&branch=main&per_page=10')
        for run in listing['workflow_runs']:
            if not trusted_run(run, repository, current_run):
                continue
            artifacts = read(f'repos/{repository}/actions/runs/{run["id"]}/artifacts?per_page=100')
            if artifacts.get('total_count') != len(artifacts['artifacts']):
                continue
            candidates = [item for item in artifacts['artifacts'] if isinstance(item, dict) and item.get('name') == ARTIFACT and not item.get('expired')]
            if len(candidates) != 1:
                continue
            item = candidates[0]
            if type(item.get('id')) is not int or item['id'] <= 0 or type(item.get('size_in_bytes')) is not int or not 0 < item['size_in_bytes'] <= MAX_JSON:
                continue
            return archive_plan(read(f'repos/{repository}/actions/artifacts/{item["id"]}/zip', binary=True))
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile, RuntimeError):
        return None
    return None


def make_plan(tool, source, output, *, force=False, root=Path('.'), read=api):
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('exact source commit required')
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != source:
        raise ValueError('checkout is not the validated source')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    baseline = output.with_name('baseline-input-plan.json')
    prior = None if force else previous_plan(os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('GITHUB_RUN_ID', ''), read=read)
    if prior is not None:
        baseline.write_bytes(prior)
    elif baseline.exists():
        baseline.unlink()
    args = [str(tool), '--root', str(root), '--revision', source, '--out', str(output)]
    if force:
        args.append('--force')
    if prior is not None:
        args.extend(['--baseline', str(baseline)])
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    matrix = json.loads(result.stdout)
    if not isinstance(matrix, dict) or set(matrix) != {'include'} or not isinstance(matrix['include'], list):
        raise ValueError('invalid tool matrix')
    return matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    print(json.dumps(make_plan(args.tool.resolve(), args.source, args.out, force=args.force), separators=(',', ':')))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Image input planning failed; no build or signing was authorized.', file=sys.stderr)
        raise SystemExit(1)
