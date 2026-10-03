#!/usr/bin/env python3
"""Start the private offline demo; never bind to a public interface."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.agents.web import DemoServer


def main():
    parser = argparse.ArgumentParser(
        description="Private offline simulation; no real authentication or model/provider call."
    )
    parser.add_argument(
        "--user", choices=("demo-alpha", "demo-beta"), default="demo-alpha"
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with DemoServer(("127.0.0.1", args.port), user=args.user) as server:
        print(
            f"Offline synthetic demo: {server.origin}; simulated authentication. Ctrl+C stops the server.",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
