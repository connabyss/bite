"""`--last 0` can never find a commit, so it should be refused up front instead of running and reporting
"0 commits changed code in the last 0. Nothing to check. Try a larger --last." A negative bound already says
"0 or more"; for --last the useful lower bound is 1."""

import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
RECENT = str(KIT / "recent.py")


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def repo(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    git(root, "init", "-q")
    (root / "notes.py").write_text("X = 1\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "start")
    return root


def run(root, *args):
    p = subprocess.run([sys.executable, RECENT, *args], cwd=root, capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def test_last_zero_is_refused_before_the_check_runs(tmp_path):
    rc, out = run(repo(tmp_path), "--free", "--last", "0")
    assert rc == 2, out
    assert "--last needs a whole number of 1 or more, got '0'." in out, out
    assert "Nothing to check" not in out, out


def test_negative_last_also_names_the_one_commit_minimum(tmp_path):
    rc, out = run(repo(tmp_path), "--free", "--last", "-3")
    assert rc == 2, out
    assert "--last needs a whole number of 1 or more, got '-3'." in out, out


def test_jobs_zero_is_refused_before_the_check_runs(tmp_path):
    rc, out = run(repo(tmp_path), "--free", "--jobs", "0")
    assert rc == 2, out
    assert "--jobs needs a whole number of 1 or more, got '0'." in out, out
    assert "at a time (--jobs)" not in out, out


def test_negative_jobs_also_names_the_one_job_minimum(tmp_path):
    rc, out = run(repo(tmp_path), "--free", "--jobs", "-2")
    assert rc == 2, out
    assert "--jobs needs a whole number of 1 or more, got '-2'." in out, out

