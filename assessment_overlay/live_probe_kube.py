"""Execute bounded, summary-only probes in running disposable Pods."""
import json
import subprocess


def kubectl(command, *, input=None):
    result = subprocess.run(command, input=input, capture_output=True, text=True, timeout=60)
    if result.returncode:
        # Never echo stderr: Pods may include credentials or private responses.
        raise RuntimeError('assessment:probe_kubectl_failed')
    return result.stdout


def one_pod(kubeconfig, namespace, selector, *, executable='kubectl', run=kubectl):
    base = [str(executable), '--kubeconfig=' + str(kubeconfig), '-n', namespace]
    value = json.loads(run(base + ['get', 'pods', '-l', selector, '-o', 'json']))
    pods = [item for item in value.get('items', []) if item.get('status', {}).get('phase') == 'Running']
    if len(pods) != 1:
        raise RuntimeError('assessment:exactly_one_running_pod_required')
    return pods[0]['metadata']['name']


def python_probe(kubeconfig, namespace, pod, script, *, executable='kubectl', run=kubectl):
    base = [str(executable), '--kubeconfig=' + str(kubeconfig), '-n', namespace]
    raw = run(base + ['exec', '-i', pod, '--', '/usr/local/bin/python3.12', '-'], input=script)
    result = json.loads(raw)
    if not isinstance(result, dict) or not result or any(type(value) is not bool for value in result.values()):
        raise RuntimeError('assessment:probe_summary_invalid')
    return result
