# First 90 Days: Platform & AI Enablement

## Days 1–30: Listen and map
1. Sit with each of the three teams. Walk their path from commit to production and write down where they wait, guess or redo work.
2. Inventory the Terraform: what's shared, what's copy-pasted, what's in the console but not in code (run a drift check across everything).
3. Review on-call history and recent incidents: which pages were preventable?
4. Ship one quick, visible win, for example AI review on PRs in one repo, or cutting the slowest pipeline's runtime.

**Output:** a short written assessment ranking the top pain points by impact, shared with the VP of Engineering.

## Days 31–60: Build the foundation
1. Extract the most-duplicated infrastructure into shared, versioned modules. Migrate one team first as the pilot.
2. Standard PR pipeline for all teams: lint, policy, tests, plan, AI review.
3. A `CLAUDE.md`-style standards file per repo, so AI tools and engineers follow the same rules.
4. Ephemeral preview environments per PR, so AI agents and humans can test real changes before merge.

## Days 61–90: Scale and measure
1. Migrate the other two teams onto the shared modules.
2. Turn on scheduled drift detection everywhere.
3. Default observability: every service has logs, metrics, traces and baseline alarms from the module.
4. Measure and report: lead time, change failure rate, PR review time, pipeline duration and drift issues opened/closed.

## Principles
1. Pave the road; don't build walls. Make the standard path the easiest path.
2. AI proposes, humans approve, pipelines verify.
3. Fix root causes, then automate them away.
