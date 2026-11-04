"""On a repo with fewer commits than --last, Bite used to say "in the last 999" as if it had looked at 999
(#161): with 2 commits, `bite --free --last 999` printed "1 commits changed code in the last 999." It now says
how many there really were: "1 commits changed code in all 2 commits." No key, no network."""

import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PY = sys.executable


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def shop(tmp_path):
    """A tiny repo with 2 commits: one README-only, one code change. Shorter than any --last."""
    root = tmp_path / "shop"
    root.mkdir()
    git(root, "init", "-q")
    (root / "README.md").write_text("# shop\n")
    commit(root, "start")
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "test_shop.py").write_text("import unittest\nfrom shop import total\n\n\nclass T(unittest.TestCase):\n"
                                       "    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n")
    (root / ".bite.ini").write_text(f'[bite]\ntest_command = "{PY}" -m unittest\n')
    commit(root, "Fix total rounding")
    return root


def test_last_larger_than_history_says_all_of_it(tmp_path):
    root = shop(tmp_path)
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--last", "999"], cwd=root,
                         capture_output=True, text=True, timeout=300, check=False)
    assert "in the last 999" not in out.stdout, out.stdout
    assert "1 commits changed code in all 2 commits" in out.stdout, out.stdout
