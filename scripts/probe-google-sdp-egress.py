"""Bounded connection probes; no DLP SDK, credentials, fixture or API request."""

from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import urllib.request


ENDPOINT = "dlp.me-central2.rep.googleapis.com"
ACK = "I_ACKNOWLEDGE_SYNTHETIC_NETWORK_PREFLIGHT"
LIMITATIONS = ["dns_derived_ip_port_only", "shared_ip_not_hostname_isolation", "dns_names_not_restricted", "sdk_authentication_not_proven"]
TIMEOUT = 5


def resolve(host):
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)})
    if not addresses or len(addresses) > 50 or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("unsupported DNS result")
    return addresses


def tls(ip):
    context = ssl.create_default_context()
    context.set_alpn_protocols(["h2"])
    with socket.create_connection((ip, 443), timeout=TIMEOUT) as connection:
        with context.wrap_socket(connection, server_hostname=ENDPOINT) as channel:
            if channel.selected_alpn_protocol() != "h2":
                raise ValueError("HTTP/2 not negotiated")


def blocked(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT):
            return False
    except TimeoutError:
        # A timeout is an observation, not proof of a datapath policy verdict.
        return True


def metadata_identity(expected):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/email",
        headers={"Metadata-Flavor": "Google"},
    )
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.headers.get("Metadata-Flavor") != "Google":
            raise ValueError("untrusted metadata")
        if response.read(256).decode("ascii").strip() != expected:
            raise ValueError("wrong metadata identity")


def observe(environ, *, resolver=resolve, tls_connect=tls, denial=blocked, identity=metadata_identity):
    gsa = environ.get("PORTFOLIO_GOOGLE_SDP_EXPECTED_GSA", "")
    if environ.get("PORTFOLIO_GOOGLE_SDP_NETWORK_PREFLIGHT_ACK") != ACK:
        raise ValueError("network preflight acknowledgment required")
    if not re.fullmatch(r"google-sdp-runtime@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com", gsa):
        raise ValueError("trusted runtime identity required")
    if any(environ.get(key) for key in ("grpc_proxy", "https_proxy", "http_proxy", "GRPC_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "all_proxy")):
        raise ValueError("proxy route prohibited")
    approved = resolver(ENDPOINT)
    unrelated = resolver("example.com")
    if len(unrelated) > 3 or set(approved).intersection(unrelated) or "8.8.8.8" in approved:
        raise ValueError("negative targets cannot isolate the policy")
    identity(gsa) # Email only, never request or print an access token.
    tls_connect(approved[0]) # Verified TLS/HTTP2 handshake, no DLP request.
    probes = []
    for name, destinations in (
        ("unrelated_resolved_https", [(ip, 443) for ip in unrelated]),
        ("unrelated_direct_ip", [(ip, 443) for ip in unrelated]),
        ("alternate_https_route", [("8.8.8.8", 443)]),
        ("alternate_dns_route", [("8.8.8.8", 53)]),
    ):
        for ip, port in destinations:
            if not denial(ip, port):
                raise ValueError("unapproved connection succeeded")
            probes.append({"test": name, "destination_ip": ip, "port": port, "observation": "timeout"})
    return {"positive_ip": approved[0], "tls_certificate_verified": True, "http2_negotiated": True, "metadata_identity_matched": True, "probes": probes}


def main(argv=None, environ=None):
    started = datetime.now(timezone.utc).isoformat()
    result = {"status": "FAIL", "provider_operations": 0, "limitations": LIMITATIONS}
    code = 2
    if (sys.argv[1:] if argv is None else argv) == ["--network-preflight"]:
        try:
            result.update(observe(os.environ if environ is None else environ))
            result["status"] = "OBSERVATIONS_PASSED_AWAITING_DATAPATH_EVIDENCE"
            code = 0
        except Exception:
            # No exception, metadata value, provider value or credential is emitted.
            pass
    result["started_at"] = started
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
