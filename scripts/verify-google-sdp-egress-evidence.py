"""Offline correlation of bounded probe observations with genuine GKE verdicts."""

from datetime import datetime, timedelta
import ipaddress
import json
from pathlib import Path
import re
import sys


def verify(observations, logs, pod):
    if not re.fullmatch(r"google-sdp-egress-preflight-[a-z0-9-]{1,63}", pod):
        raise ValueError("wrong probe Pod")
    if observations["status"] != "OBSERVATIONS_PASSED_AWAITING_DATAPATH_EVIDENCE" or observations["provider_operations"] != 0:
        raise ValueError("failed or live probe")
    if not all(observations[key] is True for key in ("tls_certificate_verified", "http2_negotiated", "metadata_identity_matched")):
        raise ValueError("positive checks absent")
    if observations["limitations"] != ["dns_derived_ip_port_only", "shared_ip_not_hostname_isolation", "dns_names_not_restricted", "sdk_authentication_not_proven"]:
        raise ValueError("limitations missing")
    positive = observations["positive_ip"]
    if ipaddress.ip_address(positive).version != 4 or not ipaddress.ip_address(positive).is_global:
        raise ValueError("invalid positive address")
    probes = observations["probes"]
    required = {"unrelated_resolved_https", "unrelated_direct_ip", "alternate_https_route", "alternate_dns_route"}
    if not 4 <= len(probes) <= 8 or {probe["test"] for probe in probes} != required:
        raise ValueError("incomplete negative coverage")
    for probe in probes:
        ip = ipaddress.ip_address(probe["destination_ip"])
        port = 53 if probe["test"] == "alternate_dns_route" else 443
        if ip.version != 4 or not ip.is_global or str(ip) == positive or probe["port"] != port or probe["observation"] != "timeout":
            raise ValueError("invalid negative observation")
        if probe["test"].startswith("alternate_") and str(ip) != "8.8.8.8":
            raise ValueError("wrong alternate route")
    start = datetime.fromisoformat(observations["started_at"])
    end = datetime.fromisoformat(observations["finished_at"])
    if start.utcoffset() is None or end.utcoffset() is None or not timedelta(0) <= end - start <= timedelta(seconds=180):
        raise ValueError("unbounded probe window")
    if not isinstance(logs, list) or not 1 <= len(logs) <= 1000:
        raise ValueError("invalid log batch")
    verdicts = set()
    positive_seen = False
    for entry in logs:
        resource = entry.get("resource", {})
        labels = resource.get("labels", {})
        payload = entry.get("jsonPayload", {})
        source = payload.get("src", {})
        connection = payload.get("connection", {})
        if resource.get("type") != "k8s_node" or labels.get("cluster_name") != "google-sdp-evaluation" or labels.get("location") != "us-east1-b":
            continue
        if source.get("pod_name") != pod or source.get("namespace", source.get("pod_namespace")) != "google-sdp-evaluation":
            continue
        if entry.get("logName") != f"projects/{labels.get('project_id')}/logs/policy-action":
            continue
        timestamp = datetime.fromisoformat(payload.get("timestamp", entry.get("timestamp", "")).replace("Z", "+00:00"))
        if not start - timedelta(seconds=5) <= timestamp <= end + timedelta(seconds=5):
            continue
        if connection.get("direction") != "egress" or connection.get("protocol") != "tcp":
            continue
        destination = (connection.get("dest_ip"), connection.get("dest_port"))
        if payload.get("disposition") == "deny":
            verdicts.add(destination)
        if payload.get("disposition") == "allow" and destination == (positive, 443):
            positive_seen |= any(policy.get("name") == "google-sdp-evaluation-regional-egress" and policy.get("namespace") == "google-sdp-evaluation" for policy in payload.get("policies", []))
    if not positive_seen or any((probe["destination_ip"], probe["port"]) not in verdicts for probe in probes):
        raise ValueError("matching datapath allow/deny evidence absent")
    return {"status": "VERIFIED_IP_PORT_BOUNDARY", "provider_operations": 0, "limitations": observations["limitations"]}


def main():
    try:
        if len(sys.argv) != 4 or any(Path(name).stat().st_size > 2_000_000 for name in sys.argv[1:3]):
            raise ValueError("invalid bounded evidence inputs")
        result = verify(*(json.loads(Path(name).read_text()) for name in sys.argv[1:3]), sys.argv[3])
    except Exception:
        print('{"status":"FAIL","reason":"egress_evidence_not_verified"}')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
