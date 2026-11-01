"""bite --json: the results for other programs, under names that stay the same between releases."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402

RECENT = str(Path(recent.__file__))


def c(undo, **kw):
    return {"sha": "a" * 40, "subject": "Fix x", "undo": undo, **kw}


def test_each_result_has_its_stable_name():
    r = recent.results([c("guarded", caught="`test_x`"), c("unguarded"), c("TEST GUARDS NOTHING", test_code=["t.py"]),
                        c("not flagged: a tidy-up commit"), {"sha": "b" * 40, "subject": "never checked"}])
    assert [x["result"] for x in r["commits"]] == ["noticed", "no_test_noticed", "its_tests_didnt_notice", "skipped"]
    assert r["commits"][1]["label"] == "NO TEST NOTICED" and "**" not in r["commits"][1]["detail"]
    assert r["outcome"] == "gaps" and r["schema"] == 1


def test_outcomes():
    assert recent.results([c("guarded")])["outcome"] == "noticed"
    assert recent.results([], error="no tests")["outcome"] == "error"
    assert recent.results([], none="nothing claims a fix") == {**recent.results([]), "message": "nothing claims a fix"}
    assert recent.results([])["outcome"] == "nothing_checked"
    false = {"sha": "c" * 40, "subject": "Fix y", "status": "FALSE DONE", "bug": "still wrong", "today": "STILL BROKEN"}
    assert recent.results([], tried=[false, {"sha": "d" * 40, "status": "held"}])["false_done"] == [
        {"sha": "c" * 40, "subject": "Fix y", "bug": "still wrong", "today": "STILL BROKEN"}]


def test_json_puts_only_the_results_on_stdout():
    p = subprocess.run([sys.executable, RECENT, "--demo", "--json"], capture_output=True, text=True, encoding="utf-8",
                       cwd=tempfile.mkdtemp())
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert r["outcome"] == "gaps" and {"noticed", "no_test_noticed"} <= {x["result"] for x in r["commits"]}
    assert "One-page report" in p.stderr


def test_json_outside_a_repo_still_prints_json():
    p = subprocess.run([sys.executable, RECENT, "--json", "--free"], capture_output=True, text=True, encoding="utf-8",
                       cwd=tempfile.mkdtemp())
    assert p.returncode == 1 and json.loads(p.stdout)["outcome"] == "error"
    assert "not inside a git repository" in p.stderr
