"""Bite printed "1 commits changed code" and "Checked 1 commit(s)" for a single commit. Read aloud, "(s)" is
noise and "1 commits" is a typo; say "1 commit" and "2 commits" instead."""

import io
import subprocess
import sys
import tarfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent

RECENT = str(KIT / "recent.py")


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def test_a_single_checked_commit_is_not_plural(tmp_path):
    root = tmp_path / "shop"
    (root / "tests").mkdir(parents=True)
    git(root, "init", "-q")
    (root / "shop.py").write_text("def total(a, b):\n    return a + b + 1\n")
    (root / "tests" / "test_shop.py").write_text(
        "from shop import total\n\n\ndef test_total():\n    assert total(1, 1) == 2\n")
    commit(root, "Start")
    (root / "shop.py").write_text("def total(a, b):\n    return a + b\n")
    commit(root, "Fix total adding one too many")

    p = subprocess.run([sys.executable, RECENT, "--free", "--last", "1"], cwd=root, capture_output=True,
                       text=True, timeout=300)
    out = p.stdout + p.stderr
    assert "Bite: 1 commit changed code in the last 1." in out, out
    assert "Checked 1 commit:" in out, out
    assert "Bite score: 1/1 (a test noticed the one change Bite could check)." in out, out
    assert "1 commits" not in out and "commit(s)" not in out, out
    assert "of the 1 changes" not in out and "1 changes" not in out, out


def test_submodule_singular_message(tmp_path, capsys):
    recent.SUB_WARNED.clear()
    root = tmp_path / "repo1"
    root.mkdir()
    dest = tmp_path / "dest1"
    dest.mkdir()
    (dest / ".gitmodules").write_text('[submodule "sub1"]\n\tpath = sub1\n\turl = ...\n')

    orig_git = recent.repo.git
    recent.repo.git = lambda *a, **kw: "160000 commit 1111111111111111111111111111111111111111\tsub1"
    try:
        left = recent.submodule_fill(root, dest, "HEAD")
        captured = capsys.readouterr().out
        assert left == 1
        assert "1 git submodule isn't checked out" in captured, captured
        assert "submodule(s)" not in captured
        assert "aren't" not in captured
    finally:
        recent.repo.git = orig_git


def test_lfs_singular_message(tmp_path, capsys):
    recent.LFS_WARNED.clear()
    root = tmp_path / "repo2"
    root.mkdir()
    dest = tmp_path / "dest2"
    dest.mkdir()

    # create a tar containing a single small LFS pointer file
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        data = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 100\n"
        ti = tarfile.TarInfo(name="large.bin")
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
    tar = buf.getvalue()

    orig_git = recent.repo.git
    recent.repo.git = lambda *a, **kw: None
    try:
        left = recent.lfs_fill(root, dest, tar)
        captured = capsys.readouterr().out
        assert left == 1
        assert "1 Git LFS file is only a pointer file" in captured, captured
        assert "file(s)" not in captured
        assert "are only pointer files" not in captured
    finally:
        recent.repo.git = orig_git


def test_card_and_html_report_singular(tmp_path):
    root = tmp_path / "card_test"
    root.mkdir()

    # Share card: with n=0, total=1: "No test noticed the one change Bite checked."
    card_path = recent.write_card(root, 0, 1)
    svg = card_path.read_text(encoding="utf-8")
    assert "No test noticed the one change Bite checked." in svg, svg
    assert "of the 1 changes" not in svg, svg

    # HTML report: with n=0, total=1: "No test noticed the one change Bite could check."
    cs = [{"sha": "a" * 40, "subject": "Fix x", "undo": "unguarded"}]
    page = recent.write_html(root, cs, [], 1.0).read_text(encoding="utf-8")
    assert "No test noticed the one change Bite could check." in page, page
    assert "of the 1 changes" not in page, page
