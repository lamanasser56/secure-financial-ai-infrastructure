#!/usr/bin/env python3
"""Gateway entry point, owned by the signed gateway image (python3.12 -m agent_platform.programs.gateway_entry).

The prelude the live gateway ran before its program moved into the image: refuse an unreviewed toolchain, pin the
Prisma engine platform (prisma would otherwise detect it by running `cat /etc/os-release` and `openssl version`,
neither of which exists in the distroless runtime) and disable the Prisma CLI path (no schema writes at startup;
the schema job owns DDL). Configuration comes only from /config/litellm.yaml (rendered from providers/<profile>.yaml)
and the gateway Secret (environment). The model provider credential is Workload Identity; no key file exists.
"""
import sys
from importlib.metadata import version

# Must equal the pins in requirements-gateway.txt (checked by platform/core/tests/test_gateway_entry.py).
REVIEWED_TOOLCHAIN = {'litellm': '1.104.7', 'prisma': '0.15.0'}
PRISMA_BINARY_PLATFORM = 'debian-openssl-3.0.x'
ARGV = ['/app/proxy.py', '--config', '/config/litellm.yaml', '--host', '0.0.0.0', '--port', '4001',
        '--num_workers', '1']


def main():
    for name, expected in sorted(REVIEWED_TOOLCHAIN.items()):
        if version(name) != expected:
            raise SystemExit('gateway:toolchain_unreviewed:' + name)
    import prisma.binaries.platform as prisma_platform
    prisma_platform.binary_platform = lambda: PRISMA_BINARY_PLATFORM
    import litellm_proxy_extras.prisma_toolchain as prisma_toolchain
    prisma_toolchain.prisma_cli_available = lambda: False
    sys.argv = list(ARGV)
    from litellm.proxy.proxy_cli import run_server
    run_server()


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('gateway:arguments_rejected')
    main()
