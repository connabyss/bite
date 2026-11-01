"""Offline checks for recent.py: a scripted worker and judge, a tiny repo with Claude-made commits.
Run: python tests/selftest.py, or python -m pytest   (no key, no network)"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
print("Bite self-test: about 50 checks on small practice repos, 15 s to 3 min. Each \"ok\" line is one check.",
      flush=True)
CLAUDE = "\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + name, flush=True)


def sh(root, *a):
    subprocess.run(a, cwd=root, check=True, capture_output=True)


def commit(root, msg):
    sh(root, "git", "add", "-A")
    sh(root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)


def make_repo():
    root = Path(tempfile.mkdtemp()) / "proj"
    root.mkdir()
    sh(root, "git", "init", "-q")
    (root / "calc.py").write_text("def clamp(x, lo, hi):\n    return x\n")
    (root / "test_calc.py").write_text("import unittest\nfrom calc import clamp\n\nclass T(unittest.TestCase):\n"
                                       "    def test_mid(self):\n        self.assertEqual(clamp(5, 0, 9), 5)\n")
    (root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n")
    commit(root, "start")
    # Claims both ends; only the low end is done, and no test was added.
    (root / "calc.py").write_text("def clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    return x\n")
    commit(root, "Fix clamp so values stay between lo and hi" + CLAUDE)
    (root / "README.md").write_text("hi\n")
    commit(root, "Add readme" + CLAUDE)
    (root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef double(x):\n    return 2 * x\n")
    commit(root, "Add double (by a person)")
    return root


CLAIM_TEST = ("import unittest\nfrom calc import clamp\n\nclass C(unittest.TestCase):\n"
              "    def test_high(self):\n        self.assertEqual(clamp(50, 0, 9), 9)\n")


def fake_worker(holds=False, test=CLAIM_TEST, path=None, name="test_bite_claim.py"):
    def w(cfg, folder, c, diff, budget):
        (folder / name).write_text(test if not holds else test.replace("50", "5").replace("9)", "5)"))
        return {"test_file": path or name,
                "claim": "clamp keeps values in range", "result": "fails", "why": "high end not clamped"}
    return w


def run(root, argv, worker, verdict="REAL"):
    recent.worker = worker
    recent.judge = lambda cfg, c, diff, test, fail: {"verdict": verdict, "matters": 2, "bug": "clamp lets values above hi through"}
    recent.SPENT[0] = 0.0
    cwd = os.getcwd()
    os.chdir(root)
    try:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = recent.main([a for a in argv if a != "--keep"] if "--keep" in argv else argv + ["--again"])
        return rc, buf.getvalue()
    finally:
        os.chdir(cwd)


# Error guidance must name setup steps that actually exist, without a real key.
with tempfile.TemporaryDirectory() as tmp:
    missing = Path(tmp) / "missing.ini"
    try:
        recent.bite.Config(missing)
    except SystemExit as exc:
        message = str(exc)
        check("missing config points to optional .bite.ini, not an absent setup command",
              "missing.ini" in message and ".bite.ini" in message and "optional" in message
              and "--setup" not in message)
    else:
        check("missing config fails clearly", False)
    with patch.dict(os.environ, {}, clear=True), patch.object(recent.bite, "KEY_FILE", Path(tmp) / "key.txt"):
        try:
            recent.bite.load_key()
        except SystemExit as exc:
            message = str(exc)
            check("missing key explains environment and key.txt options, not an absent setup command",
                  "ANTHROPIC_API_KEY" in message and "key.txt" in message and "--setup" not in message)
        else:
            check("missing key fails clearly", False)


project = (KIT / "pyproject.toml").read_text(encoding="utf-8")
expected_version = next(line.split("=", 1)[1].strip().strip('"') for line in project.splitlines()
                        if line.startswith("version ="))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = recent.main(["--version"])
check("--version prints the installed version and exits 0",
      rc == 0 and buf.getvalue().strip() == f"bite {expected_version}")

buf = io.StringIO()
with patch("importlib.metadata.version", side_effect=PackageNotFoundError("bite-check")), \
        contextlib.redirect_stdout(buf):
    rc = recent.main(["--version"])
check("--version falls back to pyproject.toml when Bite isn't installed",
      rc == 0 and buf.getvalue().strip() == f"bite {expected_version}")

a = {"subject": "Fix tooltip spacing", "body": "", "sha": "x"}
b = {"subject": "Fix export so saved files aren't truncated", "body": "", "sha": "y"}
for c in (a, b):
    c["score"] = (3 if recent.CLAIM.search(c["subject"]) else 0) + (2 if recent.MATTERS.search(c["subject"]) else 0)
check("claims about saving or data rank above cosmetic ones", b["score"] > a["score"])

root = make_repo()
check("every commit is picked, whoever or whatever made it", len(recent.commits(root, 40)) == 4)

rc, out = run(root, [], fake_worker())
check("false done found", 'FALSE "DONE": commit' in out and "Fix clamp" in out)
check("unguarded change reported", "NO TEST NOTICED" in out)
check("still broken today", "STILL BROKEN" in out)
check("proof written", (root / "bite_proof" / "REPORT.md").is_file() and
      any(p.name.endswith("test_bite_claim.py") for p in (root / "bite_proof").iterdir()))
check("readme commit not tested (no code)", "Add readme" not in out.split("Bite:")[1].split("\n")[1] if "\n" in out else True)

rc, out = run(root, ["--keep"], fake_worker(holds=True))
check("a claim tested before is not paid for again", "earlier run" in out and "$0.00" in out and 'FALSE "DONE"' in out)

rc, out = run(root, [], fake_worker(holds=True))
check("a claim that holds is not reported", "FALSE" not in out and "held up" in out)

rc, out = run(root, [], fake_worker(), verdict="NOT")
check("second check can veto", "FALSE" not in out and "second check disagreed" in out)

rc, out = run(root, [], fake_worker(path="../../etc/test_bite_claim.py"))
check("test file outside the copy is ignored", "no test written" in out and "FALSE" not in out)

rc, out = run(root, [], fake_worker(test="import nothing_here\n"))
check("test that doesn't load is not a finding", "FALSE" not in out and "didn't load" in out)

rc, out = run(root, ["--free"], fake_worker())
check("--free spends nothing and tests no claims", "FALSE" not in out and "$0.00" in out)

# --write-tests: for a change no test noticed, a worker writes the missing test. Bite keeps it only if it passes
# with the change in and fails with the change taken out, and shows it in the pull request comment.
GUARD_TEST = ("import unittest\nfrom calc import clamp\n\nclass G(unittest.TestCase):\n"
              "    def test_low(self):\n        self.assertEqual(clamp(-5, 0, 9), 0)\n")


def fake_guard(test=GUARD_TEST):
    def w(cfg, folder, c, diff, budget):
        (folder / "test_bite_claim.py").write_text(test)
        return {"test_file": "test_bite_claim.py", "guards": "clamp lifts values below lo up to lo"}
    return w


def no_claim_worker(*a):
    raise AssertionError("--write-tests must not test claims")


real_guard, real_guard_judge = recent.guard_worker, recent.guard_judge
recent.guard_judge = lambda cfg, c, diff, test, fail: {"verdict": "FAIR", "why": "it tests the low clamp"}
try:
    recent.guard_worker = fake_guard()
    rc, out = run(root, ["--write-tests"], no_claim_worker)
    comment = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")
    report = (root / "bite_proof" / "FREE_REPORT.md").read_text(encoding="utf-8")
    check("--write-tests: a test that passes with the change and fails without it is kept",
          "wrote one: passes with the change, fails without it" in out and "FALSE" not in out)
    check("--write-tests: the pull request comment shows the test, ready to paste in",
          "🧪 The missing test" in comment and "clamp(-5, 0, 9)" in comment and "~~~~python" in comment
          and "Bite wrote below (🧪) for 1 of them" in comment and "paste in the test Bite wrote (🧪 below)" in comment)
    check("--write-tests: the report shows how it failed without the change, and the test is saved",
          "failed like this" in report and any(p.name.endswith("_test_bite_claim.py") for p in (root / "bite_proof").iterdir()))
    kept = root / "bite_proof" / "missing_tests" / "test_bite_claim.py"
    check("--write-tests: the kept test is saved at its own path, ready to drop in or download",
          kept.is_file() and "clamp(-5, 0, 9)" in kept.read_text(encoding="utf-8"))
    with patch.dict(os.environ):
        os.environ.pop("GITHUB_RUN_ID", None)  # CI sets it: this run stands for one on a computer
        rc, out = run(root, ["--write-tests"], no_claim_worker)
    check("--write-tests on a computer: no download line in the comment",
          "📥" not in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8"))
    with patch.dict(os.environ, {"GITHUB_RUN_ID": "77", "GITHUB_REPOSITORY": "o/r"}):
        rc, out = run(root, ["--write-tests"], no_claim_worker)
    check("--write-tests in the Action: the comment points to the download on the run's page",
          "📥 Or download it" in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")
          and "github.com/o/r/actions/runs/77" in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8"))
    recent.guard_worker = fake_guard(GUARD_TEST.replace("clamp(-5, 0, 9), 0", "clamp(5, 0, 9), 5"))
    rc, out = run(root, ["--write-tests"], no_claim_worker)
    comment = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")
    check("--write-tests: a test that passes without the change too is thrown away",
          "passed without the change too" in out and "🧪" not in comment and "add a test that fails without it" in comment)
    check("--write-tests: a thrown-away test isn't offered for download", not (root / "bite_proof" / "missing_tests").exists())
    recent.guard_worker = fake_guard(GUARD_TEST.replace("clamp(-5, 0, 9), 0", "clamp(50, 0, 9), 9"))
    rc, out = run(root, ["--write-tests"], no_claim_worker)
    check("--write-tests: a test that fails with the change in is thrown away",
          "failed with the change in" in out and "🧪" not in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8"))
    # The same bar as a claim test: a second fresh check must call the written test fair, or it isn't kept.
    recent.guard_worker = fake_guard()
    seen = []
    recent.guard_judge = lambda cfg, c, diff, test, fail: seen.append(fail) or {"verdict": "NOT", "why": "it tests a typo"}
    rc, out = run(root, ["--write-tests"], no_claim_worker)
    check("--write-tests: a test the second check doesn't call fair is thrown away",
          len(seen) == 1 and "clamp" in seen[0] and "second check didn't call its test fair (it tests a typo)" in out
          and "🧪" not in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")
          and not (root / "bite_proof" / "missing_tests").exists())
    recent.guard_judge = lambda cfg, c, diff, test, fail: {"verdict": "FAIR", "why": "it tests the low clamp"}
    rc, out = run(root, ["--free"], no_claim_worker)
    check("--free alone writes no test", "writing the missing test" not in out)
finally:
    recent.guard_worker, recent.guard_judge = real_guard, real_guard_judge

rc, out = run(root, ["--serious"], fake_worker())
check("--serious skips claims that aren't about data, money, logins, security or crashes",
      "FALSE" not in out and "testing the claim" not in out and "Nothing serious to check" in out)

# Fixed later: today's code passes the claim test.
(root / "calc.py").write_text("def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n")
commit(root, "really clamp (by a person)")
rc, out = run(root, [], fake_worker())
check("fixed since is said so", "fixed since" in out)

# A long free pass: each result shows the moment it's known (even with output sent to a file) and is saved, so
# stopping partway keeps it. And bite_proof/ stays out of the user's git.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef half(x):\n    return x / 2\n")
commit(root, "Fix half so it handles odd numbers" + CLAUDE)


class Out(io.StringIO):
    flushed = ""

    def flush(self):
        self.flushed = self.getvalue()


real_undo, seen = recent.undo_check, []


def stop_on_second(*a):
    seen.append(1)
    if len(seen) == 2:
        raise KeyboardInterrupt
    return real_undo(*a)


recent.undo_check = stop_on_second
buf, cwd = Out(), os.getcwd()
os.chdir(root)
try:
    with contextlib.redirect_stdout(buf):
        recent.main(["--free", "--again"])
except KeyboardInterrupt:
    pass
finally:
    os.chdir(cwd)
    recent.undo_check = real_undo
check("free pass: the first result is shown before the run ends", "NO TEST NOTICED" in buf.flushed)
log = root / "bite_proof" / "recent_log.json"
check("free pass: stopped partway, the first result is saved",
      log.is_file() and any(c.get("undo") for c in recent.json.loads(log.read_text())["free"]))
run(root, ["--free"], fake_worker())
st = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
check("bite_proof/ doesn't show up in git status", "bite_proof" not in st)

# Two tests written at the same path (each on its own copy) both land in missing_tests/, the second renamed.
g = lambda sha, t: {"sha": sha, "guard": {"status": "WRITTEN", "test_file": "tests/test_bite_claim.py", "test": t}}  # noqa: E731
saved = recent.save_missing_tests(root, [g("aaaaaaaa11", "one\n"), g("bbbbbbbb22", "two\n"),
                                        {"sha": "c", "guard": {"status": "its test passed without the change too"}}])
check("missing tests: two at one path are both kept, the second named after its commit",
      saved == ["tests/test_bite_claim.py", "tests/test_bite_claim_bbbbbbbb.py"]
      and (root / "bite_proof" / "missing_tests" / "tests" / "test_bite_claim_bbbbbbbb.py").read_text() == "two\n")
recent.save_missing_tests(root, [])

# test_covers: a change the test command can't reach is listed as such, not called "unguarded".
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                "test_covers = calc.py, test_*\n")
(root / "view.py").write_text("COLOR = 'red'\n")
commit(root, "Fix the panel colour in the view" + CLAUDE)
rc, out = run(root, ["--free"], fake_worker())
check("test_covers: a commit outside the tests' reach is listed, not checked",
      "outside the tests' reach" in out and "the panel colour" not in out and "Fix clamp" in out)

# A test runner only notices its own language: pytest passing with a TypeScript change taken out says nothing.
check("the test command's language: pytest is Python, npm test is JavaScript, make is unknown",
      [recent.repo.runs_language(c)[0] for c in (f"{PY} -m pytest -q", "npm test", "cargo test", "make test",
                                                  "npm test && pytest")] == ["Python", "JavaScript or TypeScript", "Rust", "", ""])
check("JavaScript runners called by name are JavaScript too (tape, ava, uvu, and under nyc or c8 coverage)",
      {recent.repo.runs_language(c)[0] for c in ("nyc tape 'test/**/*.js'", "tape test/*.js", "c8 ava", "uvu tests",
                                                  "tap", "jasmine")} == {"JavaScript or TypeScript"})
root = make_repo()
(root / "app.ts").write_text("export const clampUi = (x: number) => Math.max(0, x);\n")
commit(root, "Fix the slider so it never goes below zero" + CLAUDE)
rc, out = run(root, ["--free"], fake_worker())
check("a TypeScript-only fix under Python tests is listed as code the tests can't run, not flagged",
      "1 changed only code your tests can't run (they run Python)" in out and "never goes below zero" not in out
      and "Fix clamp" in out)
(root / "app.ts").write_text("export const clampUi = (x: number) => Math.min(9, Math.max(0, x));\n")
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef half(x):\n    return x / 2\n")
commit(root, "Fix the slider top end and add half" + CLAUDE)
c = {"sha": recent.repo.git(root, "rev-parse", "HEAD"), "subject": "Fix the slider top end and add half", "body": ""}
recent.files_of(root, c, recent.repo.load_cfg(root))
check("a commit changing Python and TypeScript takes out only the Python part",
      c["code"] == ["calc.py"] and c["other_lang"] == ["app.ts"])
root = make_repo()
(root / "app.ts").write_text("export const clampUi = (x: number) => Math.max(0, x);\n")
commit(root, "Fix the slider so it never goes below zero" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("only TypeScript changed: the comment says the Python tests can't notice it, not 'no code changed'",
      "isn't Python, and your tests only run Python" in (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8"))

# No commit claims a fix: say so and stop, rather than spend checks on commits that promise nothing.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef triple(x):\n    return 3 * x\n")
commit(root, "Triple, for the scoreboard" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("no fix claims: says so and checks nothing", "No fix claims found in the last 1" in out and "free check" not in out)
rc, out = run(root, ["--free", "--last", "1", "--any"], fake_worker())
check("--any checks them anyway", "free check of 1" in out)

# A change to comments only isn't a code change: nothing to undo, nothing to flag.
root = make_repo()
(root / "calc.py").write_text("# Clamp helpers.\n" + (root / "calc.py").read_text())
(root / "test_more.py").write_text("import unittest\n\nclass M(unittest.TestCase):\n    def test_ok(self):\n        pass\n")
commit(root, "Add more tests, fix the header comment" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("a comment-only edit isn't checked as a code change", "ITS TESTS DIDN'T NOTICE" not in out and "free check" not in out)

# A test that guards nothing: the commit's own new test still passes with its code change taken out.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text().replace("2 * x", "x + x if x else 0"))
(root / "test_double.py").write_text("import unittest\nfrom calc import double\n\nclass D(unittest.TestCase):\n"
                                     "    def test_zero(self):\n        self.assertEqual(double(0), 0)\n")
commit(root, "Double zero right away, for the scoreboard" + CLAUDE)
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef sq(x):\n    return x * x\n")
(root / "test_sq.py").write_text("import unittest\nfrom calc import sq\n\nclass S(unittest.TestCase):\n"
                                 "    def test_sq(self):\n        self.assertEqual(sq(3), 9)\n")
commit(root, "Square, for the scoreboard" + CLAUDE)
rc, out = run(root, ["--free", "--last", "2"], fake_worker())
check("fake test: a commit's own test that passes without its code is reported, by name",
      "ITS TESTS DIDN'T NOTICE" in out and "test_double.py" in out and "No fix claims" in out)
check("fake test: a commit whose test does fail without its code is not", "test_sq.py" not in out)
rep = (root / "bite_proof" / "FREE_REPORT.md").read_text() if (root / "bite_proof" / "FREE_REPORT.md").is_file() else ""
check("fake test: the report gives the commit, the gap, a rerun recipe and a note for their coding AI",
      "Double zero right away" in rep and "What Bite saw" in rep and "git worktree add" in rep
      and "Hand this to your coding AI" in rep and "Checked 2 commit(s): a test noticed 1" in out)

# A flagged commit that created a file: `git checkout <sha>^ -- <file>` has no such path to restore, so the
# recipe has to delete it instead.
fresh_root = make_repo()
(fresh_root / "fresh.py").write_text("def triple(x):\n    return 3 * x\n")
commit(fresh_root, "Fix the scoreboard triple" + CLAUDE)
run(fresh_root, ["--free", "--last", "1"], fake_worker())
fresh_rep = (fresh_root / "bite_proof" / "FREE_REPORT.md").read_text()
checkout_lines = [ln for ln in fresh_rep.splitlines() if "git checkout" in ln]
check("free report: a file the commit created is deleted, not put in the git checkout line",
      "rm -f fresh.py" in fresh_rep and not any("fresh.py" in ln for ln in checkout_lines))
# A commit that created a module, in a project that's also pip-installed (#28): with the module deleted from Bite's
# copy, Python would import the installed one and the commit's own test would pass. PYTHONPATH stands in for the install.
inst_root = make_repo()
(inst_root / "fresh.py").write_text("def triple(x):\n    return 3 * x\n")
(inst_root / "test_fresh.py").write_text("import unittest\nfrom fresh import triple\n\nclass F(unittest.TestCase):\n"
                                         "    def test_two(self):\n        self.assertEqual(triple(2), 6)\n")
commit(inst_root, "Fix the scoreboard triple" + CLAUDE)
installed = Path(tempfile.mkdtemp())
(installed / "fresh.py").write_text((inst_root / "fresh.py").read_text())
with patch.dict(os.environ, {"PYTHONPATH": str(installed)}):
    rc, out = run(inst_root, ["--free", "--last", "1"], fake_worker())
check("installed copy: a module the commit created isn't loaded from the install instead (#28)",
      "ITS TESTS DIDN'T NOTICE" not in out and "✅ tests crash without it" in out)
# A src/ layout installed with pip install -e .: the copy must load its own src/, not the checkout's.
src_root = make_repo()
(src_root / "src" / "shapes").mkdir(parents=True)
(src_root / "src" / "shapes" / "__init__.py").write_text("def sides(name):\n    return 0\n")
(src_root / "test_shapes.py").write_text("import unittest\nfrom shapes import sides\n\nclass S(unittest.TestCase):\n"
                                         "    def test_square(self):\n        self.assertEqual(sides('square'), 4)\n")
(src_root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q test_shapes\nallowed_programs = {PY}\n")
commit(src_root, "start shapes")
(src_root / "src" / "shapes" / "__init__.py").write_text("def sides(name):\n    return 4 if name == 'square' else 0\n")
commit(src_root, "Fix sides for a square" + CLAUDE)
editable = Path(tempfile.mkdtemp())  # what pip install -e . puts on the path: today's code
(editable / "shapes").mkdir()
(editable / "shapes" / "__init__.py").write_text((src_root / "src" / "shapes" / "__init__.py").read_text())
with patch.dict(os.environ, {"PYTHONPATH": str(editable)}):
    rc, out = run(src_root, ["--free", "--last", "1"], fake_worker())
check("src/ layout: each copy loads its own src/, not an editable install of today's code",
      "NO TEST NOTICED" not in out and "noticed by test_square" in out)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("a run that flags nothing says what it verified", "Checked 1 commit(s): a test noticed 1," in out)

# Noise filters for TEST GUARDS NOTHING (from 7 noise flags on two real repos): another OS, a tidy-up, tests
# written for other code, and a gap a later commit closed. Each would otherwise be flagged.
def weak_commit(subject, test_src=None):
    root = make_repo()
    (root / "calc.py").write_text((root / "calc.py").read_text().replace("2 * x", "x + x if x else 0"))
    (root / "test_double.py").write_text(test_src or ("import unittest\nfrom calc import double\n\nclass D(unittest.TestCase):\n"
                                                      "    def test_zero(self):\n        self.assertEqual(double(0), 0)\n"))
    commit(root, subject + CLAUDE)
    return root


other_os = "macOS" if recent.HERE != "mac" else "Windows"
rc, out = run(weak_commit(f"Double zero right away on {other_os}"), ["--free", "--last", "1"], fake_worker())
check("noise: a change built for another OS isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "built for" in out)
rc, out = run(weak_commit("chore(lint): tidy double"), ["--free", "--last", "1"], fake_worker())
check("noise: a tidy-up isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "tidy-up" in out)
rc, out = run(weak_commit("Refactor double into one line"), ["--free", "--last", "1"], fake_worker())
check("noise: a refactor or rename without a \"refactor:\" prefix isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "tidy-up" in out)
for subject in ("Release 1.0.154", "Bump version to 12.2.0", "v2.3.1"):
    rc, out = run(weak_commit(subject), ["--free", "--last", "1"], fake_worker())
    check(f"noise: a release commit ({subject}) isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "a release" in out)
rc, out = run(weak_commit("Release the lock when double fails"), ["--free", "--last", "1"], fake_worker())
check("a commit that only starts with \"Release\" is still checked", "ITS TESTS DIDN'T NOTICE" in out)
# Go: interface{} and any are the same type, so swapping one for the other changes nothing a test could see.
root = make_repo()
(root / "box.go").write_text("package box\n\nfunc Keep(v interface{}) interface{} { return v }\n")
commit(root, "add box")
(root / "box.go").write_text("package box\n\nfunc Keep(v any) any { return v }\n")
commit(root, "Replace interface{} with any")
sha = recent.repo.git(root, "rev-parse", "HEAD")
check("noise: Go interface{} -> any counts as no code change", recent.comment_only(root, sha, "box.go"))
(root / "box.go").write_text("package box\n\nfunc Keep(v string) any { return v }\n")
commit(root, "Keep strings only")
sha = recent.repo.git(root, "rev-parse", "HEAD")
check("a real Go type change still counts as code", not recent.comment_only(root, sha, "box.go"))
root = make_repo()
(root / "calc.py").write_text('"""Small number helpers."""\n\n' + (root / "calc.py").read_text().replace(
    "def double(x):\n", 'def double(x):\n    """Twice x: handles negatives too."""\n'))
commit(root, "Explain how double handles negatives" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("noise: a commit that only edits docstrings isn't flagged", "NO TEST NOTICED" not in out and "Nothing to check" in out)
root = make_repo()
(root / "calc.py").write_text("from typing import Optional\n\n\n" + (root / "calc.py").read_text().replace(
    "def double(x):", "def double(x: int) -> Optional[int]:"))
commit(root, "Add type hints to double" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("noise: a commit that only adds type hints isn't flagged", "NO TEST NOTICED" not in out and "Nothing to check" in out)
root = make_repo()
(root / "calc.py").write_text("from dataclasses import dataclass\n\n\n@dataclass\nclass Box:\n    size: int = 0\n\n\n" + (root / "calc.py").read_text())
commit(root, "start box")
(root / "calc.py").write_text((root / "calc.py").read_text().replace("    size: int = 0", "    size: str = 0"))
commit(root, "Box size is text" + CLAUDE)
rc, out = run(root, ["--free", "--any", "--last", "1"], fake_worker())
check("a type hint a decorator reads (a dataclass field) still counts as code", "NO TEST NOTICED" in out)
other_py = 8 if sys.version_info[1] != 8 else 9
rc, out = run(weak_commit(f"Double zero right away on Python 3.{other_py}"), ["--free", "--last", "1"], fake_worker())
check("noise: a change for another Python version isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and f"built for Python 3.{other_py}" in out)
rc, out = run(weak_commit(f"Double zero right away on Python 3.{sys.version_info[1]}"), ["--free", "--last", "1"], fake_worker())
check("a change for this Python version is still checked", "ITS TESTS DIDN'T NOTICE" in out)
rc, out = run(weak_commit("perf: double zero faster"), ["--free", "--last", "1"], fake_worker())
check("noise: a speed-up isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "speed-up" in out)
rc, out = run(weak_commit("Fix double zero, faster"), ["--free", "--last", "1"], fake_worker())
check("a speed-up that also claims a fix is still checked", "ITS TESTS DIDN'T NOTICE" in out)
rc, out = run(weak_commit("Double zero right away", "import unittest\n\nclass D(unittest.TestCase):\n"
                          "    def test_text(self):\n        self.assertEqual('a'.upper(), 'A')\n"), ["--free", "--last", "1"], fake_worker())
check("noise: tests that don't name the changed code aren't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "about other code" in out)
root = weak_commit("Double zero right away")
(root / "test_double_more.py").write_text("import unittest\nfrom calc import double\nimport inspect\n\nclass E(unittest.TestCase):\n"
                                          "    def test_shortcut(self):\n        self.assertIn('if x else 0', inspect.getsource(double))\n")
commit(root, "Pin the zero shortcut (by a person)")
rc, out = run(root, ["--free", "--last", "2"], fake_worker())
check("noise: a gap a later commit closed isn't flagged", "ITS TESTS DIDN'T NOTICE" not in out and "a later test notices" in out)
check("noise filters keep real catches: the plain weak test is still flagged",
      "ITS TESTS DIDN'T NOTICE" in run(weak_commit("Double zero right away"), ["--free", "--last", "1"], fake_worker())[1])

# free_test_command: step 1 uses the faster command, step 2 still uses test_command.
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"free_test_command = {PY} -c \"import sys; sys.exit(3)\"\n")
rc, out = run(root, [], fake_worker())
check("free_test_command: the free pass runs it", "tests already fail" in out)
check("free_test_command: the claim test still runs with the full command", 'FALSE "DONE"' in out)

# When the tests fail on Bite's copy, it says what broke (e.g. a file the project makes only at install time).
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"free_test_command = {PY} -c \"import pkg.version\"\n")
rc, out = run(root, ["--free"], fake_worker())
check("tests that fail on the copy: Bite prints why", "why: ModuleNotFoundError: No module named 'pkg'" in out)

# .NET: Bite finds the test command, and runs one claim test by class name (dotnet test takes no file path).
import bite  # noqa: E402
net = Path(tempfile.mkdtemp())
(net / "src" / "Calc.Tests").mkdir(parents=True)
(net / "src" / "Calc.Tests" / "Calc.Tests.csproj").write_text("<Project/>")
(net / "src" / "Calc").mkdir()
(net / "src" / "Calc" / "Calc.csproj").write_text("<Project/>")
check("dotnet: the one test project is found when there's no solution", bite.guess_test_command(net) == "dotnet test src/Calc.Tests/Calc.Tests.csproj")
(net / "My Game.sln").write_text("")
check("dotnet: a solution is named (quoted when it has a space)", bite.guess_test_command(net) == 'dotnet test "My Game.sln"')
(net / "ProjectSettings").mkdir()
(net / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.1f1\n")
check("Unity: no guess (its tests run inside the editor)", bite.guess_test_command(net) == "")


class GlobCfg:
    test_glob = bite.DEFAULT_TEST_FILES


check("dotnet: C# test files and test projects count as tests",
      bite.is_test_file("sim/Game.Sim.Tests/HeatTests.cs", GlobCfg) and bite.is_test_file("src/Calc.Test/Util.cs", GlobCfg)
      and not bite.is_test_file("sim/Game.Sim/Heat.cs", GlobCfg))


class NetCfg:
    claim_cmd, contain, box_test_cmd = "", "", ""
    test_cmd = 'dotnet test Game.sln --filter "Category!=Slow" -v q'


cmd = recent.claim_command(NetCfg, "tests/Game.Tests/BiteClaimTests.cs")
check("dotnet: claim test picked by --filter, not by file path",
      cmd == 'dotnet test Game.sln -v q --filter "FullyQualifiedName~BiteClaim"')
class GoCfg:
    claim_cmd, contain, box_test_cmd = "", "", ""
    test_cmd = "go test -count=1 ./..."


check("go test: the claim test runs as its package (go refuses ./... next to a file: 'setup failed')",
      [recent.claim_command(GoCfg, r) for r in ("middleware/compress_bite_claim_test.go", "bite_claim_test.go")]
      == ["go test -count=1 ./middleware", "go test -count=1 ./."])
check("dotnet: a C# build error is a load failure, not a finding",
      bite.load_failure("Calc.cs(3,5): error CS0103: The name 'x' does not exist"))

check("dotnet: a test run that ran no tests isn't a pass",
      recent.ran_nothing("dotnet test tests/App.Tests", "Build succeeded.\n  App.Tests -> bin/App.Tests.dll\n")
      and not recent.ran_nothing("dotnet test x.sln", "Passed!  - Failed: 0, Passed: 112, Skipped: 1, Total: 113"))
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"claim_command = {PY} -c \"print('No test matches the given testcase filter')\"\n")
rc, out = run(root, [], fake_worker())
check("dotnet: a filter that matched no test is not a claim that holds",
      "    test didn't load" in out and "    holds" not in out and "FALSE" not in out)

root = make_repo()  # C# names its files BiteClaimTests.cs, not bite_claim
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"claim_command = {PY} -m unittest -q {{file}}\n")
rc, out = run(root, [], fake_worker(name="BiteClaimTests.py"))
check("a C#-style name (BiteClaimTests) counts as the claim test file", 'FALSE "DONE"' in out and "no test written" not in out)

# Git LFS: git archive writes pointer files; Bite's copy gets the real content from the repo's LFS store.
import hashlib  # noqa: E402
root = make_repo()
real = b"\x89PNG real art bytes\n" * 50
oid = hashlib.sha256(real).hexdigest()
ptr = f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(real)}\n".encode()
(root / "art.png").write_bytes(ptr)
(root / "gone.png").write_bytes(ptr.replace(oid.encode(), b"0" * 64))
(root / ".gitattributes").write_text("*.png -text\n")  # as in LFS repos: no line-ending changes (Windows autocrlf)
commit(root, "add art")
store = root / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4]
store.mkdir(parents=True)
(store / oid).write_bytes(real)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    copy = recent.export(root, recent.repo.git(root, "rev-parse", "HEAD"), recent.repo.load_cfg(root))
check("LFS: a pointer file gets its real content in Bite's copy", (copy / "art.png").read_bytes() == real)
check("LFS: a file that can't be fetched stays a pointer and Bite says so",
      (copy / "gone.png").read_bytes() == ptr.replace(oid.encode(), b"0" * 64) and "Git LFS" in buf.getvalue())

# Options: a typo or --help must never fall through to the paid step.
for args, code in ((["--help"], 0), (["--fre"], 2), (["--budget"], 2), (["--last", "5", "--bogus"], 2),
                   (["--last", "abc"], 2), (["--free-checks", "2.5"], 2), (["--suspects", "x"], 2),
                   (["--budget", "lots"], 2)):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = recent.main(args)
    check(f"options: {' '.join(args)} exits {code} before any check runs",
          rc == code and "free check of" not in buf.getvalue() and "Traceback" not in buf.getvalue())
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    recent.main(["--last", "abc"])
check("options: a non-number value gets a one-line message", buf.getvalue().strip() == "Bite: --last needs a whole number, got 'abc'.")
missing = [o for o in sorted(recent.FLAGS | set(recent.VALUED)) if o not in recent.__doc__]
check(f"options: --help lists every option main() accepts (missing: {missing})", not missing)

# First run: a missing test runner is named, with the fix, before any copy is made (not "exit 1" per commit).
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m pytest -q\nallowed_programs = {PY}\n")
real_run = subprocess.run
no_pytest = lambda a, *k, **kw: (subprocess.CompletedProcess(a, 1) if a[1:] == ["-c", "import pytest"]  # noqa: E731
                                 else real_run(a, *k, **kw))
with patch.object(recent.subprocess, "run", no_pytest):
    rc, out = run(root, ["--free"], fake_worker())
check("first run: pytest missing says so and gives the install line, before any check",
      rc == 1 and "pytest isn't installed" in out and "-m pip install pytest" in out and "free check of" not in out)
(root / ".bite.ini").write_text(f"[kit]\ntest_command = no-such-runner-xyz run\nallowed_programs = {PY}\n")
rc, out = run(root, ["--free"], fake_worker())
check("first run: a test command that isn't installed is named", rc == 1 and "can't find 'no-such-runner-xyz'" in out)
with patch.object(recent.shutil, "which", lambda name: None if name == "git" else "x"):
    rc, out = run(root, ["--free"], fake_worker())
check("first run: no git says how to get it, no traceback", rc == 1 and "git isn't installed" in out)

# Report: every run leaves one page that says what was checked and how each commit did.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef neg(x):\n    return -x\n")
commit(root, "Fix <b>neg</b> & friends" + CLAUDE)
rc, out = run(root, ["--free"], fake_worker())
page = (root / "bite_proof" / "report.html").read_text(encoding="utf-8") if rc == 0 else ""
check("report: report.html is written and named at the end of a run", "report.html" in out and "<table>" in page)
check("report: a commit nobody's test guards is shown as such", "No test noticed it was gone" in page)
check("report: the Bite logo sits next to the page title (#89)",
      "<h1><img " in page and "bite-avatar.png" in page.split("</h1>")[0])
note = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if rc == 0 else ""
check("comment: the pull request comment leads with a plain verdict and what to do",
      note.startswith(f"<!-- bite-check -->\n### {recent.CAT} ⚠️ Bite: no test noticed 3 changes") and "**Next:**" in note
      and "<details>" in note and "“Fix &lt;b&gt;neg" in note and "<sub>Commit `" in note)
check("report: commit subjects are escaped, not run as HTML", "Fix &lt;b&gt;neg&lt;/b&gt; &amp; friends" in page)

# Every kind of comment ends the same way: the fold with the same words on how Bite checks, then the link.
c1 = {"sha": "a" * 40, "subject": "one"}
notes = {"worth a look": note}
for name, cs in (("tests check it", [dict(c1, undo="guarded")]), ("couldn't check", [dict(c1, undo="tests fail at this commit")]),
                 ("no code", [])):
    notes[name] = recent.write_comment(root, cs).read_text(encoding="utf-8")
# Each situation gets its own verdict (PR #41: red tests got a calm "nothing here it could check").
c2 = {"sha": "b" * 40, "subject": "two"}
newest_fails = recent.write_comment(root, [dict(c1, undo="tests fail at this commit", why="NameError: x"),
                                           dict(c2, undo="guarded")], newest=c1["sha"]).read_text(encoding="utf-8")
check("comment: tests failing on the newest commit lead with a red verdict and say fix them first",
      f"### {recent.CAT} ❌ Bite: your tests already fail" in newest_fails and "fix them first" in newest_fails and "NameError: x" in newest_fails)
older_fails = recent.write_comment(root, [dict(c1, undo="tests fail at this commit"), dict(c2, undo="guarded")],
                                   newest=c2["sha"]).read_text(encoding="utf-8")
check("comment: tests that failed only on an older commit don't decide the verdict",
      f"### {recent.CAT} ✅" in older_fails and "Bite skipped it" in older_fails and "❌" not in older_fails)
check("comment: tests failing on the newest commit point to how to tell Bite to run them",
      "tell Bite how to run them" in newest_fails and recent.SETUP_LINK in newest_fails)
# A test file that's a plain script (it calls sys.exit when loaded) makes pytest crash with exit 3 (bite-kit did).
with tempfile.TemporaryDirectory() as tmp:
    proj = Path(tmp)
    (proj / "tests").mkdir()
    (proj / "tests" / "test_script.py").write_text("import sys\nsys.exit(0)\n")
    (proj / "crash.ini").write_text(f"[kit]\ntest_command = \"{Path(sys.executable).as_posix()}\" -m pytest -q -p no:cacheprovider\n")
    crashed = bite.run_tests(bite.Config(proj / "crash.ini"), proj)
check(f"tests: pytest crashing on a script-style test file is said in words (got {crashed['why']!r})",
      not crashed["ok"] and crashed["why"].startswith("pytest crashed while loading your tests") and "(exit 3)" in crashed["why"])
check("tests: other runners keep the plain exit code", bite.exit_why("npm test", 3) == "exit 3")
notes["no tests ran"] = recent.write_comment(root, [dict(c1, undo="no tests ran at this commit")], newest=c1["sha"]).read_text(encoding="utf-8")
check("comment: no tests ran is a warning, not a calm dash", f"### {recent.CAT} ⚠️ Bite: no tests found" in notes["no tests ran"])
notes["tests fail"] = newest_fails
check("comment: a commit set aside on purpose says skipped, not couldn't check",
      "Skipped: a tidy-up" in recent.write_comment(root, [dict(c1, undo="not flagged: a tidy-up (no behaviour change meant)")]).read_text(encoding="utf-8"))
# A long commit title is shown whole in the comment, and cut at a word with "…" in the terminal (#71 showed "…the t").
long_title = "Bite checks Bite: an issue for each gap, and a pull request with the test that closes it"
check("comment: a long commit title is shown whole, not cut mid-word",
      f"“{long_title}”" in recent.write_comment(root, [dict(c1, subject=long_title, undo="guarded")]).read_text(encoding="utf-8"))
check(f"terminal: a long commit title is cut at a word, with … (got {recent.short(long_title)!r})",
      recent.short(long_title) == "Bite checks Bite: an issue for each gap, and a pull request with the…"
      and len(recent.short(long_title)) <= 70 and recent.short("short one") == "short one")
with patch.dict(os.environ, {"BITE_PR_COMMITS": "34", "BITE_CHECKED_COMMITS": "20"}):
    big = recent.write_comment(root, [dict(c1, undo="guarded")]).read_text(encoding="utf-8")
check("comment: a pull request with more commits than were checked says so", "newest 20 of this pull request's 34 commits" in big)
broken = make_repo()
(broken / ".bite.ini").write_text("[kit]\ntest_command = no_such_runner_bite run\n")
rc, out = run(broken, ["--free"], fake_worker())
notes["couldn't run"] = (broken / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if (broken / "bite_proof" / "COMMENT.md").is_file() else ""
check("comment: when Bite can't run, the comment says why instead of leaving the last one up",
      rc == 1 and f"### {recent.CAT} ❌ Bite couldn't start" in notes["couldn't run"] and "no_such_runner_bite" in notes["couldn't run"])
plain_root = make_repo()
(plain_root / "calc.py").write_text((plain_root / "calc.py").read_text() + "\n\ndef cube(x):\n    return x ** 3\n")
commit(plain_root, "Add cube" + CLAUDE)
rc, out = run(plain_root, ["--free", "--last", "1"], fake_worker())
check("comment: code with no fix claim says no claim to check, not that no code changed",
      "says it fixes something" in (plain_root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8"))
# The comment names the test that caught each change, not just "a test" (CH: "a test" / "your tests" is vague).
named = make_repo()
(named / "calc.py").write_text((named / "calc.py").read_text().replace("    return x\n", "    return min(x, hi)\n", 1))
(named / "test_high.py").write_text(CLAIM_TEST.replace("class C", "class H"))
commit(named, "Fix clamp at the high end" + CLAUDE)
rc, out = run(named, ["--free", "--last", "1"], fake_worker())
named_note = (named / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if rc == 0 else ""
check("comment: a guarded commit names the test that failed without it",
      "- ✅ The test `test_high` noticed it was gone. If this change breaks later, that test will warn you." in named_note)
check("terminal: the same plain words, naming the test", "✅ noticed by test_high" in out)
# Bite-proof (CH 10-30): only when every change checked had a test that noticed it, the same in all three places.
named_page = (named / "bite_proof" / "report.html").read_text(encoding="utf-8") if rc == 0 else ""
check("bite-proof: a run where a test noticed every change says so, with the badge, in the terminal, report and comment",
      "Bite-proof. Nice work." in out and recent.BADGE in out and "Bite-proof. Nice work." in named_page
      and named_note.startswith(f"<!-- bite-check -->\n### {recent.CAT} ✅ Bite-proof. Nice work.") and recent.BADGE in named_note)
check("bite-proof: never shown when a change had no test, or a claim tested was false",
      "Bite-proof" not in note and "Bite-proof" not in page
      and not recent.bite_proof(["held"], [{"status": "FALSE DONE"}]) and not recent.bite_proof(["held", "none"]))
# --roast changes only the words of the two warnings, the same everywhere; the next step stays.
rc, out = run(root, ["--free", "--roast"], fake_worker())
roast_note = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if rc == 0 else ""
roast_page = (root / "bite_proof" / "report.html").read_text(encoding="utf-8") if rc == 0 else ""
check("roast: the gentle line shows in the terminal, report and comment, with the plain next step",
      all("If this fix wandered off, nothing would notice. A test would." in t and "add a test that fails without it" in t
          for t in (out, roast_note, roast_page)) and "No test noticed it was gone" not in roast_note)
recent.ROAST[0] = True
odd = recent.say({"sha": "c" * 40, "undo": "TEST GUARDS NOTHING", "test_code": ["test_x"]})[2]
recent.ROAST[0] = False
check("roast: its own tests that miss the change get the gentle line too",
      odd == "⚠️ These tests (`test_x`) are looking the other way. **Next:** make one fail without the change.")
rc, out = run(root, ["--free"], fake_worker())
check("roast: off again on the next plain run", "No test noticed it was gone" in out and "wandered off" not in out)
check("caught_by: reads failing test names from pytest, unittest, go and cargo output",
      recent.caught_by("FAILED tests/t.py::TestA::test_one - assert 1 == 2\nFAILED tests/t.py::test_two\n") == "`test_one` and 1 more"
      and recent.caught_by("FAIL: test_x (t.T.test_x)\n") == "`test_x`" and recent.caught_by("--- FAIL: TestGo (0.00s)") == "`TestGo`"
      and recent.caught_by("test parse::empty ... FAILED") == "`parse::empty`" and recent.caught_by("all good") == "")
rc, out = run(root, ["--free", "--last", "0"], fake_worker())
notes["nothing in the pull request"] = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if rc == 0 else ""
how = "Bite asks one question about each change: if it disappeared, would any test notice? It takes the change out, runs your tests, and puts it back."
check("comment: every kind starts with the same cat logo, the picture in assets/", len(notes) >= 7
      and all(n.split("\n")[1].startswith(f"### {recent.CAT} ") for n in notes.values())
      and (KIT / "assets" / "bite-avatar.png").is_file())
check("comment: every kind (worth a look, tests check it, couldn't check, no code) ends with the same words and link",
      all(n.startswith(f"<!-- bite-check -->\n### {recent.CAT} ") and how in n
          and n.endswith("[What is Bite?](https://github.com/connabyss/bite)\n\n</details>\n") for n in notes.values()))
check("comment: a run with nothing to check still writes the comment the GitHub Action posts",
      "No commit in this pull request changed code" in notes["nothing in the pull request"])

# A pull request that merged its base back in ("Update branch"): the base's newer commits must not crowd out the
# pull request's own. GitHub checks out a merge of the pull request into the base, so HEAD is a merge too.
root = make_repo()
sh(root, "git", "checkout", "-q", "-b", "pr")
dated = lambda d: {**os.environ, "GIT_AUTHOR_DATE": d, "GIT_COMMITTER_DATE": d}  # noqa: E731
def commit_at(msg, d, *extra):
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", *extra, "-m", msg],
                   cwd=root, check=True, capture_output=True, env=dated(d))
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef half(x):\n    return x / 2\n")
commit_at("Add half", "2030-01-01T10:00:00")
sh(root, "git", "checkout", "-q", "-")
(root / "notes.txt").write_text("ci\n")
commit_at("CI: run on Intel Macs", "2030-01-01T11:00:00")
base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
sh(root, "git", "checkout", "-q", "pr")
subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-edit", base],
               cwd=root, check=True, capture_output=True, env=dated("2030-01-01T12:00:00"))
pr_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "checkout", "-q", "--detach", base],
               cwd=root, check=True, capture_output=True)
subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "--no-edit", pr_head],
               cwd=root, check=True, capture_output=True, env=dated("2030-01-01T13:00:00"))
got = [c["subject"] for c in recent.commits(root, 1, base)]
check(f"pull request: after merging its base back in, it checks its own commit, not the base's newer one (got {got})",
      got == ["Add half"])
rc, out = run(root, ["--free", "--since", base, "--last", "1", "--free-checks", "1"], fake_worker())
check("pull request: the whole free pass with --since checks the pull request's code commit",
      "Nothing to check" not in out and "1 commits changed code" in out)
rc, out = run(root, ["--free", "--since", "no-such-branch"], fake_worker())
check("pull request: an unknown --since is named, not taken as 'nothing to check'",
      rc == 1 and "isn't a commit or branch" in out)
check("action.yml: the pull request check looks only at the pull request's own commits (--since the base)",
      '--since "$BASE"' in (KIT / "action.yml").read_text(encoding="utf-8"))

# bite --demo: a made-up project where one fix has a test and one doesn't, so a first run shows both results.
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = recent.main(["--demo"])
out = buf.getvalue()
check("--demo: the fix with a test is noticed and the fix without one is flagged",
      rc == 0 and "noticed by test_discount_never_below_zero" in out
      and 'NO TEST NOTICED: ' in out and "Fix totals showing long decimals" in out.split("NO TEST NOTICED: ", 1)[-1])
shown = [ln.rstrip() for ln in out.splitlines() if "✅ noticed" in ln or "⚠️ NO TEST NOTICED  " in ln]
readme = (KIT / "README.md").read_text(encoding="utf-8")
check(f"README.md: shows bite --demo and the same two lines a demo run prints (got {shown})",
      "bite --demo" in readme and len(shown) == 2 and all(ln in readme for ln in shown))

# Docs: the key rule is stated where a reader looks first.
for doc in ("AGENTS.md", "README.md"):
    t = (KIT / doc).read_text(encoding="utf-8")
    check(f"{doc}: says Bite needs an API key and never uses a Claude login, with the SDK rule's link",
          "never uses" in t and "login" in t and "https://code.claude.com/docs/en/agent-sdk/overview" in t)
check("CLAUDE.md: loads AGENTS.md, so Claude reads the same instructions as every other coding AI",
      "@AGENTS.md" in (KIT / "CLAUDE.md").read_text(encoding="utf-8"))

check("action.yml: the pull request check runs the free pass and the README shows how to add it",
      "bite --free" in (KIT / "action.yml").read_text(encoding="utf-8")
      and "uses: connabyss/bite@" in (KIT / "README.md").read_text(encoding="utf-8"))

print(f"\n{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
