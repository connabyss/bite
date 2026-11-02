"""File paths with spaces in the "check it yourself" steps, found by the overnight stress test (2026-11-01): Bite
wrote `cp /tmp/sp ace/bite_proof/x.py my pkg/shop cafe.py`, which the shell reads as five words, so the steps
failed when pasted. Each test here failed before its fix. No key, no network."""

import shlex
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
SHOP = "def total(xs):\n    return sum(xs)\n\n\ndef label(x):\n    return str(x)\n"
TEST = ("import importlib.util, pathlib\np = pathlib.Path(__file__).parent.parent / 'my pkg' / 'shop cafe.py'\n"
        "spec = importlib.util.spec_from_file_location('shop', p)\nm = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n\n\ndef test_total():\n    assert m.total([1, 2]) == 3\n")


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def steps(report):
    block = report.split("Check it yourself")[1].split("```")[1]
    return [ln for ln in block.strip().splitlines() if ln.startswith(("cp ", "rm ", "git checkout", "git show", "cd "))]


def test_paths_with_spaces_are_quoted_in_the_steps(tmp_path):
    root = tmp_path / "my project"
    (root / "tests").mkdir(parents=True)
    (root / "my pkg").mkdir()
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "my pkg" / "shop cafe.py").write_text(SHOP, encoding="utf-8")
    (root / "tests" / "test_shop.py").write_text(TEST, encoding="utf-8")
    commit(root, "start")
    (root / "my pkg" / "shop cafe.py").write_text(SHOP.replace("return sum(xs)", "return round(sum(xs), 2)")
                                                  .replace("return str(x)", "return str(x).strip()"), encoding="utf-8")
    with open(root / "tests" / "test_shop.py", "a", encoding="utf-8") as f:
        f.write("\n\ndef test_rounds():\n    assert m.total([0.1, 0.2]) == 0.3\n")
    commit(root, "Fix total rounding and label spaces")
    r = subprocess.run([PY, str(KIT / "recent.py"), "--free"], cwd=root, capture_output=True, timeout=300)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    assert (root / "bite_proof" / "FREE_REPORT.md").is_file(), out[-3000:]
    report = (root / "bite_proof" / "FREE_REPORT.md").read_text(encoding="utf-8")
    cp = next(s for s in steps(report) if s.startswith("cp "))
    words = shlex.split(cp)
    assert len(words) == 3 and words[2] == "my pkg/shop cafe.py" and Path(words[1]).is_file(), cp
    cd = [s for s in steps(report) if s.startswith("cd ")][-1]
    assert shlex.split(cd)[1] == root.as_posix(), cd


def test_each_path_is_one_word_for_the_shell():
    assert recent.arg("shop.py") == "shop.py"
    assert shlex.split(recent.arg("my pkg/a b.py")) == ["my pkg/a b.py"]
    assert shlex.split(recent.arg("we$ird `x`.py")) == ["we$ird `x`.py"]
