"""A big generated file (a 60,000-line bundle.js) found by the overnight stress test (2026-11-01): a fix that touched
300 places in it took Bite almost ten minutes to split into pieces, because it read the whole file a character at
a time for each of the 300 pieces. Each test here failed before its fix. No key, no network."""

import subprocess
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import bite  # noqa: E402
import recent  # noqa: E402


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def test_reading_a_big_file_skips_ordinary_text_in_one_go():
    text = ("var total = price * count + tax; // add tax\n" * 120000)  # about 5 MB
    start = time.perf_counter()
    lines = bite.code_lines(text, ".js")
    took = time.perf_counter() - start
    assert lines[0] == "var total = price * count + tax; " and len(lines) == 120001
    assert took < 1.5, f"reading 5 MB of code took {took:.1f}s"


def test_reading_fast_still_knows_strings_and_comments():
    assert bite.code_lines('a = "#fff"  # colour\nb = 1\n', ".py") == ['a = "#fff"  ', "b = 1", ""]
    assert bite.code_lines("s = `http://x\n// still text`; // gone\n", ".js") == ["s = `http://x", "// still text`; ", ""]
    assert bite.code_lines('x = "a\\"//b" // c\n', ".js") == ['x = "a\\"//b" ', ""]
    assert bite.code_lines("p := `C:\\`; // c\n", ".go") == ["p := `C:\\`; ", ""]
    assert bite.code_lines("y = 7 // 2\n", ".py") == ["y = 7 // 2", ""]


def test_a_change_in_many_functions_stops_counting_pieces_early(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q")
    funcs = [f"function f{i}(x) {{\n  return x + {i};\n}}\n" for i in range(40)]
    (root / "bundle.js").write_text("\n".join(funcs))
    commit(root, "start")
    (root / "bundle.js").write_text("\n".join(f.replace("x + ", "x - ") for f in funcs))
    commit(root, "Fix the sign in every function")
    sha = git(root, "rev-parse", "HEAD").strip()
    c = {"sha": sha, "code": ["bundle.js"]}
    assert len(recent.parts(root, c)) == 40

    calls = []
    real = recent.same_code
    monkeypatch.setattr(recent, "same_code", lambda *a, **k: calls.append(1) or real(*a, **k))
    ps = recent.parts(root, c, most=recent.MAX_PARTS)
    assert len(ps) == recent.MAX_PARTS + 1 and len(calls) == recent.MAX_PARTS + 1

    # The piece check asks for no more than it can use, and still finds the commit too big to split.
    calls.clear()
    monkeypatch.setattr(recent, "PART_RUNS", [6])
    monkeypatch.setattr(recent, "QUICK", [False])
    assert recent.unnoticed_part(root, c, tmp_path / "unused", None) == []
    assert len(calls) == recent.MAX_PARTS + 1
