# Platform Standards (read by humans and AI tools)

This file is the single source of truth for how infrastructure is written here.
AI coding tools (Claude Code, Cursor, Codex) and the AI PR reviewer read it, so
the rules engineers follow and the rules AI follows are the same rules.

## Repo layout
- `modules/` holds shared, reusable building blocks. Platform-owned.
- `teams/<team>/` holds thin stacks. A team stack should only call modules and
  set inputs. If you are writing raw `resource` blocks in a team stack, stop:
  the logic probably belongs in a module.
- `scripts/` holds platform tooling in Python, with tests in `tests/`.
- `agents/` holds read-only AI agents. New agent tools must be read-only, allowlisted,
  and covered by an offline test using the scripted model in `tests/conftest.py`.

## Terraform rules
1. Every variable and output has a `description`. Constrain inputs with `validation` where a bad value is possible.
2. Never use `:latest` image tags. Deploys must be reproducible and rollback-able.
3. Default to least privilege. The app task role starts empty; teams attach only what they need.
4. Security groups reference other security groups instead of CIDRs wherever possible.
5. Every service gets logs, health checks, autoscaling and default alarms from the module. Do not opt out.
6. Prod gets `deletion_protection` and one NAT gateway per AZ. Non-prod shares one NAT to save cost.
7. A Checkov skip is allowed only inline, with a one-line reason a reviewer can challenge.
8. No hand-made changes in the AWS console. If drift detection opens an issue, codify or revert.

## Making changes
- Change a module: bump behaviour carefully. CI plans **every** team stack, so read all three plans.
- Destroy or replace in a plan: call it out in the PR description and say why it is safe.
- Run locally before pushing: `terraform fmt -recursive`, `tflint --recursive`, `checkov -d .`, `pytest tests/`.

## For AI tools specifically
- Propose changes; do not apply them. `terraform apply` is never run by an AI tool.
- Prefer editing an existing module over creating a new one.
- When unsure about intent, ask in the PR comment rather than guessing.
- Keep review comments specific: file, line, risk, suggested fix.
