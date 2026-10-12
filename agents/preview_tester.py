"""Preview Test Agent: AI tests a running preview environment before merge.

Atmosphere priority #1: "enable AI to conduct more testing against software
applications before production."

The agent gets:
  * the list of endpoints the service exposes (a small JSON spec), and
  * an HTTP tool that can ONLY reach the preview environment's base URL.
It designs test cases (happy path, missing/invalid inputs, edge cases), runs
them, and reports PASS/FAIL with evidence. It cannot reach anything else, and
by default it may only send safe methods (GET/HEAD).

Usage:
  python -m agents.preview_tester --base-url http://localhost:8080 \
      --spec examples/sample_app_endpoints.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

from agents.core import AnthropicLLM, Tool, run_agent

SAFE_METHODS = {"GET", "HEAD"}

SYSTEM = """You are a QA engineer testing a PREVIEW deployment of a service before it is merged.
Goal: find real bugs a reviewer would want to know about before production.

Method:
1. Call list_endpoints first.
2. For each endpoint, test the happy path, then missing/invalid/edge-case inputs
   (empty values, wrong types, very large values, unknown IDs).
3. Treat any 5xx as a bug. A 4xx for bad input is correct behaviour.
4. Check response shape against what the endpoint description promises.
5. Stay within the tool budget; prefer a few high-value tests over many trivial ones.

Final answer: a Markdown report with
- a table: | # | Request | Expected | Actual | Result |
- a "Bugs found" section with reproduction steps (exact request) and likely cause
- a one-line verdict: SAFE TO MERGE or NEEDS FIXES
Never claim a test passed unless you ran it."""


class PreviewHttp:
    """HTTP client locked to one origin. This is the agent's only network access."""

    def __init__(self, base_url: str, allow_writes: bool = False, timeout: float = 10.0):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid base URL: {base_url}")
        self.base_url = base_url.rstrip("/") + "/"
        self.origin = (parsed.scheme, parsed.netloc)
        self.allowed = SAFE_METHODS | ({"POST", "PUT", "PATCH"} if allow_writes else set())
        self.timeout = timeout

    def resolve(self, path: str) -> str:
        if "://" in path or path.startswith("//") or "\\" in path:
            raise PermissionError(f"Blocked: '{path}' is not a relative path on the preview environment")
        url = urljoin(self.base_url, path.lstrip("/"))
        p = urlparse(url)
        if (p.scheme, p.netloc) != self.origin:
            raise PermissionError(f"Blocked: {url} is outside the preview environment {self.base_url}")
        return url

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        method = method.upper()
        if method not in self.allowed:
            raise PermissionError(f"Method {method} not allowed. Allowed: {sorted(self.allowed)}")
        url = self.resolve(path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, text = resp.status, resp.read(4000).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            status, text = exc.code, exc.read(4000).decode("utf-8", "replace")
        return {"request": f"{method} {path}", "status": status, "body": text}


def build_tools(http: PreviewHttp, spec: list[dict]) -> list[Tool]:
    return [
        Tool(
            name="list_endpoints",
            description="List the endpoints this service exposes, with parameters and expected behaviour.",
            input_schema={"type": "object", "properties": {}},
            func=lambda: spec,
        ),
        Tool(
            name="http_request",
            description="Send one HTTP request to the preview environment. Path is relative, e.g. '/api/x?y=1'.",
            input_schema={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "HEAD", "POST", "PUT", "PATCH"]},
                    "path": {"type": "string"},
                    "body": {"type": "object"},
                },
                "required": ["method", "path"],
            },
            func=http.request,
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--spec", required=True, help="JSON list of endpoints")
    ap.add_argument("--allow-writes", action="store_true", help="Also allow POST/PUT/PATCH")
    ap.add_argument("--max-steps", type=int, default=15)
    args = ap.parse_args(argv)

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    http = PreviewHttp(args.base_url, allow_writes=args.allow_writes)
    result = run_agent(AnthropicLLM(), SYSTEM, f"Test the preview at {args.base_url}.",
                       build_tools(http, spec), max_steps=args.max_steps)
    print(result.final_text)
    print()
    print(result.audit_markdown())
    return 1 if "NEEDS FIXES" in result.final_text or result.hit_step_limit else 0


if __name__ == "__main__":
    sys.exit(main())
