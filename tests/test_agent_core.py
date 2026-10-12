from conftest import ScriptedLLM, final_turn, tool_turn

from agents.core import Tool, run_agent

ECHO = Tool("echo", "echo", {"type": "object", "properties": {"x": {"type": "string"}}}, lambda x: {"echo": x})
BOOM = Tool("boom", "fails", {"type": "object", "properties": {}}, lambda: 1 / 0)


def test_tool_result_is_fed_back_and_final_text_returned():
    llm = ScriptedLLM([tool_turn(("echo", {"x": "hi"})), final_turn("done")])
    res = run_agent(llm, "sys", "task", [ECHO])
    assert res.final_text == "done"
    assert res.steps == 2
    assert res.tool_calls[0].output.find('"echo": "hi"') != -1
    last_user = llm.seen[1]["messages"][-1]
    assert last_user["content"][0]["type"] == "tool_result"


def test_unknown_tool_is_rejected_not_executed():
    llm = ScriptedLLM([tool_turn(("delete_everything", {})), final_turn("ok")])
    res = run_agent(llm, "sys", "task", [ECHO])
    assert res.tool_calls[0].is_error
    assert "Unknown tool" in res.tool_calls[0].output


def test_tool_exception_goes_back_to_model_as_error():
    llm = ScriptedLLM([tool_turn(("boom", {})), final_turn("handled")])
    res = run_agent(llm, "sys", "task", [BOOM])
    assert res.tool_calls[0].is_error
    assert "ZeroDivisionError" in res.tool_calls[0].output
    assert res.final_text == "handled"


def test_step_limit_stops_a_looping_agent():
    llm = ScriptedLLM([tool_turn(("echo", {"x": str(i)})) for i in range(10)])
    res = run_agent(llm, "sys", "task", [ECHO], max_steps=3)
    assert res.hit_step_limit
    assert len(res.tool_calls) == 3


def test_only_registered_tools_are_offered_to_model():
    llm = ScriptedLLM([final_turn("x")])
    run_agent(llm, "sys", "task", [ECHO])
    assert llm.seen[0]["tools"] == ["echo"]


def test_audit_trail_lists_every_call():
    llm = ScriptedLLM([tool_turn(("echo", {"x": "a"}), ("echo", {"x": "b"})), final_turn("x")])
    res = run_agent(llm, "sys", "task", [ECHO])
    audit = res.audit_markdown()
    assert "2 tool calls" in audit and '{"x": "b"}' in audit
