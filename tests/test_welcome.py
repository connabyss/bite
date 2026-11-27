"""The welcome workflow comments on first issues and pull requests and thanks people on merge (2026-11-13).
It runs on pull_request_target, so it must never check out or run a pull request's code. No key, no network."""
from pathlib import Path

FLOW = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "welcome.yml").read_text(encoding="utf-8")


def test_it_never_checks_out_code_from_a_pull_request():
    assert "pull_request_target" in FLOW
    assert "actions/checkout" not in FLOW and "uses:" not in FLOW


def test_first_time_search_names_issues_and_pull_requests():
    # GitHub's search refuses a query without is:issue or is:pull-request (HTTP 422)
    assert 'author:$AUTHOR is:issue"' in FLOW and 'author:$AUTHOR is:pull-request"' in FLOW


def test_the_owner_and_bots_are_never_welcomed():
    assert "github.actor != 'connabyss'" in FLOW and '"$AUTHOR_TYPE" = "Bot"' in FLOW
