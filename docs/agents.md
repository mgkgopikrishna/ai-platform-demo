# Platform AI Agents

Four small agents, each aimed at a specific Atmosphere pain point. They are
not a framework; they are about 150 lines each on one shared loop (`agents/core.py`).

| Agent | Problem it targets | Runs when | Can it change anything? |
|---|---|---|---|
| **Preview Test Agent** (`preview_tester.py`) | Priority #1: AI testing apps *before* production | After a PR's preview environment deploys | No. HTTP only to the preview URL; GET/HEAD by default |
| **Incident Triage Agent** (`incident_triage.py`) | One platform engineer on escalation for three teams; context-gathering is the slow part of a page | When an alarm fires (or on demand by on-call) | No. AWS Describe/Get/FilterLogEvents only |
| **AI Review Panel** (`review_panel.py`) | Priority #1: better AI code review before code ships | On every PR (optional job) | No. Reads the diff, standards, plan risk and repo code |
| **Drift Triage Agent** (`drift_triage.py`) | "Keep declared state and reality converged"; detection is easy, deciding codify vs revert is the work | When the drift workflow finds drift | No. Reads plan JSON and repo files |

Plus `plan_risk.py`: **deterministic** Terraform plan analysis (replacements of
stateful resources, IAM changes, internet-open ingress, including drift where
live infra is currently exposed). It runs before any AI, in PR checks and in
drift triage.

## The Review Panel (multi-agent, consensus)

Inspired by multi-agent "swarm" systems such as MiroFish, but applied to a
concrete, verifiable problem instead of open-ended prediction.

1. Four specialists (**security, reliability, cost, platform standards**) review the
   same PR **independently and in parallel**, each narrowly focused. One generalist
   reviewer tends to skim; narrow reviewers go deeper in their own area.
2. Each returns structured JSON findings.
3. **Plain code merges them**: similar findings on the same file are grouped and get
   a consensus score ("flagged by 3/4 reviewers"). Higher consensus means higher
   confidence; single-reviewer findings are still shown, just ranked lower.
4. The final risk is the max of the panel and the **deterministic plan risk**,
   so the panel can raise severity but never lower it.
5. A reviewer that returns unparseable output is **reported**, never silently
   dropped, so you always know which areas went unreviewed.

Trade-off to be honest about: four reviewers cost about four times one review.
Worth it on module changes that affect every team; for small team-only PRs the
single reviewer in `pr-checks.yml` is enough.

## Design principles

1. **Deterministic first, AI second.** Facts ("this plan replaces a database")
   come from code. The model explains and prioritises; it cannot downgrade a
   HIGH finding. Same pattern as my DevOps-Autopilot project.
2. **Read-only and least privilege.** Each agent gets an explicit allowlist of
   tools. Unknown tool names are rejected. The preview tester's HTTP client is
   locked to one origin (it cannot reach the cloud metadata endpoint, for
   example) and refuses writes unless `--allow-writes` is passed.
3. **Humans act.** Agents produce a report with evidence and a recommended next
   step. Nothing restarts, rolls back, applies or merges on an agent's say-so.
4. **Bounded.** Hard step limits and truncated tool output keep cost and
   runaway loops in check.
5. **Auditable.** Every report ends with the exact tool calls the agent made.
6. **Testable offline.** The model is injected. Tests drive the real loop and
   real tools with a scripted fake model; no API key needed in CI.

## Try it locally

```bash
pip install -r agents/requirements.txt
export ANTHROPIC_API_KEY=...            # only needed for the AI part

# Deterministic only, no key needed
python -m agents.drift_triage --plan examples/fixtures/drift_plan.json --team team-a --no-llm

# Preview Test Agent vs the sample app (2 planted bugs)
python examples/sample_app.py 8080 &
python -m agents.preview_tester --base-url http://localhost:8080 --spec examples/sample_app_endpoints.json

# Incident Triage Agent replaying a recorded bad deploy
python -m agents.incident_triage --cluster team-a-prod-api --service team-a-prod-api \
  --alarm team-a-prod-api-5xx-rate --fixtures examples/fixtures/incident_bad_deploy.json

# AI Review Panel on a deliberately risky PR (SSH open, circuit breaker removed, NAT cost, S3 in a team stack)
python -m agents.review_panel --diff examples/fixtures/risky_pr.diff

# Drift Triage Agent with AI recommendations
python -m agents.drift_triage --plan examples/fixtures/drift_plan.json --team team-a
```

The model defaults to `claude-sonnet-5-5`; override with `AGENT_MODEL`.

## What's verified vs not

Verified offline (`pytest tests/`): the agent loop, tool allowlisting, error
handling, step limits, the HTTP origin guard, the planted bugs being
reproducible, the incident evidence chain, plan risk rules, and the review
panel's parallel run, parsing, consensus merge and deterministic floor.

Not verified here: live model output quality (needs an API key) and the
`AwsBackend` against a real account. Model output varies run to run; that's
why the deterministic layer and the audit trail exist.

## What I'd build next in a real org

1. Per-PR preview environments, so the Preview Test Agent runs on every PR automatically.
2. Feed the agents' reports back as data: which findings did engineers act on? Prune what's noise.
3. Expose the read-only tools over MCP so engineers' own AI coding tools can use the same safe access.
