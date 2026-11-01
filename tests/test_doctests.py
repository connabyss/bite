"""Python doctests: when the tests run the examples in docstrings (pytest --doctest-modules), an example the
commit wrote with its fix is its test. Before this, taking the change out took the example out too, so the fix
read as "no test noticed" (found by the overnight stress test, 2026-11-01)."""

import json
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
OLD = "def total(prices):\n    return sum(prices)\n\n\ndef label(name):\n    return name.title()\n"
NEW = 'def total(prices):\n    """\n    >>> total([0.1, 0.2])\n    0.3\n    """\n    return round(sum(prices), 2)\n\n\n' \
      "def label(name):\n    return name.title()\n"
LABEL_TEST = "from shop import label\n\n\ndef test_label():\n    assert label('tea') == 'Tea'\n"


def git(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


def project(tmp_path, doctests=True):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    git(root, "init", "-q")
    flag = " --doctest-modules" if doctests else ""
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider{flag}\n")
    (root / "shop.py").write_text(OLD)
    (root / "tests" / "test_shop.py").write_text(LABEL_TEST)
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
    (root / "shop.py").write_text(NEW)
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "Fix total rounding")
    return root


def result(root):
    p = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json", "--last", "1"], cwd=root,
                       capture_output=True, text=True, timeout=600)
    return json.loads(p.stdout)["commits"][0]["result"]


def test_docstring_lines_are_found():
    assert recent.doc_lines(NEW.encode()) == {1, 2, 3, 4}
    assert recent.doc_lines(b"def f(:\n") == set()


def test_a_doctest_the_fix_wrote_notices_it(tmp_path):
    assert result(project(tmp_path)) == "noticed"


def test_without_doctests_on_it_is_still_unnoticed(tmp_path):
    # The examples only count when the tests run them.
    assert result(project(tmp_path, doctests=False)) == "no_test_noticed"


def test_doctests_switched_on_in_pytest_settings(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --doctest-modules\n")
    cfg = type("C", (), {"test_cmd": "pytest -q", "free_cmd": ""})()
    assert recent.runs_doctests(cfg, tmp_path)
    assert not recent.runs_doctests(cfg, tmp_path / "nope")
