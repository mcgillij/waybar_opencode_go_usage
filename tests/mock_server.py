#!/usr/bin/env python3
"""Mock OpenCode API on 127.0.0.1:8931 with the PR's fixture data.

Usage: python3 mock_server.py [go|rl|zen|none]
  go   -> Go subscription answers (403 on Zen billing)
  rl   -> Go rolling window rate-limited
  zen  -> Zen-only account (403 on Go usage)
  none -> 401 everywhere
"""
import http.server
import json
import sys

GO = {
    "usage": {
        "rolling": {"status": "ok", "percent": 28,
                    "resetsAt": "2026-11-18T18:00:00Z"},
        "weekly": {"status": "ok", "percent": 40,
                   "resetsAt": "2026-11-23T00:00:00Z"},
        "monthly": {"status": "ok", "percent": 61,
                    "resetsAt": "2026-12-01T00:00:00Z"},
    }
}
RL = {"usage": {"rolling": {"status": "rate-limited", "percent": 97,
                            "resetsAt": "2026-11-18T18:00:00Z"}}}
ZEN = {"balanceMicroCents": "1234000000"}
ERR = {"type": "error", "error": {"type": "EntitlementError",
                                  "message": "no subscription"}}

MODE = sys.argv[1] if len(sys.argv) > 1 else "go"
ROUTES = {
    ("go", "/zen/go/v1/usage"): (200, GO),
    ("rl", "/zen/go/v1/usage"): (200, RL),
    ("zen", "/zen/go/v1/usage"): (403, ERR),
    ("zen", "/console/api/billing/status"): (200, ZEN),
    ("go", "/console/api/billing/status"): (403, ERR),
    ("none", "/zen/go/v1/usage"): (401, ERR),
    ("none", "/console/api/billing/status"): (401, ERR),
}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code, obj = ROUTES.get((MODE, self.path), (404, {"error": "nope"}))
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


http.server.HTTPServer(("127.0.0.1", 8931), H).serve_forever()
