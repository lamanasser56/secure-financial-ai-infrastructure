#!/usr/bin/env python3
"""Gateway entry point for the qualified LiteLLM image (mounted read-only from a ConfigMap).

The same prelude the C windows proved live: refuse an unreviewed toolchain, pin the Prisma engine platform
and disable the Prisma CLI path (no schema writes at startup; the schema job owns DDL). Configuration
comes only from /config/litellm.yaml (rendered from providers/<profile>.yaml) and the gateway Secret
(environment). The model provider credential is Workload Identity; no key file exists.
"""
import sys
from importlib.metadata import version

REVIEWED_TOOLCHAIN = {'litellm': '1.104.0', 'prisma': '0.15.0'}
PRISMA_BINARY_PLATFORM = 'debian-openssl-3.0.x'


def main():
    for name, expected in sorted(REVIEWED_TOOLCHAIN.items()):
        if version(name) != expected:
            raise SystemExit('gateway:toolchain_unreviewed:' + name)
    import prisma.binaries.platform as prisma_platform
    prisma_platform.binary_platform = lambda: PRISMA_BINARY_PLATFORM
    import litellm_proxy_extras.prisma_toolchain as prisma_toolchain
    prisma_toolchain.prisma_cli_available = lambda: False
    sys.argv = ['/app/proxy.py', '--config', '/config/litellm.yaml', '--host', '0.0.0.0', '--port', '4000',
                '--num_workers', '1']
    from litellm.proxy.proxy_cli import run_server
    run_server()


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('gateway:arguments_rejected')
    main()
