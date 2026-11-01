"""A submodule whose folder is named like a code file (vendor/chart.js), found by the overnight stress test
(2026-11-01): a commit that bumped it showed as "couldn't check: Bite hit a file error (Is a directory)", and
bite live stopped with a traceback. Each test here failed before its fix. No key, no network."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parent.parent
PY = sys.executable
SHOP = "exports.total = (xs) => xs.reduce((a, b) => a + b, 0);\n"
FIXED = "exports.total = (xs) => Math.round(xs.reduce((a, b) => a + b, 0) * 100) / 100;\n"
TEST = ("const test = require('node:test');\nconst assert = require('node:assert');\nconst { total } = require('../shop.js');\n"
        "test('total', () => assert.strictEqual(total([1, 2]), 3));\n")
ROUNDS = "test('total rounds', () => assert.strictEqual(total([0.1, 0.2]), 0.3));\n"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always"]


def git(root, *a):
    return subprocess.run([*GIT, *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)


def make(tmp_path):
    lib = tmp_path / "chartlib"
    lib.mkdir()
    git(lib, "init", "-q")
    (lib / "chart.js").write_text("export const v = 1;\n")
    commit(lib, "one")
    (lib / "chart.js").write_text("export const v = 2;\n")
    commit(lib, "two")
    root = tmp_path / "proj"
    (root / "test").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".bite.ini").write_text("[bite]\ntest_command = node --test\n")
    (root / "shop.js").write_text(SHOP)
    (root / "test" / "shop.test.js").write_text(TEST)
    git(root, "submodule", "add", "-q", str(lib), "vendor/chart.js")
    git(root / "vendor" / "chart.js", "checkout", "-q", "HEAD~1")
    commit(root, "start")
    return root


def test_a_commit_that_bumps_a_submodule_is_still_checked(tmp_path):
    root = make(tmp_path)
    git(root / "vendor" / "chart.js", "checkout", "-q", "-")
    (root / "shop.js").write_text(FIXED)
    with open(root / "test" / "shop.test.js", "a") as f:
        f.write(ROUNDS)
    commit(root, "Fix total rounding, bump chart.js")
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json"], cwd=root, capture_output=True, text=True,
                         timeout=300)
    c = json.loads(out.stdout)["commits"][0]
    assert c["result"] == "noticed", c


def test_live_check_with_a_moved_submodule_answers(tmp_path):
    root = make(tmp_path)
    git(root / "vendor" / "chart.js", "checkout", "-q", "-")
    (root / "shop.js").write_text(FIXED)
    out = subprocess.run([PY, str(KIT / "recent.py"), "live"], cwd=root, capture_output=True, text=True, timeout=300)
    assert "Traceback" not in out.stderr + out.stdout, out.stderr[-1500:]
    assert "no test noticed the change to shop.js" in out.stdout, out.stdout
