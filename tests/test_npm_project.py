"""A whole free check on a tiny npm project, start to finish. No network, nothing to install.

Every other end-to-end test here uses a Python project with pytest. This one builds a JavaScript project that runs
its tests with Node's built-in runner (`node --test`) and has two "fix" commits: one that a test guards, and one
that no test guards. Bite has to tell them apart."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RECENT = str(Path(__file__).resolve().parent.parent / "recent.py")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

PACKAGE = '{\n  "name": "shop",\n  "version": "1.0.0",\n  "scripts": {"test": "node --test"}\n}\n'
START = {
    "package.json": PACKAGE,
    "shop.js": "exports.total = (xs) => xs.reduce((a, b) => a + b, 0);\n"
               "exports.label = (name) => name;\n",
    "test/shop.test.js": "const test = require('node:test');\nconst assert = require('node:assert');\n"
                         "const { total } = require('../shop');\n\n"
                         "test('total of one', () => assert.strictEqual(total([1]), 1));\n",
}
# Fix 1 rounds the total and brings the test that guards it.
GUARDED = {
    "shop.js": "exports.total = (xs) => Math.round(xs.reduce((a, b) => a + b, 0) * 100) / 100;\n"
               "exports.label = (name) => name;\n",
    "test/rounding.test.js": "const test = require('node:test');\nconst assert = require('node:assert');\n"
                             "const { total } = require('../shop');\n\n"
                             "test('total rounds to cents', () => assert.strictEqual(total([0.1, 0.2]), 0.3));\n",
}
# Fix 2 trims the label, and nothing tests labels, so taking it out changes no test result.
UNGUARDED = {
    "shop.js": GUARDED["shop.js"].replace("(name) => name;", "(name) => name.trim();"),
}


def make_project(root):
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for message, files in (("Start", START), ("Fix total rounding", GUARDED), ("Fix label whitespace", UNGUARDED)):
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", message], cwd=root, check=True)
    return root


@pytest.mark.skipif(shutil.which("npm") is None, reason="needs Node.js")
def test_bite_tells_a_guarded_npm_fix_from_an_unguarded_one(tmp_path):
    root = make_project(tmp_path / "shop")
    p = subprocess.run([sys.executable, RECENT, "--free", "--json"], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    result = {c["subject"]: c["result"] for c in json.loads(p.stdout)["commits"]}
    assert result == {"Fix total rounding": "noticed", "Fix label whitespace": "no_test_noticed"}, (result, p.stderr)
