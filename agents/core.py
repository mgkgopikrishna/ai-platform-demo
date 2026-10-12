"""Minimal, auditable agent loop on top of the Anthropic Messages API (tool use).

Design rules (the same for every agent in this repo):
  1. Tools are explicit and allowlisted. The model can only call what we register.
  2. Tools are read-only by default. Agents investigate and recommend; humans act.
  3. Every tool call is recorded, so a reviewer can see exactly what the agent did.
  4. Hard step limit, so a confused agent stops instead of looping (and spending).
  5. The LLM is injected, so tests run offline with a scripted fake.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
MAX_TOOL_RESULT_CHARS = 8000


class LLM(Protocol):
    def create(self, *, system: str, messages: list[dict], tools: list[dict]) -> dict:
        """Return {"content": [blocks], "stop_reason": str}."""


class AnthropicLLM:
    """Real model client. Needs ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 2000):
        import anthropic  # imported lazily so offline tests don't need it

        self._client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def create(self, *, system: str, messages: list[dict], tools: list[dict]) -> dict:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        blocks: list[dict] = []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        return {"content": blocks, "stop_reason": resp.stop_reason}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    func: Callable[..., Any]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass
class ToolCall:
    name: str
    input: dict
    output: str
    is_error: bool


@dataclass
class AgentResult:
    final_text: str
    steps: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    hit_step_limit: bool = False

    def audit_markdown(self) -> str:
        lines = ["<details><summary>Agent audit trail "
                 f"({len(self.tool_calls)} tool calls, {self.steps} steps)</summary>", ""]
        for i, c in enumerate(self.tool_calls, 1):
            flag = " (error)" if c.is_error else ""
            lines.append(f"{i}. `{c.name}({json.dumps(c.input)})`{flag}")
        lines += ["", "</details>"]
        return "\n".join(lines)


def _truncate(text: str) -> str:
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + f"\n...[truncated {len(text) - MAX_TOOL_RESULT_CHARS} chars]"


def run_agent(llm: LLM, system: str, task: str, tools: list[Tool], max_steps: int = 10) -> AgentResult:
    registry = {t.name: t for t in tools}
    specs = [t.spec() for t in tools]
    messages: list[dict] = [{"role": "user", "content": task}]
    calls: list[ToolCall] = []

    for step in range(1, max_steps + 1):
        resp = llm.create(system=system, messages=messages, tools=specs)
        content = resp["content"]
        messages.append({"role": "assistant", "content": content})

        tool_uses = [b for b in content if b["type"] == "tool_use"]
        if resp["stop_reason"] != "tool_use" or not tool_uses:
            text = "\n".join(b["text"] for b in content if b["type"] == "text").strip()
            return AgentResult(final_text=text, steps=step, tool_calls=calls)

        results = []
        for use in tool_uses:
            tool = registry.get(use["name"])
            if tool is None:
                out, err = f"Unknown tool '{use['name']}'. Allowed: {sorted(registry)}", True
            else:
                try:
                    value = tool.func(**use["input"])
                    out = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
                    err = False
                except Exception as exc:  # tool errors go back to the model, not up the stack
                    out, err = f"{type(exc).__name__}: {exc}", True
            out = _truncate(out)
            calls.append(ToolCall(use["name"], use["input"], out, err))
            results.append({"type": "tool_result", "tool_use_id": use["id"], "content": out, "is_error": err})
        messages.append({"role": "user", "content": results})

    return AgentResult(
        final_text="Stopped: step limit reached before the agent finished. Review the audit trail.",
        steps=max_steps,
        tool_calls=calls,
        hit_step_limit=True,
    )
