#!/usr/bin/env python3
"""Prepared zero-model/zero-SDP application metadata/provider denial probe.

Timeouts are observations only. Require native DENY verdict correlation before
admission; no missing route or injected result establishes enforcement.
"""
from datetime import datetime, timezone
import ipaddress
import json
import socket
import sys


def run():
    rows = []
    for name, host, port in (('metadata', '169.254.169.254', 80),
                            ('vertex', 'us-east1-aiplatform.googleapis.com', 443),
                            ('sdp', 'dlp.us-east1.rep.googleapis.com', 443)):
        ips = sorted({entry[4][0] for entry in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)})
        if not ips or len(ips) > 50 or (name != 'metadata' and any(not ipaddress.ip_address(ip).is_global for ip in ips)):
            raise ValueError
        ip = ips[0]
        try:
            with socket.create_connection((ip, port), timeout=5):
                raise ValueError
        except TimeoutError:
            rows.append({'test': name, 'destination_ip': ip, 'port': port, 'observation': 'timeout'})
    return {'status': 'OBSERVATIONS_PASSED_AWAITING_DATAPATH_EVIDENCE', 'probes': rows,
            'model_requests': 0, 'sdk_attempts': 0, 'metadata_http_requests': 0,
            'finished_at': datetime.now(timezone.utc).isoformat()}


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('probe:arguments_rejected')
    try:
        print(json.dumps(run()))
    except Exception:
        raise SystemExit('probe:application_denial_observation_failed') from None
