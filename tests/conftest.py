import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


class ScriptedLLM:
    """Plays back a fixed list of model turns, and records what it was sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def create(self, *, system, messages, tools):
        self.seen.append({"messages": [dict(m) for m in messages], "tools": [t["name"] for t in tools]})
        return self.turns.pop(0)


def tool_turn(*calls):
    return {"stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": f"t{i}", "name": n, "input": a} for i, (n, a) in enumerate(calls)]}


def final_turn(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}
