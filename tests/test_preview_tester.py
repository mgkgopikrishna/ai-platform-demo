import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import ScriptedLLM, final_turn, tool_turn

from agents.core import run_agent
from agents.preview_tester import PreviewHttp, build_tools
from examples.sample_app import Handler

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_guard_blocks_other_hosts():
    http = PreviewHttp("http://preview-123.internal")
    with pytest.raises(PermissionError):
        http.resolve("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(PermissionError):
        http.resolve("//evil.example.com/x")


def test_guard_blocks_unsafe_methods_by_default():
    http = PreviewHttp("http://preview-123.internal")
    with pytest.raises(PermissionError):
        http.request("DELETE", "/api/venues/1")
    with pytest.raises(PermissionError):
        http.request("POST", "/api/x", {"a": 1})


def test_sample_app_planted_bugs_are_reproducible(app_url):
    http = PreviewHttp(app_url)
    assert http.request("GET", "/healthz")["status"] == 200
    assert http.request("GET", "/api/venues/1/schedule")["status"] == 200
    assert http.request("GET", "/api/venues/999/schedule")["status"] == 404
    assert http.request("GET", "/api/venues/abc/schedule")["status"] == 500  # bug 1
    assert http.request("GET", "/api/channels?limit=0")["status"] == 500     # bug 2


def test_agent_loop_runs_real_requests_against_preview(app_url):
    spec = json.loads((ROOT / "examples/sample_app_endpoints.json").read_text())
    llm = ScriptedLLM([
        tool_turn(("list_endpoints", {})),
        tool_turn(("http_request", {"method": "GET", "path": "/api/venues/abc/schedule"}),
                  ("http_request", {"method": "GET", "path": "http://169.254.169.254/"})),
        final_turn("NEEDS FIXES"),
    ])
    res = run_agent(llm, "sys", "test it", build_tools(PreviewHttp(app_url), spec))
    by_input = {c.input.get("path"): c for c in res.tool_calls if c.name == "http_request"}
    assert '"status": 500' in by_input["/api/venues/abc/schedule"].output
    assert by_input["http://169.254.169.254/"].is_error  # metadata endpoint blocked
