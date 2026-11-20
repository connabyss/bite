"""A repo with no recognizable test runner only said "set test_command in .bite.ini", which a newcomer can't
act on without knowing what Bite looked for or what the file looks like. Say both, in the console and in the
pull request comment."""

import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
RECENT = str(KIT / "recent.py")


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def repo_without_tests(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    git(root, "init", "-q")
    (root / "notes.py").write_text("TITLE = 'notes'\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", "start")
    return root


def test_the_message_names_the_runners_and_shows_the_file(tmp_path):
    root = repo_without_tests(tmp_path)
    p = subprocess.run([sys.executable, RECENT, "--free"], cwd=root, capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr

    assert p.returncode == 1, out
    assert "Bite: no test command found." in out, out
    assert "pytest, npm test, cargo test, go test, dotnet test, Maven and Gradle" in out, out
    assert "[bite]\n    test_command = python -m pytest" in out, out


def test_the_pull_request_comment_says_the_same(tmp_path):
    root = repo_without_tests(tmp_path)
    subprocess.run([sys.executable, RECENT, "--free"], cwd=root, capture_output=True, text=True, timeout=300)
    comment = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")

    assert "Bite found no test command." in comment, comment
    assert "pytest, npm test, cargo test, go test, dotnet test, Maven and Gradle" in comment, comment
    assert "[bite]\n    test_command = python -m pytest" in comment, comment
