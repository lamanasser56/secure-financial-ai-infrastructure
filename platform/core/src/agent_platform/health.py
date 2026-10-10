"""Exec readiness probe for loopback-only servers: `python -m agent_platform.health http://127.0.0.1:<port>/`."""
import sys
import urllib.request


def main(argv):
    if len(argv) != 1 or not argv[0].startswith('http://127.0.0.1:'):
        raise SystemExit(2)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                urllib.request.Request(argv[0], headers={'Host': argv[0].split('/')[2]}), timeout=3) as response:
            raise SystemExit(0 if response.status == 200 else 1)
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
