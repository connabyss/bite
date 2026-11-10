"""Faster for users (2026-11-02): --jobs checks several commits at the same time on one machine, and a commit
checked before with ✅ isn't run again unless something it depends on changed. Neither may hide a real gap.
No key, no network."""

import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PY = sys.executable

# Fails whenever another run of it is going at the same time, like tests that use the same port or database.
CLASH = ("import os, time, tempfile, pathlib\n\n\ndef test_alone():\n"
         "    lock = pathlib.Path(tempfile.gettempdir()) / ('bite_clash_' + os.environ.get('CLASH_ID', ''))\n"
         "    try:\n        fd = os.open(lock, os.O_CREAT | os.O_EXCL)\n    except FileExistsError:\n"
         "        raise AssertionError('another run is using it')\n"
         "    try:\n        time.sleep(1.5)\n    finally:\n        os.close(fd)\n        os.remove(lock)\n")


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "HEAD").strip()[:8]


def bite(root, *args, env=None):
    import os
    e = dict(os.environ, **(env or {}))
    return subprocess.run([PY, str(KIT / "recent.py"), "--free", "--any", "--free-checks", "10", *args], cwd=root,
                          capture_output=True, text=True, timeout=300, env=e).stdout


def line(out, sha):
    return next((ln for ln in out.splitlines() if ln.startswith(f"  {sha} ")), "")


def project(tmp_path):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "shop.py").write_text("def total(xs):\n    return sum(xs)\n")
    (root / "tests" / "test_shop.py").write_text("import shop\n\n\ndef test_total():\n    assert shop.total([1, 2]) == 3\n")
    commit(root, "start")
    return root


def test_tests_that_clash_side_by_side_cant_hide_a_gap(tmp_path):
    root = project(tmp_path)
    (root / "tests" / "test_clash.py").write_text(CLASH)
    commit(root, "a test that needs the machine to itself")
    shas = []
    for name in ("a", "b", "c"):  # three changes no test looks at
        with open(root / "shop.py", "a") as f:
            f.write(f"\n\ndef {name}():\n    return '{name}'\n")
        shas.append(commit(root, f"Fix {name}"))
    out = bite(root, "--jobs", "3", "--only", ",".join(shas), env={"CLASH_ID": str(tmp_path.name)})
    assert "3 at a time" in out, out
    for sha in shas:
        assert "NO TEST NOTICED" in line(out, sha), out


def test_a_remembered_check_is_asked_again_once_its_test_is_deleted(tmp_path):
    root = project(tmp_path)
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "tests" / "test_round.py").write_text("import shop\n\n\ndef test_round():\n"
                                                  "    assert shop.total([0.1, 0.2]) == 0.3\n")
    fix = commit(root, "Fix total rounding")
    first = bite(root)
    assert "noticed by test_round" in line(first, fix), first
    again = bite(root)
    assert "checked before with" in again and "noticed" in line(again, fix), again
    (root / "tests" / "test_round.py").unlink()  # the test that guarded it is deleted later
    commit(root, "tidy tests")
    after = bite(root)
    assert "checked before" not in after, after
    assert "noticed by test_round" not in line(after, fix), after


def test_a_remembered_check_is_asked_again_once_its_test_is_weakened(tmp_path):
    root = project(tmp_path)
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "tests" / "test_round.py").write_text("import shop\n\n\ndef test_round():\n"
                                                  "    assert shop.total([0.1, 0.2]) == 0.3\n")
    fix = commit(root, "Fix total rounding")
    assert "noticed by test_round" in line(bite(root), fix)
    # the test still exists, but no longer checks the rounding the fix added
    (root / "tests" / "test_round.py").write_text("import shop\n\n\ndef test_round():\n"
                                                  "    assert shop.total([1, 2]) == 3\n")
    commit(root, "simplify test")
    after = bite(root)
    # It says what a run with no memory says: Bite checks a fix on a copy of its own commit, so a test weakened
    # later doesn't turn it into a gap, and the memory may keep it (it did ask again before, for nothing).
    fresh = bite(root, "--again")
    assert line(after, fix).split()[1:4] == line(fresh, fix).split()[1:4], (after, fresh)


def rounding_fix(root):
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "tests" / "test_round.py").write_text("import shop\n\n\ndef test_round():\n"
                                                  "    assert shop.total([0.1, 0.2]) == 0.3\n")
    return commit(root, "Fix total rounding")


def test_a_later_commit_adding_a_test_keeps_the_earlier_checks(tmp_path):
    # A pull request where every commit adds a test (as it should) started over from zero on each push: a new test
    # file changed what every remembered ✅ was keyed on, though no ✅ can depend on a test written after it.
    root = project(tmp_path)
    fix = rounding_fix(root)
    assert "noticed by test_round" in line(bite(root), fix)
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n\n\ndef count(xs):\n"
                                  "    return len(xs)\n")
    (root / "tests" / "test_count.py").write_text("import shop\n\n\ndef test_count():\n"
                                                  "    assert shop.count([1, 2]) == 2\n")
    new = commit(root, "Fix count")
    after = bite(root)
    assert "1 commit checked before with" in after, after
    assert "noticed by test_round" in line(after, fix), after
    assert "noticed by test_count" in line(after, new), after  # the new commit itself is checked


def test_a_later_commit_adding_to_an_existing_test_file_keeps_the_earlier_checks(tmp_path):
    root = project(tmp_path)
    fix = rounding_fix(root)
    assert "noticed by test_round" in line(bite(root), fix)
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n\n\ndef count(xs):\n"
                                  "    return len(xs)\n")
    with open(root / "tests" / "test_round.py", "a") as f:
        f.write("\n\ndef test_count():\n    assert shop.count([1, 2]) == 2\n")
    commit(root, "Fix count")
    after = bite(root)
    assert "1 commit checked before with" in after and "noticed by test_round" in line(after, fix), after


def test_a_piece_only_a_later_test_notices_is_asked_again_once_that_test_is_weakened(tmp_path):
    # The ✅ here leans on today's tests: one piece of the fix had no test at its commit, and a later test notices it.
    # Weaken that later test and the memory must not keep the ✅: a run with no memory finds the untested piece.
    root = project(tmp_path)
    (root / "shop.py").write_text("def total(xs):\n    return sum(xs)\n\n\ndef count(xs):\n    return len(xs)\n")
    commit(root, "add count")
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n\n\n"
                                  "def count(xs):\n    return len([x for x in xs if x is not None])\n")
    (root / "tests" / "test_round.py").write_text("import shop\n\n\ndef test_round():\n"
                                                  "    assert shop.total([0.1, 0.2]) == 0.3\n")
    fix = commit(root, "Fix total rounding and count")
    (root / "tests" / "test_count.py").write_text("import shop\n\n\ndef test_count():\n"
                                                  "    assert shop.count([1, None]) == 1\n")
    commit(root, "test count")
    first = bite(root)
    assert "noticed by test_round" in line(first, fix), first
    (root / "tests" / "test_count.py").write_text("import shop\n\n\ndef test_count():\n"
                                                  "    assert shop.count([1]) == 1\n")
    commit(root, "simplify count test")
    after = bite(root)
    # asked again, it finds the piece no test notices now (what a run with no memory says)
    assert "PART NOT NOTICED" in line(after, fix) and "checked before" not in after, after


def test_a_check_that_leaned_on_todays_tests_is_asked_again_when_they_change(tmp_path):
    # A ✅ that used today's tests (a piece of the change checked on today's code, or a test deleted since) still
    # needs every test file to be the same.
    import importlib
    sys.path.insert(0, str(KIT))
    recent = importlib.import_module("recent")
    root = project(tmp_path)
    fix = rounding_fix(root)
    c = {"sha": git(root, "rev-parse", fix).strip(), "code": ["shop.py"]}
    cfg = recent.repo.load_cfg(root)
    key, base = recent.checked_key(root, cfg), recent.checked_key(root, cfg, tests=False)
    (root / "tests" / "test_more.py").write_text("def test_more():\n    assert True\n")
    commit(root, "more tests")
    key2, base2 = recent.checked_key(root, cfg), recent.checked_key(root, cfg, tests=False)
    assert key2 != key and base2 == base
    assert recent.still_holds(root, c, {"key": key, "base": base, "today": False}, key2, base2, cfg)
    assert not recent.still_holds(root, c, {"key": key, "base": base, "today": True}, key2, base2, cfg)
    assert not recent.still_holds(root, c, {"key": key}, key2, base2, cfg)  # written by an older Bite


def test_a_new_dependency_version_asks_again(tmp_path):
    root = project(tmp_path)
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "tests" / "test_round.py").write_text("import shop\n\n\ndef test_round():\n"
                                                  "    assert shop.total([0.1, 0.2]) == 0.3\n")
    fix = commit(root, "Fix total rounding")
    bite(root)
    assert "checked before" in bite(root)
    (root / "requirements.txt").write_text("decimal-helpers==2.0\n")
    commit(root, "bump a library")
    assert "checked before" not in bite(root)

def test_a_slow_run_says_what_makes_the_next_one_faster():
    sys.path.insert(0, str(KIT))
    import recent
    from types import SimpleNamespace
    slow = recent.slow_tip(600, 5, SimpleNamespace(test_cmd="python -m pytest -q"))
    assert "about 10 minutes" in slow and "--jobs 4" in slow and "--shard 1/4" in slow and "-n auto" in slow
    assert "-n auto" not in recent.slow_tip(600, 5, SimpleNamespace(test_cmd="python -m pytest -n auto"))
    assert "-n auto" not in recent.slow_tip(600, 5, SimpleNamespace(test_cmd="npm test"))
    assert recent.slow_tip(60, 5, SimpleNamespace(test_cmd="npm test")) == ""


def test_a_slow_step_shows_it_is_still_working(capsys):
    sys.path.insert(0, str(KIT))
    import recent
    import time as t
    with recent.heartbeat(every=0.05):
        t.sleep(0.3)
    out = capsys.readouterr().out
    assert "still working" in out and "$0.00 so far" in out
    with recent.heartbeat(every=0.05):
        pass
    t.sleep(0.2)
    assert "still working" not in capsys.readouterr().out  # it stops when the step is done


def test_no_still_working_line_after_the_step_ends(monkeypatch, capsys):
    # Windows CI, 2026-11-04: a "still working" line already on its way printed after the step ended. The step's
    # end now waits for it. Here the line takes 0.2 s to print, so without that wait it lands after the end.
    sys.path.insert(0, str(KIT))
    import recent
    import time as t
    real = recent.step
    monkeypatch.setattr(recent, "step", lambda msg: (t.sleep(0.2), real(msg)))
    with recent.heartbeat(every=0.05):
        t.sleep(0.07)
    capsys.readouterr()
    t.sleep(0.4)
    assert "still working" not in capsys.readouterr().out


def test_jobs_beside_a_test_command_that_is_already_parallel_gets_a_warning():
    """Bite's own repo (4 cores, pytest -n auto, 2026-11-10): --jobs 2 took 22 min against 14 one at a time, and
    --jobs 3 overloaded the machine until tests timed out. So --jobs beside -n auto says so, and the slow-run tip
    stops suggesting --jobs there."""
    sys.path.insert(0, str(KIT))
    import recent
    from types import SimpleNamespace
    saved = recent.JOBS[0]
    try:
        recent.JOBS[0] = 3
        warn = recent.jobs_clash("python -m pytest -q -n auto -p no:cacheprovider")
        assert "-n auto" in warn and "--jobs 3" in warn and "slower" in warn
        assert recent.jobs_clash("python -m pytest -q --numprocesses=4") != ""
        assert recent.jobs_clash("python -m pytest -q -n 0") == ""  # -n 0: xdist off, one process
        assert recent.jobs_clash("python -m pytest -q") == ""
        assert recent.jobs_clash("npm test -- -n auto") == ""  # not pytest's -n
        recent.JOBS[0] = 1
        assert recent.jobs_clash("python -m pytest -n auto") == ""  # no --jobs, nothing to fight
    finally:
        recent.JOBS[0] = saved
    assert "--jobs" not in recent.slow_tip(600, 5, SimpleNamespace(test_cmd="python -m pytest -n auto"))
