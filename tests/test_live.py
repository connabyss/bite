"""bite live: the check a coding AI gets the moment it says "fixed" (Claude Code's Stop hook and /bite).
No key, no network: a tiny repo, and the hook's JSON written by hand the way Claude Code sends it."""

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import live  # noqa: E402

PY = sys.executable
CODE = "def total(prices, discount=0):\n    return sum(prices) - discount\n"
FIXED = "def total(prices, discount=0):\n    return sum(prices) * (1 - discount / 100)\n"
TEST = "from cart import total\n\n\ndef test_plain():\n    assert total([10, 20]) == 30\n"
# 100 - 10 and 100 * 0.9 are both 90: this test passes with or without the fix (Claude wrote it in a real trial).
WEAK = TEST + "\n\ndef test_discount():\n    assert total([50, 50], 10) == 90\n"
GOOD = TEST + "\n\ndef test_discount():\n    assert total([200], 10) == 180\n"


def git(root, *a, **kw):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, **kw)


def make(tmp_path):
    root = tmp_path / "shop"
    root.mkdir()
    git(root, "init", "-q")
    (root / "cart.py").write_text(CODE)
    (root / "test_cart.py").write_text(TEST)
    (root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
    return root


def stop(root, again=False, session="s1", transcript=""):
    return live.hook({"session_id": session, "cwd": str(root), "stop_hook_active": again,
                      "transcript_path": transcript})


def test_no_test_noticed_sends_back_once_then_warns(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    first = stop(root)
    assert first.get("decision") == "block" and "cart.py" in first["reason"] and "fails without your change" in first["reason"]
    second = stop(root, again=True)  # Claude stopped again without adding a test
    assert "decision" not in second and "no test noticed" in second["systemMessage"]
    assert stop(root, again=True) == {}  # warned once is enough: no repeat for the same change
    assert stop(root, session="s2").get("decision") == "block"  # a new session gets its one send-back too


def test_a_new_test_that_passes_without_the_fix_is_caught(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    (root / "test_cart.py").write_text(WEAK)
    r = live.check(root)
    assert r["status"] == "tests_blind" and r["test_code"] == ["test_cart.py"]
    assert "don't notice" in live.say(r)
    assert "Those tests pass without your change" in stop(root)["reason"]


def test_a_test_that_notices_gets_a_tick(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    (root / "test_cart.py").write_text(GOOD)
    out = stop(root)
    assert "decision" not in out and "✅" in out["systemMessage"] and "test_discount" in out["systemMessage"]


def test_a_change_committed_during_the_turn_is_still_checked(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "Fix discount",
        env={**__import__("os").environ, "GIT_COMMITTER_DATE": "2030-01-01T12:00:00Z"})
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "user", "timestamp": "2030-01-01T11:59:00Z",
                              "message": {"role": "user", "content": "fix the discount"}}) + "\n"
                  + json.dumps({"type": "user", "timestamp": "2030-01-01T12:00:30Z",  # a tool result: not the person
                                "message": {"content": [{"type": "tool_result", "content": "ok"}]}}) + "\n")
    out = stop(root, transcript=str(tr))
    assert out.get("decision") == "block" and "cart.py" in out["reason"]


def test_nothing_changed_stays_quiet(tmp_path):
    root = make(tmp_path)
    (root / "notes.md").write_text("not code\n")
    assert stop(root) == {}
    assert live.check(root)["status"] == "nothing"


def test_tests_already_failing_are_named_not_called_a_pass(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text("def total(prices, discount=0):\n    return 0\n")
    r = live.check(root)
    assert r["status"] == "cant" and "fail with the change in" in r["why"]


def test_the_hook_never_breaks_the_session(tmp_path, capsys):
    with patch("sys.stdin", io.StringIO("not json")):
        assert live.main(["--hook"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["systemMessage"].startswith("Bite's live check stopped")


def test_bite_live_prints_the_result_for_slash_bite(tmp_path, monkeypatch, capsys):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    monkeypatch.chdir(root)
    import recent
    assert recent.main(["live"]) == 1
    assert "no test noticed the change to cart.py" in capsys.readouterr().out


def test_a_repository_with_no_commits_says_so_instead_of_naming_head(tmp_path, monkeypatch, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    git(root, "init", "-q")
    (root / "cart.py").write_text(CODE)
    monkeypatch.chdir(root)
    import recent
    assert recent.main(["live"]) == 0
    out = capsys.readouterr().out
    assert "this repository has no commits yet" in out
    assert "Make a first commit, then run bite live again." in out
    assert "--since HEAD" not in out


def test_a_missing_since_ref_still_names_the_ref(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(make(tmp_path))
    import recent
    assert recent.main(["live", "--since", "nosuchbranch"]) == 1
    assert "--since nosuchbranch isn't a commit or branch in this repository." in capsys.readouterr().out


def test_the_plugin_runs_these_commands():
    hooks = json.loads((KIT / "plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["Stop"][0]["hooks"][0]["command"] == "bite live --hook"
    assert "!`bite live" in (KIT / "plugin" / "commands" / "bite.md").read_text(encoding="utf-8")
    market = json.loads((KIT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert (KIT / market["plugins"][0]["source"] / ".claude-plugin" / "plugin.json").is_file()


def test_unknown_live_option_errors_and_points_to_help(capsys):
    assert live.main(["--bogus"]) == 2
    out = capsys.readouterr().out
    assert out == "Bite: unknown option '--bogus'. Run bite live --help for the options\n."
    

def test_unknown_option_after_a_valid_option_also_errors(capsys):
    assert live.main(["--since", "HEAD", "--bogus"]) == 2
    assert capsys.readouterr().out == "Bite: unknown option '--bogus'. Run bite live --help for the options\n."

def test_typo_of_since_option_errors_with_exit_code_2(capsys):
    # The issue's example: --sinse is a typo, not an option.
    assert live.main(["--sinse", "main"]) == 2
    assert capsys.readouterr().out == "Bite: unknown option '--sinse'. Run bite live --help for the options.\n"


def test_since_with_nothing_after_it_errors_with_exit_code_2(capsys):
    assert live.main(["--since"]) == 2
    assert capsys.readouterr().out == "Bite: --since needs a commit or branch after it, like bite live --since main.\n"
