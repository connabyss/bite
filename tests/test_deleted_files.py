"""A fix that also deletes a file, found by the overnight stress test (2026-11-01): when a test noticed the change
but not every piece of it, Bite stopped the whole run with an IndexError, and it counted putting the deleted file
back as a piece of its own. Each test here failed before its fix. No key, no network."""

import json
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PY = sys.executable
SHOP = "def total(xs):\n    return sum(xs)\n\n\ndef label(x):\n    return str(x)\n"
OLD_HELPERS = "def legacy_total(xs):\n    total = 0\n    for x in xs:\n        total += x\n    return total\n"


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def run(root):
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json"], cwd=root, capture_output=True, text=True,
                         timeout=300)
    assert out.returncode in (0, 1), out.stderr[-2000:]
    return json.loads(out.stdout)["commits"][0]


def make(tmp_path):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "shop.py").write_text(SHOP)
    (root / "old_helpers.py").write_text(OLD_HELPERS)
    (root / "tests" / "test_shop.py").write_text("from shop import total\n\n\ndef test_total():\n"
                                                  "    assert total([1, 2]) == 3\n")
    commit(root, "start")
    (root / "old_helpers.py").unlink()
    with open(root / "tests" / "test_shop.py", "a") as f:
        f.write("\n\ndef test_total_rounds():\n    assert total([0.1, 0.2]) == 0.3\n")
    return root


def test_a_fix_that_deletes_a_file_still_names_its_untested_piece(tmp_path):
    root = make(tmp_path)
    (root / "shop.py").write_text(SHOP.replace("return sum(xs)", "return round(sum(xs), 2)")
                                  .replace("return str(x)", "return str(x).strip()"))
    commit(root, "Fix total rounding and label spaces, drop old helpers")
    c = run(root)
    assert c["label"] == "PART NOT NOTICED" and "label()" in c["detail"] and "old_helpers" not in c["detail"], c


def test_the_deleted_file_is_not_a_piece_of_its_own(tmp_path):
    root = make(tmp_path)
    (root / "shop.py").write_text(SHOP.replace("return sum(xs)", "return round(sum(xs), 2)"))
    commit(root, "Fix total rounding, drop old helpers")
    c = run(root)
    assert c["result"] == "noticed" and "test_total_rounds" in c["label"], c
