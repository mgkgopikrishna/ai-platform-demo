"""Incident Triage Agent: first responder for an alarm, read-only.

Atmosphere context: one platform engineer on an escalation path for three
teams. When a page fires at 2am, the slowest part is gathering context:
what changed, what the service is saying, what the logs say. This agent does
that gathering in under a minute and hands the human a hypothesis with evidence.

It can ONLY read. It never restarts, scales, rolls back or edits anything.

Usage:
  # against recorded fixtures (demo / tests)
  python -m agents.incident_triage --cluster team-a-prod-api --service team-a-prod-api \
      --alarm "team-a-prod-api-5xx-rate" --fixtures examples/fixtures/incident_bad_deploy.json
  # against real AWS (read-only IAM role)
  python -m agents.incident_triage --cluster ... --service ... --alarm ... --region us-east-1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Protocol

from agents.core import AnthropicLLM, Tool, run_agent

SYSTEM = """You are an on-call SRE doing first-response triage. You have READ-ONLY tools.

Method:
1. Establish the timeline: when did the alarm start, and what deployed or changed shortly before?
2. Check the ECS service events (failed tasks, circuit breaker rollbacks, health-check failures).
3. Read recent error logs and look for the first new error, not the loudest one.
4. Correlate: does the first error line up with a deploy or config change?

Final answer in Markdown:
## Summary  (one sentence)
## Most likely cause  (with confidence: high / medium / low)
## Evidence  (numbered; each item cites the tool output it came from, with timestamps)
## Recommended next step for the human  (concrete; e.g. "roll back to task definition :41")
## What I could not determine
Never invent evidence. If the data does not support a conclusion, say so."""


class Backend(Protocol):
    def service_events(self, cluster: str, service: str, limit: int) -> list[dict]: ...
    def deployments(self, cluster: str, service: str) -> list[dict]: ...
    def error_logs(self, log_group: str, minutes: int, limit: int) -> list[dict]: ...
    def alarm_history(self, alarm_name: str, limit: int) -> list[dict]: ...
    def task_definition_diff(self, current: str, previous: str) -> dict: ...


class FixtureBackend:
    """Replays a recorded incident from JSON, so the agent can be demoed and tested offline."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as fh:
            self.data = json.load(fh)

    def service_events(self, cluster, service, limit=20):
        return self.data["service_events"][:limit]

    def deployments(self, cluster, service):
        return self.data["deployments"]

    def error_logs(self, log_group, minutes=30, limit=50):
        return self.data["error_logs"][:limit]

    def alarm_history(self, alarm_name, limit=10):
        return self.data["alarm_history"][:limit]

    def task_definition_diff(self, current, previous):
        return self.data["task_definition_diff"]


class AwsBackend:
    """Real AWS calls. Every call here is a read (Describe*/Get*/FilterLogEvents)."""

    def __init__(self, region: str):
        import boto3

        self.ecs = boto3.client("ecs", region_name=region)
        self.logs = boto3.client("logs", region_name=region)
        self.cw = boto3.client("cloudwatch", region_name=region)

    def _service(self, cluster, service):
        return self.ecs.describe_services(cluster=cluster, services=[service])["services"][0]

    def service_events(self, cluster, service, limit=20):
        return [{"at": e["createdAt"].isoformat(), "message": e["message"]}
                for e in self._service(cluster, service)["events"][:limit]]

    def deployments(self, cluster, service):
        return [{"task_definition": d["taskDefinition"].split("/")[-1], "status": d["status"],
                 "rollout_state": d.get("rolloutState"), "created_at": d["createdAt"].isoformat(),
                 "running": d["runningCount"], "failed_tasks": d.get("failedTasks", 0)}
                for d in self._service(cluster, service)["deployments"]]

    def error_logs(self, log_group, minutes=30, limit=50):
        start = int((time.time() - minutes * 60) * 1000)
        resp = self.logs.filter_log_events(
            logGroupName=log_group, startTime=start, limit=limit,
            filterPattern='?ERROR ?Error ?Exception ?Traceback ?FATAL')
        return [{"at": e["timestamp"], "message": e["message"][:500]} for e in resp["events"]]

    def alarm_history(self, alarm_name, limit=10):
        resp = self.cw.describe_alarm_history(AlarmName=alarm_name, HistoryItemType="StateUpdate",
                                              MaxRecords=limit)
        return [{"at": h["Timestamp"].isoformat(), "summary": h["HistorySummary"]}
                for h in resp["AlarmHistoryItems"]]

    def task_definition_diff(self, current, previous):
        def env_and_image(td):
            c = self.ecs.describe_task_definition(taskDefinition=td)["taskDefinition"]["containerDefinitions"][0]
            return {"image": c["image"], "environment": {e["name"]: e["value"] for e in c.get("environment", [])},
                    "secrets": sorted(s["name"] for s in c.get("secrets", []))}
        a, b = env_and_image(previous), env_and_image(current)
        return {
            "image": {"previous": a["image"], "current": b["image"]},
            "env_added": sorted(set(b["environment"]) - set(a["environment"])),
            "env_removed": sorted(set(a["environment"]) - set(b["environment"])),
            "secrets_added": sorted(set(b["secrets"]) - set(a["secrets"])),
            "secrets_removed": sorted(set(a["secrets"]) - set(b["secrets"])),
        }


def build_tools(backend: Backend, cluster: str, service: str, log_group: str) -> list[Tool]:
    none = {"type": "object", "properties": {}}
    return [
        Tool("get_alarm_history", "State changes of the alarm that paged, newest first.",
             {"type": "object", "properties": {"alarm_name": {"type": "string"}}, "required": ["alarm_name"]},
             lambda alarm_name: backend.alarm_history(alarm_name, 10)),
        Tool("get_deployments", f"Current and recent ECS deployments of {service}.", none,
             lambda: backend.deployments(cluster, service)),
        Tool("get_service_events", f"Recent ECS service events for {service}, newest first.", none,
             lambda: backend.service_events(cluster, service, 20)),
        Tool("get_error_logs", f"Error lines from {log_group} in the last N minutes.",
             {"type": "object", "properties": {"minutes": {"type": "integer", "minimum": 5, "maximum": 180}}},
             lambda minutes=30: backend.error_logs(log_group, minutes, 50)),
        Tool("diff_task_definitions", "Compare two task definitions: image, env vars and secrets added/removed.",
             {"type": "object", "properties": {"current": {"type": "string"}, "previous": {"type": "string"}},
              "required": ["current", "previous"]},
             lambda current, previous: backend.task_definition_diff(current, previous)),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cluster", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--alarm", required=True)
    ap.add_argument("--log-group", help="Defaults to /ecs/<service>")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixtures")
    src.add_argument("--region")
    args = ap.parse_args(argv)

    backend: Backend = FixtureBackend(args.fixtures) if args.fixtures else AwsBackend(args.region)
    tools = build_tools(backend, args.cluster, args.service, args.log_group or f"/ecs/{args.service}")
    task = f"Alarm '{args.alarm}' is firing for service {args.service} in cluster {args.cluster}. Triage it."
    result = run_agent(AnthropicLLM(), SYSTEM, task, tools, max_steps=10)
    print(result.final_text)
    print()
    print(result.audit_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
