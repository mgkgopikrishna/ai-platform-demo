"""Tiny stand-in for a team's API (stdlib only), used to demo the Preview Test Agent.

It has two deliberate bugs that a good tester should find:
  1. A non-numeric venue id returns 500 instead of 400.
  2. limit=0 on /api/channels returns 500 (division by zero) instead of 400.

Run:  python examples/sample_app.py 8080
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VENUES = {1: "Downtown Gym", 2: "Airport Gate B12", 3: "Sports Bar Austin"}
CHANNELS = [
    {"id": "sports-1", "category": "sports"}, {"id": "sports-2", "category": "sports"},
    {"id": "trivia-1", "category": "games"}, {"id": "news-1", "category": "news"},
]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep demo output quiet
        pass

    def do_GET(self):
        try:
            url = urlparse(self.path)
            q = parse_qs(url.query)
            parts = [p for p in url.path.split("/") if p]
            if url.path == "/healthz":
                return self._send(200, {"status": "ok"})
            if len(parts) == 4 and parts[:2] == ["api", "venues"] and parts[3] == "schedule":
                venue_id = int(parts[2])  # BUG 1: ValueError -> 500 for non-numeric ids
                if venue_id not in VENUES:
                    return self._send(404, {"error": "venue not found"})
                return self._send(200, {"venue": VENUES[venue_id],
                                        "schedule": [{"hour": h, "channel": "sports-1"} for h in range(9, 12)]})
            if url.path == "/api/channels":
                category = q.get("category", [None])[0]
                limit = int(q.get("limit", ["10"])[0])
                items = [c for c in CHANNELS if category in (None, c["category"])]
                pages = -(-len(items) // limit)  # BUG 2: limit=0 -> ZeroDivisionError -> 500
                return self._send(200, {"items": items[:limit], "pages": pages})
            return self._send(404, {"error": "not found"})
        except Exception as exc:
            return self._send(500, {"error": "internal server error", "type": type(exc).__name__})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"sample app on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
