#!/usr/bin/env python3
"""Fixed local proxy entry point; all configuration is operator-selected."""
from litellm.proxy.proxy_cli import run_server

if __name__ == "__main__":
    run_server()
