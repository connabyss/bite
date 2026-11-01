"""The comeback alarm (issue #88): a later commit that quietly puts the old code back is named."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ask  # noqa: E402
import recent  # noqa: E402

RECENT = str(Path(recent.__file__))
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def project(steps: list) -> Path:
    """A git repo with one commit per (subject, {file: text or None to delete}). Returns its folder."""
    root = Path(tempfile.mkdtemp(prefix="bite_back_test_"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for subject, files in steps:
        for name, text in files.items():
            if text is None:
                (root / name).unlink()
            else:
                (root / name).write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", subject], cwd=root, check=True)
    return root


def sha_of(root: Path, subject: str) -> str:
    return subprocess.run(["git", "log", "--format=%H", f"--grep=^{subject}$"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.split()[0]


OLD = "def total(prices):\n    return sum(prices)\n"
FIXED = "def total(prices):\n    return round(sum(prices), 2)\n"
OTHER = "\n\ndef tax(price):\n    return price * 0.2\n"


def check(root: Path, subject: str = "Fix totals") -> tuple:
    c = {"sha": sha_of(root, subject), "code": ["shop.py"]}
    return recent.came_back(root, c), c


def test_a_quiet_undo_is_named():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}),
                    ("Add tax", {"shop.py": FIXED + OTHER}), ("Simplify total()", {"shop.py": OLD + OTHER}),
                    ("Docs", {"README.md": "hi\n"})])
    back, c = check(root)
    assert back == "undone since"
    assert c["undone_by"] == {"sha": sha_of(root, "Simplify total()"), "subject": "Simplify total()"}
    kind, label, text = recent.say({**c, "subject": "Fix totals", "undo": back})
    assert kind == "back" and "UNDONE" in label and "Simplify total()" in text and c["undone_by"]["sha"][:8] in text


def test_an_open_revert_is_only_noted():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}),
                    ('Revert "Fix totals"', {"shop.py": OLD})])
    back, c = check(root)
    assert back == "reverted since" and c["undone_by"]["subject"] == 'Revert "Fix totals"'
    kind, label, _ = recent.say({**c, "subject": "Fix totals", "undo": back})
    assert kind == "skip" and "on purpose" in label


def test_no_alarm_while_the_fix_is_still_there():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}), ("Add tax", {"shop.py": FIXED + OTHER})])
    assert check(root)[0] == ""


def test_no_alarm_when_the_code_moved_on():
    # Rewritten, not put back: neither the fix nor its undo applies to today's code.
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}),
                    ("Rewrite total()", {"shop.py": "def total(prices):\n    return float(f'{sum(prices):.2f}')\n" + OTHER})])
    assert check(root)[0] == ""


def test_no_alarm_when_an_added_line_was_reworded():
    # The fix only added a line. A later commit reworded it: that's not the old code coming back.
    guard = "def total(prices):\n    if not prices:\n        return 0\n    return sum(prices)\n"
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": guard}),
                    ("Tidy the guard", {"shop.py": guard.replace("if not prices:", "if len(prices) == 0:") + OTHER})])
    assert check(root)[0] == ""


def test_no_alarm_when_the_file_moved_away():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}),
                    ("Move the shop", {"shop.py": None, "store.py": FIXED})])
    assert check(root)[0] == ""


def test_no_alarm_when_the_fix_came_back_again():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}), ("Simplify", {"shop.py": OLD}),
                    ("Put the rounding back", {"shop.py": FIXED})])
    assert check(root)[0] == ""


def test_the_newest_commit_is_never_undone():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED})])
    assert check(root)[0] == ""


def test_every_output_says_it():
    c = {"sha": "a" * 40, "subject": "Fix totals", "undo": "undone since",
         "undone_by": {"sha": "b" * 40, "subject": "Simplify total()"}}
    r = recent.results([c, {"sha": "c" * 40, "subject": "Fix x", "undo": "guarded", "caught": "`test_x`"}])
    assert r["outcome"] == "undone_later" and r["commits"][0]["result"] == "undone_later"
    assert r["commits"][0]["undone_by"] == c["undone_by"]
    assert not recent.bite_proof(["back", "held"])
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        text = recent.write_comment(root, [c]).read_text(encoding="utf-8")
        assert "came undone" in text.splitlines()[1] and "Simplify total()" in text
        page = recent.write_html(root, [c], [], 1).read_text(encoding="utf-8")
        assert "undone by a later commit" in page and "Bite-proof" not in page
    kind, label, sentence = ask.verdict({**c, "time": 1767268800})
    assert kind == "gap" and label == "🔁 UNDONE BY A LATER COMMIT" and "Simplify total()" in sentence
    assert "UNDONE BY A LATER COMMIT" in ask.answer([{**c, "time": 1767268800}], emoji=False)
    kind, label, sentence = ask.verdict({**c, "undo": "reverted since", "time": 1767268800})
    assert kind == "cant" and "on purpose" in sentence


def test_the_comeback_demo_names_the_culprit():
    p = subprocess.run([sys.executable, RECENT, "--demo", "comeback", "--json"], capture_output=True, text=True,
                       encoding="utf-8", cwd=tempfile.mkdtemp(), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    back = [x for x in r["commits"] if x["result"] == "undone_later"]
    assert r["outcome"] == "undone_later" and len(back) == 1
    assert back[0]["subject"].startswith("Fix totals") and back[0]["undone_by"]["subject"] == "Simplify total()"
    assert "UNDONE BY A LATER COMMIT" in p.stderr


def test_the_culprit_is_the_last_undo_not_an_earlier_one():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}), ("Simplify", {"shop.py": OLD}),
                    ("Put the rounding back", {"shop.py": FIXED}), ("Simplify again", {"shop.py": OLD + OTHER})])
    back, c = check(root)
    assert back == "undone since" and c["undone_by"]["subject"] == "Simplify again"


def test_the_culprit_is_not_a_reformat_of_the_fix():
    # A reformat changed the fix's line first (so a plain line search would blame it); a later commit undid the fix.
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}),
                    ("Format", {"shop.py": FIXED.replace("round(sum(prices), 2)", "round(sum(prices), ndigits=2)")}),
                    ("Speed up total()", {"shop.py": OLD + OTHER})])
    back, c = check(root)
    assert back == "undone since" and c["undone_by"]["subject"] == "Speed up total()"


def test_reverting_in_the_middle_of_a_title_is_on_purpose_too():
    root = project([("Start", {"shop.py": OLD}), ("Fix totals", {"shop.py": FIXED}),
                    ("fix #12 by reverting the rounding", {"shop.py": OLD})])
    assert check(root)[0] == "reverted since"
