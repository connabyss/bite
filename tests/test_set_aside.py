"""spantruth's `version("spantruth") == __version__` test read the installed (newer) version, so it failed on every
older commit's copy and Bite skipped all of them as "tests fail at this commit". A test that fails with nothing taken
out can't notice anything either way, so now Bite sets a few such tests aside and checks with the rest, and says so.
No key, no network."""

import json
import os
import subprocess
import sys
from pathlib import Path

RECENT = str(Path(__file__).resolve().parent.parent / "recent.py")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def run_bite(tmp_path, steps):
    installed = tmp_path / "installed_version"  # stands in for the installed package's metadata: today's version
    installed.write_text("2")
    root = tmp_path / "shop"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for msg, files in steps(installed):
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", msg], cwd=root, check=True)
    (root / ".bite.ini").write_text(f'[bite]\ntest_command = "{sys.executable}" -m pytest -q -p no:cacheprovider\n')
    p = subprocess.run([sys.executable, RECENT, "--free", "--json"], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return {c["subject"]: c for c in json.loads(p.stdout)["commits"]}, p.stderr


def version_test(installed):
    return f"import shop\n\n\ndef test_version():\n    assert open({str(installed)!r}).read() == shop.__version__\n"


def test_a_test_failing_at_an_old_commit_is_set_aside(tmp_path):
    total = "from shop import total\n\n\ndef test_total():\n    assert total([0.1, 0.2]) == 0.3\n"
    steps = lambda inst: [  # noqa: E731
        ("Start", {"shop.py": "__version__ = '1'\n\n\ndef total(xs):\n    return sum(xs)\n",
                   "test_version.py": version_test(inst)}),
        ("Fix total rounding", {"shop.py": "__version__ = '1'\n\n\ndef total(xs):\n    return round(sum(xs), 2)\n",
                                "test_total.py": total}),
        ("Release 2", {"shop.py": "__version__ = '2'\n\n\ndef total(xs):\n    return round(sum(xs), 2)\n"})]
    commits, err = run_bite(tmp_path, steps)
    c = commits["Fix total rounding"]
    assert c["result"] == "noticed", (c, err)
    assert c["set_aside"] == "test_version", c


def test_the_commits_own_failing_test_is_not_set_aside(tmp_path):
    """Setting aside the commit's own test would hide the very thing Bite checks: that commit stays unchecked."""
    steps = lambda inst: [  # noqa: E731
        ("Start", {"shop.py": "__version__ = '1'\n\n\ndef total(xs):\n    return sum(xs)\n",
                   "test_total.py": "from shop import total\n\n\ndef test_total():\n    assert total([1]) == 1\n"}),
        ("Add the version check", {"shop.py": "__version__ = '1'\n\n\ndef total(xs):\n    return sum(xs) + 0\n",
                                   "test_version.py": version_test(inst)}),
        ("Release 2", {"shop.py": "__version__ = '2'\n\n\ndef total(xs):\n    return sum(xs) + 0\n"})]
    commits, err = run_bite(tmp_path, steps)
    c = commits["Add the version check"]
    assert c["result"] != "noticed" and "set_aside" not in c, (c, err)
