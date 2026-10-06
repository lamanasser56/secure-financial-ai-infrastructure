#!/usr/bin/env python3
"""Fixed deterministic loopback upstream. This is not a model or redactor."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.agents.demo import FakeGateway


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        state = self.server.state
        operator = json.loads((state / "operator.json").read_text())
        if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != "Bearer " + operator["stub_key"]:
            self.send_error(403)
            return
        length = self.headers.get("Content-Length", "0")
        if not length.isdigit() or not 0 < int(length) <= 16384:
            self.send_error(400)
            return
        request = json.loads(self.rfile.read(int(length)))
        prompt = request["messages"][-1]["content"]
        control = json.loads((state / "stub-control.json").read_text()) if (state / "stub-control.json").exists() else {"mode": "canonical"}
        try:
            facts = json.loads(prompt)
        except (ValueError, TypeError):
            facts = None
        if type(facts) is dict and 'observed' in facts and 'evidence_id' in facts and 'target_id' in facts:
            # Local deterministic explanation of actual observations, explicitly
            # a stub. This response has no tool or approval authority.
            envelope = {'summary': 'Observed ' + str(facts['observed']) + '. '
                + ('Supervisor exit cause remains unknown.' if facts['observed'] == 'ORPHANED'
                   else 'Review current evidence and policy before any action.'),
                'classification': 'informational'}
        else:
            envelope = FakeGateway().complete("secure-financial-chat", prompt, {}).output
        message = {"role": "assistant", "content": json.dumps(envelope, ensure_ascii=False)}
        finish = "stop"
        if control["mode"] == "native_tool":
            finish = "tool_calls"
            message["tool_calls"] = [{"id": "fixture-call", "type": "function",
                "function": {"name": "expense_summary", "arguments": "{}"}}]
        elif control["mode"] == "truncated":
            finish = "length"
        elif control["mode"] == "cross_profile":
            message["content"] = json.dumps({"summary": json.dumps({"kind": "tool",
                "tool_id": "expense_summary", "arguments": {"period": "2026-01"}}),
                "classification": "informational"})
        elif control["mode"] != "canonical":
            self.send_error(400)
            return
        self.server.count += 1
        (state / "stub-count.json").write_text(json.dumps({"stub_requests": self.server.count,
                                                         "external_model_calls": 0}) + "\n")
        response = {"id": "local-stub", "object": "chat.completion", "created": 0,
            "model": "fixture-model", "choices": [{"index": 0, "message": message,
            "finish_reason": finish}], "usage": {"prompt_tokens": 10,
            "completion_tokens": 20, "total_tokens": 30}}
        body = json.dumps(response, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port in {8765,8768,8769}:
        raise SystemExit('stub:invalid_port')
    with HTTPServer(("127.0.0.1", args.port), Handler) as server:
        prior = json.loads((args.state/'stub-count.json').read_text()) if (args.state/'stub-count.json').exists() else {'stub_requests':0}
        if type(prior['stub_requests']) is not int or not 0 <= prior['stub_requests'] <= 256:
            raise SystemExit('stub:invalid_counter')
        server.state, server.count = args.state, prior['stub_requests']
        server.serve_forever()
