# 3-Minute Demo Script (for the call with Brent)

**When to use it:** only after he asks how you'd approach AI workflows or the
three-teams problem. Offer, don't push:

> "I actually put together a small example of how I'd approach this. Happy to share my screen for three minutes if it's useful."

## 0:00–0:30 · The problem (README)
> "This models your situation: three teams deploying similar stacks. Without a platform, each team builds its own VPC, load balancer and alarms, so you get three versions of the same thing plus drift."

## 0:30–1:15 · Shared modules (teams/team-a/main.tf, then modules/ecs-service/main.tf)
> "A team stack is about 60 lines. It just calls the shared modules. The module gives every service the same baseline: health checks, autoscaling, a deployment circuit breaker that auto-rolls back a bad deploy, and default 5xx alarms. The safe path is the default path."

Point at: `deployment_circuit_breaker`, the alarms, and the `:latest` validation.

## 1:15–2:15 · The pipeline and AI review (.github/workflows/pr-checks.yml, then CLAUDE.md)
> "Every PR runs fmt, tflint, Checkov and unit tests, then plans only the teams it affects; a module change plans all three. Then an AI reviewer reads the diff *and* the plan output against CLAUDE.md, our written standards. It's looking for things linters can't judge: a resource being replaced, IAM widening, a team copying logic that belongs in a module. It comments; a human approves. AI proposes, humans approve, pipelines verify."

> "CLAUDE.md matters because it's the same rules for engineers and AI tools. When an engineer uses Cursor or Claude Code locally, the tool reads the same standards."

## 2:15–2:45 · Drift (.github/workflows/drift-detection.yml)
> "Weekdays, it plans against live infrastructure. If someone changed something in the console, it opens an issue for that team. That's how declared state and reality stay converged."

## Optional +2 min · The agents (docs/agents.md, then examples/)
Only if he's engaged and asks "what would you build?"
> "I took the three pain points from your role and built a small read-only agent for each: one that tests a preview environment before merge, one that does first-response triage when an alarm fires, and one that tells you whether drift should be codified or reverted. The rule for all of them: deterministic checks first, the AI explains and recommends, a human acts. The preview tester can only reach the preview URL, and every report ends with the exact tool calls it made."

Show: `examples/fixtures/incident_bad_deploy.json`. Explain the story (a deploy removed an env var, so 5xx errors started, then the circuit breaker rolled back) and how the agent connects those dots.

## 2:45–3:00 · Close
> "I built this with Claude Code, which is honestly how I work day to day. The next step in a real org would be ephemeral preview environments, so AI agents can actually test the running app before merge, not just review the code."

---

## Be ready for these (answer honestly)

**"Did you build this yourself?"**
> "I designed it and built it with Claude Code. That's the point: I directed it, reviewed every file, and ran validate, tflint, Checkov and the tests until they were clean."

**"Has this run against real AWS?"**
> "It validates and passes lint and policy checks, but I haven't applied it to a live account. The plan and drift jobs switch on when you give the pipeline a read-only OIDC role."

**"Why skip some Checkov checks?"**
> "Policy should be enforced, but exceptions must be visible. Each skip is inline with a reason a reviewer can challenge, like WAF being owned by the security team. Silent exceptions are what cause trouble."

**"What could go wrong with AI review?"**
> "Noise and false confidence. So it never approves or merges, it's told not to repeat what linters catch, it ends with a risk rating, and I'd track whether teams actually act on its comments. If they ignore it, it's noise, and I'd tune or remove it."

**"Why Terraform modules instead of each team owning everything?"**
> "Teams should own *what* is different about their service, not re-solve networking and alarms. Shared modules mean a fix lands once and every team gets it on the next plan."

**"Do these agents actually work?"**
> "The loop, the guardrails and the tools are covered by 33 offline tests, with a scripted model standing in for the LLM. Live output quality depends on the model, which is exactly why facts come from deterministic code and every report shows its audit trail. In a real rollout I'd measure how often engineers act on the findings."

**"Why four reviewers instead of one?"**
> "A single generalist reviewer skims. Narrow specialists go deeper, and when two or three independently flag the same line, that's a strong signal. The merge is plain code, not another AI, so the verdict is reproducible. It costs about four times as much, so I'd use it on shared-module changes, not every small PR."

**"Why not let the agent fix things itself?"**
> "Trust is earned. Read-only first, measure accuracy, then maybe allow low-risk actions behind approval, like opening a PR. Never direct changes to prod."

**"How would you get teams to adopt this?"**
> "Pilot with one team, fix what annoys them, then show the numbers. If the paved road is faster, people choose it."
