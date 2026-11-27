"""Dependabot's grouped minor and patch updates get auto-merge switched on; major updates never do (2026-11-27).
Bite #270 sat open and green because the repo allowed auto-merge but nothing turned it on. No key, no network."""
import re
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
FLOW = (KIT / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
DEPENDABOT = (KIT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
PATTERN = re.search(r'\[\[ "\$BRANCH" =~ (\S+) \]\]', FLOW).group(1)


def auto_merges(branch):
    return re.fullmatch(PATTERN.lstrip("^").rstrip("$"), branch) is not None


def test_it_switches_on_auto_merge_and_never_merges_or_runs_code_itself():
    assert "gh pr merge --auto --squash" in FLOW
    assert "uses:" not in FLOW
    assert "dependabot[bot]" in FLOW


def test_minor_and_patch_groups_are_auto_merged():
    assert auto_merges("dependabot/github_actions/actions-c2ef8f4caa")  # the branch of #270
    assert auto_merges("dependabot/pip/python-0a1b2c3d4e")


def test_major_groups_and_single_updates_wait_for_a_person():
    assert not auto_merges("dependabot/github_actions/actions-major-c2ef8f4caa")
    assert not auto_merges("dependabot/pip/python-major-0a1b2c3d4e")
    assert not auto_merges("dependabot/pip/requests-3.0.0")  # e.g. an ungrouped security update


def test_the_group_names_match_dependabot_yml():
    for group in ("actions:", "python:", "actions-major:", "python-major:"):
        assert f"\n      {group}" in DEPENDABOT
