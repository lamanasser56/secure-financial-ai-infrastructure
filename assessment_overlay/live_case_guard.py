"""Read both durable SDP ledgers around each approved live case.

This only reads the assessment redactor. Evidence contains counters and the run
identifier, never input text or credentials. A missing or corrupt ledger fails
closed before another case starts.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess


CASES = {'D02', 'D06', 'D04', 'D05', 'D07', 'O03', 'O04',
         'K01', 'K02', 'K03', 'K05', 'R01'}
REMOTE = ('import json;from pathlib import Path;'
          'print(json.dumps({n:json.loads(Path("/assessment-state/"+n).read_text()) '
          'for n in ("sdp-attempts.json","sdp-completions.json")}))')


def read(kubeconfig, run_id):
    command = ['kubectl', '--kubeconfig=' + str(kubeconfig), '-n', 'platform',
               'exec', 'deployment/redactor', '--', '/usr/local/bin/python3.12',
               '-c', REMOTE]
    result = subprocess.run(command, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError('both durable ledgers must be readable')
    state = json.loads(result.stdout)
    attempts, completions = state['sdp-attempts.json'], state['sdp-completions.json']
    if (attempts['run_id'] != run_id or completions['run_id'] != run_id
            or attempts['limit'] != 60 or completions['limit'] != 20
            or type(attempts['used']) is not int or type(completions['completed']) is not int
            or not 0 <= attempts['used'] <= 60
            or not 0 <= completions['completed'] <= 20
            or not isinstance(completions['inflight'], list)
            or completions['completed'] + len(completions['inflight']) > 20):
        raise RuntimeError('durable ledger state invalid')
    return {'run_id': run_id, 'sdk_attempts': attempts['used'],
            'completed_redactions': completions['completed'],
            'inflight': len(completions['inflight']), 'hard_limits': [20, 60],
            'manual_stop': [12, 40]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['before', 'after'])
    parser.add_argument('case', choices=sorted(CASES))
    parser.add_argument('--kubeconfig', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.run_dir / 'initial-manifest.json').read_text())
    run_id = manifest['run_id']
    if not re.fullmatch(r'assess-[0-9a-f]{16}', run_id):
        raise RuntimeError('invalid run ID')
    output = args.run_dir / 'evidence' / ('case-' + args.case + '-' + args.phase + '-ledgers.json')
    if output.exists():
        raise RuntimeError('counter evidence overwrite refused')
    state = read(args.kubeconfig, run_id)
    if args.phase == 'before' and (state['completed_redactions'] >= 12 or state['sdk_attempts'] >= 40):
        raise RuntimeError('manual stop threshold reached')
    if args.phase == 'after':
        prior = args.run_dir / 'evidence' / ('case-' + args.case + '-before-ledgers.json')
        before = json.loads(prior.read_text())
        if (state['completed_redactions'] < before['completed_redactions']
                or state['sdk_attempts'] < before['sdk_attempts']):
            raise RuntimeError('durable counter decreased')
        state['delta_redactions'] = state['completed_redactions'] - before['completed_redactions']
        state['delta_sdk_attempts'] = state['sdk_attempts'] - before['sdk_attempts']
    output.write_text(json.dumps(state, sort_keys=True, indent=2) + '\n')
    print(args.case, args.phase, state['completed_redactions'], state['sdk_attempts'])
    if state['completed_redactions'] >= 12 or state['sdk_attempts'] >= 40:
        raise RuntimeError('manual stop threshold reached')


if __name__ == '__main__':
    main()
