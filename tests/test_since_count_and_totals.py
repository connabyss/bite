"""Two lines people see on every run. A branch check (`--since main`, what the GitHub Action runs) used to say
"1 commit changed code in the last 40." about a branch that added 1 commit; it now says "since main". And the
totals line used to list zero counts ("no test noticed 0, ..., 0 couldn't be checked or skipped"); it now lists
only the counts that aren't zero. No key, no network."""

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


def branch(tmp_path):
    """3 commits on main, then a branch that adds 1 guarded fix."""
    root = tmp_path / "shop"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / ".bite.ini").write_text(f'[bite]\ntest_command = "{PY}" -m unittest\n')
    (root / "test_shop.py").write_text("import unittest\nfrom shop import total\n\n\nclass T(unittest.TestCase):\n"
                                       "    def test_total(self):\n        self.assertEqual(total([0.1, 0.2]), 0.3)\n")
    for n in range(3):
        (root / "notes.md").write_text(f"note {n}\n")
        (root / "shop.py").write_text(f"def total(xs):\n    return round(sum(xs), 2)  # v{n}\n")
        commit(root, f"start {n}")
    git(root, "checkout", "-q", "-b", "feat")
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n\n\ndef unused():\n    return 1\n")
    commit(root, "Fix total rounding")
    return root


def run(root, *args):
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free", *args], cwd=root,
                         capture_output=True, text=True, timeout=300, check=False)
    return out.stdout


def test_since_says_since_not_the_last_40(tmp_path):
    out = run(branch(tmp_path), "--since", "main")
    assert "in the last 40" not in out, out
    assert "Bite: 1 commit changed code since main." in out, out


def test_totals_line_leaves_out_zero_counts(tmp_path):
    out = run(branch(tmp_path), "--since", "main")
    line = next(l for l in out.splitlines() if l.startswith("Checked "))
    assert line == "Checked 1 commit: no test noticed 1.", out
