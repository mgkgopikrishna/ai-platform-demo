"""Deterministic risk analysis of `terraform show -json <plan>` output.

This runs BEFORE any LLM. Facts like "this plan destroys a database" come from
code, not from a model's opinion. Agents then explain and prioritise them.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}

STATEFUL_TYPES = (
    "aws_db_instance", "aws_rds_cluster", "aws_dynamodb_table", "aws_s3_bucket",
    "aws_elasticache_cluster", "aws_efs_file_system", "aws_lb",
)
OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


@dataclass
class Finding:
    severity: str
    address: str
    kind: str
    detail: str


def _action(actions: list[str]) -> str:
    s = set(actions)
    if s == {"delete", "create"}:
        return "replace"
    if "delete" in s:
        return "delete"
    if "create" in s:
        return "create"
    if "update" in s:
        return "update"
    return "no-op"


def _open_ingress(rc: dict, side: str = "after") -> bool:
    after = (rc.get("change") or {}).get(side) or {}
    if rc["type"] == "aws_vpc_security_group_ingress_rule":
        return after.get("cidr_ipv4") in OPEN_CIDRS or after.get("cidr_ipv6") in OPEN_CIDRS
    if rc["type"] == "aws_security_group":
        for rule in after.get("ingress") or []:
            cidrs = set(rule.get("cidr_blocks") or []) | set(rule.get("ipv6_cidr_blocks") or [])
            if OPEN_CIDRS & cidrs:
                return True
    if rc["type"] == "aws_security_group_rule" and after.get("type") == "ingress":
        return bool(OPEN_CIDRS & set(after.get("cidr_blocks") or []))
    return False


def analyze_changes(resource_changes: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    for rc in resource_changes:
        addr, rtype = rc["address"], rc["type"]
        act = _action((rc.get("change") or {}).get("actions", []))
        if act == "no-op":
            continue
        stateful = rtype.startswith(STATEFUL_TYPES)
        if act in ("delete", "replace"):
            sev = HIGH if stateful else MEDIUM
            what = "stateful resource (possible data loss or outage)" if stateful else "resource"
            findings.append(Finding(sev, addr, act, f"Plan will {act} this {what}."))
        if rtype.startswith("aws_iam_") and act in ("create", "update", "replace"):
            findings.append(Finding(MEDIUM, addr, "iam", f"IAM change ({act}); check it does not widen access."))
        if act in ("create", "update", "replace") and _open_ingress(rc):
            findings.append(Finding(HIGH, addr, "open-ingress", "Ingress open to the internet (0.0.0.0/0 or ::/0)."))
        elif act == "update" and _open_ingress(rc, "before") and not _open_ingress(rc, "after"):
            findings.append(Finding(HIGH, addr, "live-open-ingress",
                                    "LIVE infrastructure is open to the internet right now; this plan would close it."))
    return findings


def overall(findings: list[Finding]) -> str:
    return max((f.severity for f in findings), key=_ORDER.__getitem__, default=LOW)


def summarize_plan(plan: dict) -> dict:
    changes = plan.get("resource_changes") or []
    counts = {"create": 0, "update": 0, "delete": 0, "replace": 0}
    for rc in changes:
        a = _action((rc.get("change") or {}).get("actions", []))
        if a in counts:
            counts[a] += 1
    findings = analyze_changes(changes)
    drifted = [d["address"] for d in plan.get("resource_drift") or []]
    return {
        "counts": counts,
        "risk": overall(findings),
        "findings": [asdict(f) for f in findings],
        "drifted_resources": drifted,
    }


def load_plan(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def to_markdown(summary: dict, title: str) -> str:
    c = summary["counts"]
    out = [f"### Policy risk: {title} — **{summary['risk']}**", "",
           f"create {c['create']} · update {c['update']} · replace {c['replace']} · delete {c['delete']}", ""]
    if summary["findings"]:
        out += ["| Severity | Resource | Finding |", "|---|---|---|"]
        out += [f"| {f['severity']} | `{f['address']}` | {f['detail']} |" for f in summary["findings"]]
    else:
        out.append("No risky changes detected.")
    return "\n".join(out)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        sys.exit("usage: python -m agents.plan_risk <plan.json> <title>")
    print(to_markdown(summarize_plan(load_plan(sys.argv[1])), sys.argv[2]))
