import json
from pathlib import Path

from agents.plan_risk import HIGH, LOW, MEDIUM, analyze_changes, overall, summarize_plan

ROOT = Path(__file__).resolve().parent.parent


def rc(address, rtype, actions, before=None, after=None):
    return {"address": address, "type": rtype, "change": {"actions": actions, "before": before, "after": after}}


def test_replacing_a_database_is_high():
    f = analyze_changes([rc("aws_db_instance.main", "aws_db_instance", ["delete", "create"])])
    assert f[0].severity == HIGH and f[0].kind == "replace"


def test_deleting_stateless_resource_is_medium():
    f = analyze_changes([rc("aws_cloudwatch_metric_alarm.a", "aws_cloudwatch_metric_alarm", ["delete"])])
    assert f[0].severity == MEDIUM


def test_new_rule_open_to_internet_is_high():
    f = analyze_changes([rc("r", "aws_vpc_security_group_ingress_rule", ["create"], after={"cidr_ipv4": "0.0.0.0/0"})])
    assert [x.kind for x in f] == ["open-ingress"]


def test_live_open_ingress_detected_in_drift_revert():
    before = {"ingress": [{"cidr_blocks": ["0.0.0.0/0"], "from_port": 22}]}
    f = analyze_changes([rc("sg", "aws_security_group", ["update"], before=before, after={"ingress": []})])
    assert f[0].kind == "live-open-ingress" and f[0].severity == HIGH


def test_iam_change_is_flagged():
    f = analyze_changes([rc("aws_iam_role.x", "aws_iam_role", ["update"])])
    assert f[0].kind == "iam"


def test_noop_is_ignored_and_empty_plan_is_low():
    assert analyze_changes([rc("x", "aws_s3_bucket", ["no-op"])]) == []
    assert overall([]) == LOW


def test_fixture_drift_plan_is_high_risk():
    s = summarize_plan(json.loads((ROOT / "examples/fixtures/drift_plan.json").read_text()))
    assert s["risk"] == HIGH
    assert "module.api.aws_security_group.service" in s["drifted_resources"]
