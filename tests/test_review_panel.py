from pathlib import Path

from conftest import ScriptedLLM, final_turn, tool_turn

from agents.review_panel import SPECIALISTS, merge, parse_findings, run_panel, to_markdown, verdict

ROOT = Path(__file__).resolve().parent.parent
DIFF = (ROOT / "examples/fixtures/risky_pr.diff").read_text()

SSH = '{"severity": "%s", "file": "modules/ecs-service/main.tf", "issue": "%s", "fix": "Remove the rule."}'


def scripted(outputs):
    """Each specialist reads the diff, then replies with its canned JSON."""
    def factory(name):
        return ScriptedLLM([tool_turn(("get_diff", {})), final_turn(outputs[name])])
    return factory


def test_parse_findings_handles_prose_and_bad_values():
    text = 'Here you go:\n[{"severity": "critical", "file": "a.tf", "issue": "x", "fix": "y"}, {"nope": 1}]'
    assert parse_findings(text) == [{"severity": "LOW", "file": "a.tf", "resource": "", "issue": "x", "fix": "y"}]
    assert parse_findings("I found nothing") is None


def test_merge_groups_similar_findings_and_counts_consensus():
    merged = merge({
        "security": [{"severity": "HIGH", "file": "m.tf", "issue": "SSH port 22 open to 0.0.0.0/0", "fix": ""}],
        "reliability": [{"severity": "MEDIUM", "file": "m.tf", "issue": "SSH port 22 is open to 0.0.0.0/0", "fix": ""}],
        "cost": [{"severity": "LOW", "file": "t.tf", "issue": "NAT per AZ in dev", "fix": ""}],
    })
    assert len(merged) == 2
    top = merged[0]
    assert top.severity == "HIGH" and sorted(top.reviewers) == ["reliability", "security"]


def test_deterministic_risk_is_a_floor():
    assert verdict([], "HIGH") == "HIGH"
    assert verdict(merge({"cost": [{"severity": "LOW", "file": "a", "issue": "x", "fix": ""}]}), "MEDIUM") == "MEDIUM"


def test_full_panel_runs_all_specialists_in_parallel_and_merges():
    outputs = {
        "security": "[" + SSH % ("HIGH", "SSH port 22 open to the internet on service tasks") + "]",
        "reliability": "[" + SSH % ("MEDIUM", "SSH port 22 open to the internet on the service tasks") + ","
                       '{"severity": "HIGH", "file": "modules/ecs-service/main.tf", '
                       '"issue": "Circuit breaker removed and min healthy 0% allows full outage on deploy", "fix": "Restore."}]',
        "cost": '[{"severity": "MEDIUM", "file": "teams/team-c/main.tf", "issue": "NAT per AZ forced in all envs", "fix": "Revert."}]',
        "platform": "not json at all",
    }
    panel = run_panel(scripted(outputs), DIFF, "standards", plan_summary={"risk": "LOW"})
    assert set(panel["runs"]) == set(SPECIALISTS)
    assert panel["failed_reviewers"] == ["platform"]
    assert panel["verdict"] == "HIGH"
    ssh = next(f for f in panel["findings"] if "SSH" in f.issue)
    assert len(ssh.reviewers) == 2
    md = to_markdown(panel)
    assert "2/4" in md and "Unparseable output from: platform" in md


def test_live_run_regression_merges_by_resource_not_wording():
    """From the first live run: reviewers described the same problems in very different
    words, so text similarity alone left them as separate 1/4 rows."""
    m = "modules/ecs-service/main.tf"
    t = "teams/team-c/main.tf"
    merged = merge({
        "security": [
            {"severity": "HIGH", "file": m, "resource": "aws_vpc_security_group_ingress_rule.service_ssh",
             "issue": "The new rule opens TCP 22 to 0.0.0.0/0 on the service security group.", "fix": ""},
            {"severity": "LOW", "file": t, "resource": "aws_s3_bucket.thumbnails",
             "issue": "Bucket lacks a public access block and encryption.", "fix": ""}],
        "reliability": [
            {"severity": "HIGH", "file": m, "resource": "aws_ecs_service.this",
             "issue": "Min healthy 0% means every deploy causes full downtime.", "fix": ""},
            {"severity": "HIGH", "file": m, "resource": "aws_ecs_service.this",
             "issue": "Circuit breaker removed, so bad releases no longer roll back.", "fix": ""}],
        "cost": [
            {"severity": "MEDIUM", "file": t, "resource": "module.network",
             "issue": "single_nat_gateway hard-coded false multiplies NAT spend in non-prod.", "fix": ""}],
        "platform": [
            {"severity": "HIGH", "file": m, "resource": "module.api.aws_vpc_security_group_ingress_rule.service_ssh",
             "issue": "Port 22 to the world violates the reference-security-groups standard.", "fix": ""},
            {"severity": "HIGH", "file": m, "resource": "aws_ecs_service.this",
             "issue": "Deployment safety defaults removed for all teams.", "fix": ""},
            {"severity": "MEDIUM", "file": t, "resource": "module.network",
             "issue": "NAT conditional replaced by a constant, violating rule 6.", "fix": ""},
            {"severity": "MEDIUM", "file": t, "resource": "aws_s3_bucket.thumbnails",
             "issue": "Raw resource in a team stack instead of a module.", "fix": ""}],
    })
    ssh = next(f for f in merged if f.resource.endswith("service_ssh"))
    assert sorted(ssh.reviewers) == ["platform", "security"]
    nat = next(f for f in merged if f.resource == "module.network")
    assert sorted(nat.reviewers) == ["cost", "platform"]
    s3 = next(f for f in merged if f.resource.endswith("thumbnails"))
    assert sorted(s3.reviewers) == ["platform", "security"] and s3.severity == "MEDIUM"
    ecs = [f for f in merged if f.resource == "aws_ecs_service.this"]
    assert len(ecs) == 2  # reliability's two distinct problems stay distinct
    assert sum(len(f.reviewers) for f in ecs) == 3  # platform joined one of them
    assert len(merged) == 5
