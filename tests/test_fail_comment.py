"""The "your tests already fail" comment: plain words on where and what failed, and the right newest commit.
Tiny repos made on the spot; no key, no network."""

import json
import subprocess

from test_tricks import KIT, PY, ROUNDED, commit, make, write

BROKEN = "from shop import total\n\n\ndef test_total():\n    assert total([1]) == 2\n"
FIXED = "from shop import total\n\n\ndef test_total():\n    assert total([1]) == 1\n"


def run(root, last):
    subprocess.run([PY, str(KIT / "recent.py"), "--free", "--last", str(last)], cwd=root,
                   capture_output=True, text=True, timeout=600)
    note = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")
    rows = json.loads((root / "bite_proof" / "results.json").read_text(encoding="utf-8"))["commits"]
    return note, rows


def sha(root, rev="HEAD"):
    return subprocess.run(["git", "rev-parse", rev], cwd=root, capture_output=True, text=True).stdout.strip()


def test_failing_newest_commit_says_where_and_what_failed(tmp_path):
    root = make(tmp_path, {"tests/test_total.py": BROKEN})
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    note, rows = run(root, 1)
    assert "❌ Bite: your tests fail" in note
    assert f"commit `{sha(root)[:8]}`, the newest commit in this pull request" in note
    assert "**What failed:**" in note and "assert 1 == 2" in note
    assert "isn't a verdict on them" in note and note.count("**Next:**") == 1
    assert rows[0]["result"] == "tests_fail"


def test_a_later_commit_that_changed_no_code_is_named_as_the_newest(tmp_path):
    root = make(tmp_path, {"tests/test_total.py": BROKEN})
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    code = sha(root)
    write(root, {"README.md": "notes\n"})
    commit(root, "Add notes")
    note, _ = run(root, 2)
    assert "❌ Bite: your tests fail" in note
    assert f"`{code[:8]}`, the newest commit that changed code" in note
    assert f"the tests fail on the newest one too (`{sha(root)[:8]}`)" in note
    assert "the newest commit in this pull request" not in note


def test_tests_fixed_by_a_later_commit_dont_turn_the_comment_red(tmp_path):
    root = make(tmp_path, {"tests/test_total.py": BROKEN})
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    write(root, {"tests/test_total.py": FIXED})
    commit(root, "Fix the total test")
    note, rows = run(root, 2)
    assert "❌" not in note, note
    assert "pass on the newest one" in note
    assert rows[0]["result"] == "skipped"
