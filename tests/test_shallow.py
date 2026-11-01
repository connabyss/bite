"""A shallow clone (git clone --depth 1), found by the overnight stress test (2026-11-01): Bite said "Nothing to
check. Try a larger --last.", which can't help, since the history isn't there. Each test here failed before its
fix. No key, no network."""

import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import ask  # noqa: E402

PY = sys.executable


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def clone(tmp_path):
    src = tmp_path / "src"
    (src / "tests").mkdir(parents=True)
    git(src, "init", "-q")
    (src / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (src / "shop.py").write_text("def total(xs):\n    return sum(xs)\n")
    (src / "tests" / "test_shop.py").write_text("from shop import total\n\n\ndef test_total():\n"
                                                "    assert total([1, 2]) == 3\n")
    commit(src, "start")
    (src / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    commit(src, "Fix total rounding")
    out = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", src.as_uri(), str(out)], check=True, capture_output=True)
    return out


def test_a_shallow_clone_says_to_fetch_the_history(tmp_path):
    root = clone(tmp_path)
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free"], cwd=root, capture_output=True, text=True, timeout=300)
    assert "git fetch --unshallow" in out.stdout and "Try a larger --last" not in out.stdout, out.stdout
    assert "git fetch --unshallow" in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")


def test_bite_ask_in_a_shallow_clone_says_so_too(tmp_path):
    root = clone(tmp_path)
    r = ask.ask(root, "is the rounding fix guarded?", log=lambda s: None, free=True)
    assert "git fetch --unshallow" in r["text"], r["text"]
