"""Odd repository shapes found by the overnight stress test (2026-11-01): each test here failed before its fix.
No key, no network: tiny repos made on the spot, and Bite's own --json output."""

import json
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
SHOP = "def total(prices):\n    return sum(prices)\n\n\ndef label(name):\n    return name.title()\n"
ROUNDED = SHOP.replace("return sum(prices)", "return round(sum(prices), 2)")
LABEL_TEST = "from shop import label\n\n\ndef test_label():\n    assert label('tea') == 'Tea'\n"


def git(root, *a, **kw):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, **kw)


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def make(tmp_path):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "shop.py").write_text(SHOP)
    (root / "tests" / "test_shop.py").write_text(LABEL_TEST)
    commit(root, "start")
    return root


def add_link(root, rel, target):
    """A symbolic link committed with git's own link mode, so the test runs the same where making links needs rights."""
    blob = git(root, "hash-object", "-w", "--stdin", input=target.encode()).stdout.decode().strip()
    git(root, "update-index", "--add", "--cacheinfo", f"120000,{blob},{rel}")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"Link {rel}")


def test_a_symbolic_link_is_not_code(tmp_path):
    root = make(tmp_path)
    add_link(root, "shop_link.py", "shop.py")
    sha = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    assert recent.changed_files(root, sha) == ([], {})


def test_a_new_link_to_code_does_not_stop_the_run(tmp_path):
    # Bite stopped with "refused to write through a link" when a commit it checked had added a link to a .py file.
    root = make(tmp_path)
    add_link(root, "shop_link.py", "shop.py")
    (root / "shop.py").write_text(ROUNDED)
    commit(root, "Fix total rounding")
    p = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json", "--last", "3"], cwd=root,
                       capture_output=True, text=True, timeout=600)
    assert "Traceback" not in p.stderr, p.stderr[-800:]
    rows = {r["subject"]: r["result"] for r in json.loads(p.stdout)["commits"]}
    assert rows.get("Fix total rounding") == "no_test_noticed", rows


def test_a_file_error_in_one_commit_does_not_stop_the_run(tmp_path, monkeypatch):
    root = make(tmp_path)
    (root / "shop.py").write_text(ROUNDED)
    commit(root, "Fix total rounding")
    c = {"sha": git(root, "rev-parse", "HEAD").stdout.decode().strip(), "subject": "Fix total rounding", "body": ""}
    cfg = recent.repo.load_cfg(root)
    recent.files_of(root, c, cfg)

    def locked(*a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(recent, "take_out", locked)
    u = recent.undo_check(root, c, cfg)
    assert u.startswith("Bite hit a file error") and "Permission denied" in u
    kind, label, _ = recent.say({**c, "undo": u})
    assert kind == "skip" and label.startswith("➖ couldn't check")
