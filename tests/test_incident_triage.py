from pathlib import Path

from conftest import ScriptedLLM, final_turn, tool_turn

from agents.core import run_agent
from agents.drift_triage import find_declaration
from agents.incident_triage import FixtureBackend, build_tools

ROOT = Path(__file__).resolve().parent.parent
FIX = str(ROOT / "examples/fixtures/incident_bad_deploy.json")


def test_tools_are_read_only_names():
    tools = build_tools(FixtureBackend(FIX), "c", "s", "/ecs/s")
    assert all(t.name.startswith(("get_", "diff_")) for t in tools)


def test_agent_can_gather_the_evidence_chain():
    llm = ScriptedLLM([
        tool_turn(("get_deployments", {}), ("get_error_logs", {"minutes": 30})),
        tool_turn(("diff_task_definitions", {"current": "team-a-prod-api:42", "previous": "team-a-prod-api:41"})),
        final_turn("Most likely cause: CONTENT_CDN_URL removed in :42"),
    ])
    res = run_agent(llm, "sys", "triage", build_tools(FixtureBackend(FIX), "c", "s", "/ecs/s"))
    outputs = " ".join(c.output for c in res.tool_calls)
    assert "KeyError: 'CONTENT_CDN_URL'" in outputs
    assert "CONTENT_CDN_URL" in res.tool_calls[-1].output
    assert not any(c.is_error for c in res.tool_calls)


def test_find_declaration_locates_module_resource():
    hits = find_declaration("module.api.aws_lb.this")
    assert hits[0]["file"] == "modules/ecs-service/main.tf"
    assert 'resource "aws_lb" "this"' in hits[0]["snippet"]
