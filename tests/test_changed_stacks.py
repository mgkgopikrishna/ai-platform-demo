from pathlib import Path

from changed_stacks import affected_teams, all_teams

TEAMS = ["team-a", "team-b", "team-c"]


def test_single_team_change_plans_only_that_team():
    assert affected_teams(["teams/team-b/main.tf"], TEAMS) == ["team-b"]


def test_module_change_plans_every_team():
    assert affected_teams(["modules/ecs-service/main.tf"], TEAMS) == TEAMS


def test_shared_ci_change_plans_every_team():
    assert affected_teams([".github/workflows/pr-checks.yml"], TEAMS) == TEAMS


def test_docs_only_change_plans_nothing():
    assert affected_teams(["README.md", "docs/demo-script.md"], TEAMS) == []


def test_multiple_teams_are_deduplicated_and_sorted():
    files = ["teams/team-c/main.tf", "teams/team-a/variables.tf", "teams/team-c/outputs.tf"]
    assert affected_teams(files, TEAMS) == ["team-a", "team-c"]


def test_unknown_team_directory_is_ignored():
    assert affected_teams(["teams/team-z/main.tf"], TEAMS) == []


def test_blank_lines_are_ignored():
    assert affected_teams(["", "  ", "teams/team-a/main.tf"], TEAMS) == ["team-a"]


def test_repo_discovers_three_teams():
    root = Path(__file__).resolve().parent.parent
    assert all_teams(root) == TEAMS
