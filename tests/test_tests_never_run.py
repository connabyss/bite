"""Big Number study, 11-21: Bite said "its tests didn't notice" for commits whose new tests the project's test
command never runs, so they couldn't notice anything. weyenk/lhr's root vitest config excludes apps/lhr-office/**
(4 commits), kvakerik/steer-the-beam put scripts/test_seed_leak.py outside pytest's testpaths, and
AntonelliLab/raxmlGUI 868c7d3a added e2e/ to jest's roots in the same commit, so taking jest.config.js out with the
code hid its new tests. Now Bite keeps the runner's settings in place and names a test the command never runs.
No key, no network."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bite  # noqa: E402
import recent  # noqa: E402

RECENT = str(Path(__file__).resolve().parent.parent / "recent.py")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
VITEST_OUT = """
 ✓ tests/blog.test.ts (4 tests) 12ms
 ✓ tests/feed.test.ts (2 tests) 5ms

 Test Files  2 passed (2)
      Tests  6 passed (6)
"""


def cfg(cmd):
    return SimpleNamespace(test_cmd=cmd, box_test_cmd="", contain="", test_glob=bite.DEFAULT_TEST_FILES)


def test_the_runner_settings_stay_in_when_the_code_comes_out():
    c = cfg("npm test")
    for name in ("jest.config.js", "vitest.config.ts", "apps/web/vitest.workspace.mts", "playwright.config.ts"):
        assert bite.is_test_file(name, c), name
        assert bite.TEST_SETTINGS.search(name), name
    assert not bite.is_test_file("src/config.js", c)


def test_a_runner_settings_file_is_neither_code_to_take_out_nor_a_test_of_its_own(tmp_path):
    # raxmlGUI 868c7d3a: jest.config.js (roots += e2e/), e2e helpers and their new tests in one commit.
    root = tmp_path / "gui"
    (root / "e2e").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "package.json").write_text('{"name": "gui", "scripts": {"test": "jest"}}\n')
    (root / "jest.config.js").write_text("module.exports = { roots: ['<rootDir>/src'] };\n")
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "Start"], cwd=root, check=True)
    (root / "jest.config.js").write_text("module.exports = { roots: ['<rootDir>/src', '<rootDir>/e2e'] };\n")
    (root / "e2e" / "newick.js").write_text("exports.leaves = (t) => t.split(',').length;\n")
    (root / "e2e" / "newick.test.js").write_text(
        "const { leaves } = require('./newick');\ntest('counts leaves', () => expect(leaves('(a,b)')).toBe(2));\n")
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "Fix leaf count"], cwd=root, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    c = {"sha": sha, "subject": "Fix leaf count", "body": ""}
    recent.files_of(root, c, recent.repo.load_cfg(root))
    assert c["code"] == ["e2e/newick.js"], c["code"]
    assert c["test_code"] == ["e2e/newick.test.js"], c["test_code"]


def test_a_test_file_vitest_never_ran_is_named(tmp_path):
    f = tmp_path / "apps" / "office" / "tests"
    f.mkdir(parents=True)
    (f / "auth.test.ts").write_text("it('x', () => {})\n")
    c = {"test_code": ["apps/office/tests/auth.test.ts"]}
    assert recent.own_tests_not_run(tmp_path, c, cfg("npm test"), tmp_path, VITEST_OUT) == "apps/office/tests/auth.test.ts"
    ran = VITEST_OUT.replace("tests/feed.test.ts", "apps/office/tests/auth.test.ts")
    assert recent.own_tests_not_run(tmp_path, c, cfg("npm test"), tmp_path, ran) == ""
    # Output with no list of test files (another reporter) says nothing either way.
    assert recent.own_tests_not_run(tmp_path, c, cfg("npm test"), tmp_path, "....\nTest Files  2 passed (2)\n") == ""


def test_a_pytest_file_outside_testpaths_is_named(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "test_seed.py").write_text("def test_x():\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_seed.py").write_text("def test_x():\n    pass\n")
    out = {"test_code": ["scripts/test_seed.py"]}
    inside = {"test_code": ["tests/test_seed.py"]}
    assert recent.own_tests_not_run(tmp_path, out, cfg("python -m pytest"), tmp_path, "") == "scripts/test_seed.py"
    assert recent.own_tests_not_run(tmp_path, inside, cfg("python -m pytest"), tmp_path, "") == ""


def test_a_fix_whose_new_test_never_runs_is_not_called_unnoticed(tmp_path):
    root = tmp_path / "shop"
    (root / "tests").mkdir(parents=True)
    (root / "scripts").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    (root / ".bite.ini").write_text("[bite]\ntest_command = python -m pytest -q -p no:cacheprovider\n")
    (root / "shop.py").write_text("def total(xs):\n    return sum(xs)\n")
    (root / "tests" / "test_other.py").write_text("def test_runs():\n    assert True\n")
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "Start"], cwd=root, check=True)
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "scripts" / "test_shop.py").write_text(
        "from shop import total\n\n\ndef test_total_rounds_to_cents():\n    assert total([0.1, 0.2]) == 0.3\n")
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "Fix total rounding"], cwd=root, check=True)
    p = subprocess.run([sys.executable, RECENT, "--free", "--json"], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    c = json.loads(p.stdout)["commits"][0]
    assert c["result"] == "skipped", (c, p.stderr)
    assert "never runs its test `scripts/test_shop.py`" in c["label"] + str(c), (c, p.stderr)
