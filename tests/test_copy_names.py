"""File names that aren't plain ASCII in Bite's copies (found 2026-11-01 when a test with "shop café.py" failed
only on Windows): Bite unpacked git archive with the system's tar, and Windows' tar read the UTF-8 names in the
local code page, so the copy had the file under another name and the project's own tests failed there ("tests
already fail"). Now Python's tarfile unpacks it, on every system. No key, no network."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def test_a_copy_keeps_non_ascii_names_without_the_system_tar(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    git(root, "init", "-q")
    (root / "pkg" / "café.py").write_text("X = 1\n", encoding="utf-8")
    (root / "pkg" / "日本.txt").write_text("hi\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "start")
    sha = git(root, "rev-parse", "HEAD").strip()
    # The system's tar is what mangled the names on Windows; the copy must not depend on one.
    real = recent.subprocess.run

    def no_tar(cmd, *a, **kw):
        if Path(str(cmd[0])).stem.lower() == "tar":
            raise FileNotFoundError("no tar here")
        return real(cmd, *a, **kw)
    monkeypatch.setattr(recent.subprocess, "run", no_tar)
    dest = recent.export(root, sha, SimpleNamespace(copy_ignore=[]))
    assert (dest / "pkg" / "café.py").read_text(encoding="utf-8") == "X = 1\n"
    assert (dest / "pkg" / "日本.txt").is_file()

