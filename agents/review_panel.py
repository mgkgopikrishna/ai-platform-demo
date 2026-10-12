"""AI Review Panel: several specialist reviewers, run in parallel, merged by consensus.

Inspired by multi-agent "swarm" systems, but aimed at a concrete problem:
improving AI code review before code ships (Atmosphere priority #1).

  * Four specialists (security, reliability, cost, platform standards) review the
    same PR independently and in parallel, each with the same read-only tools.
  * Their findings are merged. Similar findings from different reviewers are
    grouped, and each merged finding carries a consensus score ("3/4 reviewers").
  * Deterministic plan risk is a floor: the panel can raise severity, never lower it.
  * The merge is plain code, not another LLM call, so the final verdict is reproducible
    from the specialists' outputs.

Usage:
  git diff origin/main...HEAD > pr.diff
  python -m agents.review_panel --diff pr.diff [--plan-json plan.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from agents.core import LLM, AnthropicLLM, Tool, run_agent
from agents.drift_triage import find_declaration
from agents.plan_risk import load_plan, summarize_plan

REPO_ROOT = Path(__file__).resolve().parent.parent
SEV_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

SPECIALISTS: dict[str, str] = {
    "security": "identity and network exposure: IAM widening, security groups open to the internet, "
                "public endpoints, missing TLS, secrets in plain config.",
    "reliability": "safe deploys and resilience: health checks, deployment settings, rollback, "
                   "autoscaling limits, single points of failure, missing alarms.",
    "cost": "cloud spend: NAT gateways, oversized tasks, unbounded autoscaling, log retention, "
            "resources that should be dev-only.",
    "platform": "platform standards in CLAUDE.md: logic copied into teams/* that belongs in a shared "
                "module, missing descriptions/validations, :latest tags, console-style one-offs.",
}

SYSTEM_TEMPLATE = """You are the {name} reviewer on a panel reviewing a Terraform pull request.
Your ONLY focus: {focus}
Other reviewers cover other areas; do not comment outside your focus.

Use the tools to read the diff, the platform standards, the deterministic plan risk, and
the code around anything suspicious. Report only real issues you can point to in the diff.

Reply with ONLY a JSON array (no prose), each item:
{{"severity": "HIGH|MEDIUM|LOW", "file": "path", "resource": "Terraform address the issue is about, e.g. aws_ecs_service.this or module.network", "issue": "one sentence", "fix": "one sentence"}}
Report each distinct problem separately, even if two problems touch the same resource.
Return [] if you find nothing in your area."""


@dataclass
class Finding:
    severity: str
    file: str
    issue: str
    fix: str
    resource: str = ""
    reviewers: list[str] = field(default_factory=list)


def parse_findings(text: str) -> list[dict] | None:
    """Pull the JSON array out of a model reply. Returns None if it can't."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    clean = []
    for it in items:
        if not isinstance(it, dict) or not it.get("issue"):
            continue
        sev = str(it.get("severity", "LOW")).upper()
        clean.append({"severity": sev if sev in SEV_ORDER else "LOW",
                      "file": str(it.get("file", "")), "resource": str(it.get("resource", "")).strip(),
                      "issue": str(it["issue"]),
                      "fix": str(it.get("fix", ""))})
    return clean


def _norm_resource(r: str) -> str:
    """'module.api.aws_ecs_service.this' and 'aws_ecs_service.this' are the same resource."""
    parts = [p for p in r.lower().replace('"', "").split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else ".".join(parts)


def _similar(a: Finding, b: dict) -> bool:
    if a.file != b["file"]:
        return False
    ra, rb = _norm_resource(a.resource), _norm_resource(b.get("resource", ""))
    if ra and rb:
        # Reviewers word the same problem very differently; the resource they point at is
        # the stable key. (A live run showed text similarity alone left duplicates unmerged.)
        return ra == rb
    return SequenceMatcher(None, a.issue.lower(), b["issue"].lower()).ratio() >= 0.55


def merge(results: dict[str, list[dict]]) -> list[Finding]:
    """Group similar findings across reviewers; keep the highest severity seen."""
    merged: list[Finding] = []
    for reviewer, items in results.items():
        for item in items:
            # A reviewer's own distinct findings never merge with each other; only
            # agreement between different reviewers raises consensus.
            match = next((m for m in merged if reviewer not in m.reviewers and _similar(m, item)), None)
            if match:
                if reviewer not in match.reviewers:
                    match.reviewers.append(reviewer)
                if SEV_ORDER[item["severity"]] > SEV_ORDER[match.severity]:
                    match.severity = item["severity"]
            else:
                merged.append(Finding(item["severity"], item["file"], item["issue"], item["fix"],
                                      item.get("resource", ""), [reviewer]))
    merged.sort(key=lambda f: (-SEV_ORDER[f.severity], -len(f.reviewers), f.file))
    return merged


def verdict(findings: list[Finding], deterministic_risk: str) -> str:
    panel = max((f.severity for f in findings), key=SEV_ORDER.__getitem__, default="LOW")
    return max(panel, deterministic_risk, key=SEV_ORDER.__getitem__)  # floor: never below code's verdict


def build_tools(diff: str, standards: str, plan_summary: dict | None) -> list[Tool]:
    none = {"type": "object", "properties": {}}
    return [
        Tool("get_diff", "The full PR diff.", none, lambda: diff),
        Tool("get_standards", "The platform standards (CLAUDE.md).", none, lambda: standards),
        Tool("get_plan_risk", "Deterministic plan risk computed by code (may be unavailable).", none,
             lambda: plan_summary or {"note": "No plan available for this PR."}),
        Tool("find_declaration", "Show the current Terraform code declaring a resource address.",
             {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]},
             find_declaration),
    ]


def run_panel(llm_factory: Callable[[str], LLM], diff: str, standards: str,
              plan_summary: dict | None = None, max_steps: int = 8) -> dict:
    tools = build_tools(diff, standards, plan_summary)

    def review(name: str):
        system = SYSTEM_TEMPLATE.format(name=name, focus=SPECIALISTS[name])
        try:
            return name, run_agent(llm_factory(name), system, "Review this pull request.", tools, max_steps), None
        except Exception as exc:  # one reviewer failing (API error, timeout) must not sink the panel
            return name, None, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=len(SPECIALISTS)) as pool:
        results = list(pool.map(review, SPECIALISTS))

    runs = {name: res for name, res, err in results if res is not None}
    errors = {name: err for name, res, err in results if err is not None}
    if len(errors) == len(SPECIALISTS):
        # Nothing reviewed at all: fail loudly instead of posting an empty "all clear".
        raise RuntimeError("Every reviewer failed: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))

    parsed, failed = {}, list(errors)
    for name, res in runs.items():
        items = parse_findings(res.final_text)
        if items is None:
            failed.append(name)  # surfaced, never silently dropped
            items = []
        parsed[name] = items

    det_risk = (plan_summary or {}).get("risk", "LOW")
    findings = merge(parsed)
    return {"findings": findings, "verdict": verdict(findings, det_risk), "deterministic_risk": det_risk,
            "failed_reviewers": failed, "errors": errors, "runs": runs}


def to_markdown(panel: dict) -> str:
    n = len(SPECIALISTS)
    out = [f"## AI Review Panel — overall risk: **{panel['verdict']}**", "",
           f"{n} specialist reviewers ran in parallel. Deterministic plan risk: "
           f"**{panel['deterministic_risk']}** (the panel can raise this, never lower it).", ""]
    if panel["failed_reviewers"]:
        out += [f"⚠️ No usable review from: {', '.join(panel['failed_reviewers'])}. Treat their area as unreviewed.", ""]
        for name, err in panel.get("errors", {}).items():
            out.append(f"   {name}: {err[:200]}")
        if panel.get("errors"):
            out.append("")
    if panel["findings"]:
        out += ["| Severity | Consensus | File | Issue | Suggested fix |", "|---|---|---|---|---|"]
        for f in panel["findings"]:
            out.append(f"| {f.severity} | {len(f.reviewers)}/{n} ({', '.join(f.reviewers)}) | `{f.file}` "
                       f"| {f.issue} | {f.fix} |")
    else:
        out.append("No issues found by the panel.")
    out += ["", "<details><summary>Audit trail per reviewer</summary>", ""]
    for name, res in panel["runs"].items():
        out += [f"**{name}**", "", res.audit_markdown(), ""]
    out.append("</details>")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff", required=True)
    ap.add_argument("--plan-json")
    ap.add_argument("--standards", default=str(REPO_ROOT / "CLAUDE.md"))
    args = ap.parse_args(argv)

    diff = Path(args.diff).read_text(encoding="utf-8")
    standards = Path(args.standards).read_text(encoding="utf-8")
    plan_summary = summarize_plan(load_plan(args.plan_json)) if args.plan_json else None
    panel = run_panel(lambda _name: AnthropicLLM(), diff, standards, plan_summary)
    print(to_markdown(panel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
