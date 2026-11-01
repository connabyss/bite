"""bot/pr_checklist.py, the check that reminds about unticked boxes in the pull request description, without ever failing."""

import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "bot"))
from pr_checklist import problems  # noqa: E402

TEMPLATE = (KIT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")


def test_the_template_as_opened_lists_every_box():
    assert len(problems(TEMPLATE)) == 3


def test_all_ticked_is_green():
    assert problems(TEMPLATE.replace("- [ ]", "- [x]")) == []


def test_capital_x_and_star_bullets_count():
    assert problems("* [X] one\n- [x] two") == []


def test_n_a_lets_a_box_that_doesnt_apply_pass():
    body = "- [x] test\n- [ ] screenshots: n/a\n- [ ] Assisted-by line (N/A, no AI)\n- [ ] CI green"
    assert problems(body) == ["CI green"]


def test_a_word_containing_na_is_not_n_a():
    assert problems("- [ ] final check") == ["final check"]


def test_no_boxes_at_all_is_red():
    assert len(problems("Fixed the thing.")) == 1
    assert len(problems(None)) == 1


def test_boxes_inside_html_comments_are_ignored():
    assert len(problems("<!-- - [x] example -->\nno list")) == 1


def run(tmp_path, body, user_type="User"):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": body, "user": {"type": user_type}}}), encoding="utf-8")
    return subprocess.run([sys.executable, str(KIT / "bot" / "pr_checklist.py")], capture_output=True, text=True,
                          env={"GITHUB_EVENT_PATH": str(event), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})


def test_the_step_never_fails_and_warns_about_the_unticked_box(tmp_path):
    r = run(tmp_path, "- [x] test\n- [ ] CI is green")
    assert r.returncode == 0 and "::warning::CI is green" in r.stdout and "::error::" not in r.stdout


def test_the_step_passes_with_no_checklist_at_all(tmp_path):
    r = run(tmp_path, "Fixed the thing.")
    assert r.returncode == 0 and "::warning::" in r.stdout


def test_the_step_passes_when_ticked(tmp_path):
    assert run(tmp_path, "- [x] test\n- [x] CI is green").returncode == 0


def test_bot_pull_requests_are_skipped(tmp_path):
    assert run(tmp_path, "no list", user_type="Bot").returncode == 0
