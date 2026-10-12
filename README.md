# ai-platform-demo

**Three teams, one platform, with AI in the pipeline.**

A small reference repo showing how I approach two problems: getting several
engineering teams to deploy similar stacks *consistently*, and making AI
useful in the delivery pipeline *safely*.

## The problem it models

Three product teams each run a similar containerized API on AWS. Without a
platform, each team writes its own VPC, load balancer, IAM and alarms, so you
end up with three versions of the same thing, three sets of bugs, and drift
between what's in Git and what's actually running.

## How it's solved

| Problem | What this repo does |
|---|---|
| Teams reinventing the wheel | Shared `modules/network` and `modules/ecs-service`; each `teams/*` stack is about 60 lines of inputs |
| Inconsistent safety | Every service gets health checks, autoscaling, a deploy circuit breaker with auto-rollback, and 5xx and unhealthy-host alarms by default |
| Bad config reaching prod | PR gate: `fmt`, `tflint`, Checkov policy, unit tests, then a `plan` per affected team |
| Reviewers missing risk in plans | AI reviewer reads the diff **and** the plan output against `CLAUDE.md` standards and comments on the PR. It advises; humans approve |
| Console changes ("ClickOps") | Weekday drift detection with `plan -detailed-exitcode` opens an issue for the owning team |
| Testing before prod is manual | **Preview Test Agent** designs and runs tests against a preview deploy, reports bugs with exact repro requests |
| Slow first response to pages | **Incident Triage Agent** gathers deploys, service events, error logs and config diffs; hands on-call a cited hypothesis |
| One AI reviewer skims everything | **AI Review Panel**: security, reliability, cost and standards reviewers run in parallel; findings merged with a consensus score |
| Drift found, but what now? | **Drift Triage Agent** recommends CODIFY or REVERT per resource; deterministic risk can't be downgraded |
| Wasted CI time | `scripts/changed_stacks.py` plans only affected teams; a module change plans all of them |

## Layout

```
modules/
  network/        VPC, public/private subnets, NAT, flow logs, locked default SG
  ecs-service/    Fargate service, ALB, IAM, autoscaling, alarms, safe deploys
teams/
  team-a/ team-b/ team-c/   thin stacks: call modules, set inputs
agents/                     read-only AI agents + deterministic plan risk (see docs/agents.md)
examples/                   sample app with planted bugs, recorded incident, drift plan
scripts/changed_stacks.py   which stacks does this PR affect?
tests/                      pytest for platform scripts
CLAUDE.md                   standards for humans and AI tools
.github/workflows/
  pr-checks.yml             lint, policy, tests, plan, AI review
  drift-detection.yml       scheduled drift check + Drift Triage Agent
  preview-test.yml          Preview Test Agent (manual, or after a preview deploy)
docs/
  agents.md                 agent design, guardrails, how to run
  demo-script.md            3-minute walkthrough
  first-90-days.md          how I'd roll this out in a real org
```

## Run the checks locally

```bash
terraform fmt -recursive -check
tflint --init && tflint --recursive --config "$(pwd)/.tflint.hcl"
checkov -d . --framework terraform --compact --quiet
pytest -q tests/
(cd teams/team-a && terraform init -backend=false && terraform validate)
```

Current status: all stacks validate, tflint is clean, Checkov is 119 passed /
0 failed (29 inline skips, each with a written reason), and 33/33 tests pass
(script, agent loop, guardrails, plan risk, and agents run offline with a
scripted model).

## Turning on the optional parts

| Feature | Set in repo settings |
|---|---|
| Real `terraform plan` in PRs and drift detection | Variable `AWS_PLAN_ROLE_ARN` (read-only IAM role trusted for GitHub OIDC), and fill in `backend.hcl` |
| AI PR review | Variable `AI_REVIEW_ENABLED=true` and secret `ANTHROPIC_API_KEY` |
| AI Review Panel (4 specialists) | Variable `AI_REVIEW_PANEL=true` and secret `ANTHROPIC_API_KEY` |

Without these, the pipeline still runs every credential-free check.

## Notes

The container images in `teams/*/variables.tf` are placeholders; each team
would point at its own ECR image. This is a reference design, validated and
linted but not applied to a live AWS account.
