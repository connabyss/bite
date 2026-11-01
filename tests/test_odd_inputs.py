"""Odd inputs found by the overnight stress test (2026-11-01): each test here failed before its fix."""

import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import bite_mcp  # noqa: E402
import live  # noqa: E402
import recent  # noqa: E402
import repo  # noqa: E402


def say(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = recent.main(args)
    return rc, buf.getvalue().strip()


def test_an_option_with_no_value_says_so():
    assert say(["--free", "--last"]) == (2, "Bite: --last needs a value after it, like --last 10.")
    assert say(["--budget"]) == (2, "Bite: --budget needs a value after it, like --budget 1.00.")


def test_a_negative_number_is_refused(tmp_path, monkeypatch):
    # git log -n-5 reads the whole history: on a big project that's hours of test runs.
    monkeypatch.chdir(tmp_path)  # not a repository: a check that slipped through couldn't run here
    assert say(["--free", "--last", "-5"]) == (2, "Bite: --last needs a whole number of 0 or more, got '-5'.")
    assert say(["--budget", "-1"])[0] == 2


def test_a_folder_that_is_not_there_is_not_a_repository(tmp_path):
    assert repo.repo_root(tmp_path / "nope") is None
    (tmp_path / "f.txt").write_text("x")
    assert repo.repo_root(tmp_path / "f.txt") is None
    assert repo.repo_root(5) is None


def test_mcp_says_plainly_when_the_folder_is_wrong(tmp_path):
    (tmp_path / "f.txt").write_text("x")
    for tool in (bite_mcp.check_fix, bite_mcp.ask_bite):
        text, err = tool({"folder": str(tmp_path / "nope"), "question": "is it fixed?"})
        assert err and text == f"Bite: {tmp_path / 'nope'} isn't a folder. Pass the project's folder as folder."
        text, err = tool({"folder": str(tmp_path / "f.txt"), "question": "is it fixed?"})
        assert err and "isn't a folder" in text
        text, err = tool({"folder": 5, "question": "is it fixed?"})
        assert err and text.startswith("Bite: folder must be a path")


def test_the_stop_hook_stays_quiet_in_a_folder_that_is_gone():
    assert live.hook({"cwd": os.path.join(os.sep, "nope", "gone"), "session_id": "s"}) == {}


def test_live_leaves_symbolic_links_out(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "shop.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start"], cwd=root, check=True)
    (root / "shop.py").write_text("x = 2\n")
    try:
        os.symlink("shop.py", root / "link.py")
    except (OSError, NotImplementedError):  # making links needs extra rights on some Windows setups
        (root / "link.py").write_text("x = 3\n")
        assert "link.py" in live.changed(root, "HEAD")
        return
    assert live.changed(root, "HEAD") == ["shop.py"]
