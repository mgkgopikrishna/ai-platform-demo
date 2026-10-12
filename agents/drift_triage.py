"""Drift Triage Agent: explains infrastructure drift and recommends codify vs revert.

Atmosphere JD: "keeping declared state and reality converged." The drift
workflow already detects drift; the hard part is deciding what to do about it.
This agent reads the plan, looks at the Terraform code that declares each
drifted resource, and recommends, per resource, whether to CODIFY (the console
change was intentional, so put it in Terraform) or REVERT (re-apply Terraform).

Deterministic risk analysis (plan_risk.py) runs first; the agent cannot
downgrade a HIGH finding.

Usage:
  terraform show -json tfplan > plan.json
  python -m agents.drift_triage --plan plan.json --team team-a [--no-llm]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agents.core import AnthropicLLM, Tool, run_agent
from agents.plan_risk import load_plan, summarize_plan

REPO_ROOT = Path(__file__).resolve().parent.parent

SYSTEM = """You are a platform engineer triaging Terraform drift for one team.

Method:
1. Call get_plan_summary. The risk level and findings in it are computed by code; you may
   explain them but you must never downgrade them.
2. For each changed or drifted resource, call find_declaration to see the Terraform that owns it.
3. Decide per resource: CODIFY (the live change looks intentional and safe; update Terraform)
   or REVERT (re-apply Terraform to restore the declared state). Explain why in one line.

Final answer in Markdown:
## Drift summary  (counts + overall risk, copied from the tool)
## Per-resource recommendation  (table: Resource | What changed | CODIFY/REVERT | Why)
## Suggested PR or command  (concrete)
Keep it short; this goes into a GitHub issue."""


def find_declaration(address: str) -> list[dict]:
    """Find where a resource address is declared in the repo's Terraform (read-only)."""
    parts = [p for p in address.split(".") if not p.startswith("module")]
    # address like module.api.aws_lb.this -> type=aws_lb, name=this
    rtype, rname = (parts[-2], parts[-1].split("[")[0]) if len(parts) >= 2 else (parts[0], "")
    needle = f'resource "{rtype}" "{rname}"'
    hits = []
    for tf in sorted(REPO_ROOT.rglob("*.tf")):
        if ".terraform" in tf.parts:
            continue
        lines = tf.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if needle in line:
                hits.append({"file": tf.relative_to(REPO_ROOT).as_posix(), "line": i + 1,
                             "snippet": "\n".join(lines[i:i + 25])})
    return hits or [{"note": f"No declaration found for {needle}"}]


def deterministic_report(team: str, summary: dict) -> str:
    c = summary["counts"]
    out = [f"## Drift summary: {team}", "",
           f"Overall risk: **{summary['risk']}** | create {c['create']}, update {c['update']}, "
           f"replace {c['replace']}, delete {c['delete']}", ""]
    if summary["drifted_resources"]:
        out += ["Drifted resources:", *[f"1. `{a}`" for a in summary["drifted_resources"]], ""]
    if summary["findings"]:
        out += ["| Severity | Resource | Finding |", "|---|---|---|"]
        out += [f"| {f['severity']} | `{f['address']}` | {f['detail']} |" for f in summary["findings"]]
    else:
        out.append("No risky changes detected by policy.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True, help="Output of terraform show -json")
    ap.add_argument("--team", required=True)
    ap.add_argument("--no-llm", action="store_true", help="Deterministic report only")
    args = ap.parse_args(argv)

    summary = summarize_plan(load_plan(args.plan))
    report = deterministic_report(args.team, summary)
    if args.no_llm:
        print(report)
        return 0

    tools = [
        Tool("get_plan_summary", "Deterministic summary of the drift plan: counts, risk, findings.",
             {"type": "object", "properties": {}}, lambda: summary),
        Tool("find_declaration", "Show the Terraform code that declares a resource address.",
             {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]},
             find_declaration),
    ]
    result = run_agent(AnthropicLLM(), SYSTEM, f"Triage drift for {args.team}.", tools, max_steps=12)
    print(result.final_text)
    print()
    print("<details><summary>Deterministic policy findings</summary>\n")
    print(report)
    print("\n</details>\n")
    print(result.audit_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
