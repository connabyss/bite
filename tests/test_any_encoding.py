"""Source files that aren't UTF-8 (Latin-1, Windows-1252: common in older Java, C# and Python code), found by the
overnight stress test (2026-11-01). Bite read them with "replace" and wrote them back as UTF-8, so a copy with one
piece taken out also changed every accented character: a test that reads one failed, and an untested piece of the
fix looked noticed. Each test here failed before its fix. No key, no network."""

import difflib
import json
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
OLD = ('# -*- coding: latin-1 -*-\n\ndef greet(name):\n    return "caf\xe9 " + name\n\n\ndef total(xs):\n'
       '    return sum(xs)\n\n\ndef label(x):\n    return str(x)\n').encode("latin-1")
NEW = OLD.replace(b"return sum(xs)", b"return round(sum(xs), 2)").replace(b"return str(x)", b"return str(x).strip()")
TESTS = ('from shop import greet, total\n\n\ndef test_greet():\n    assert greet("a") == "caf\\xe9 a"\n\n\n'
         'def test_total():\n    assert total([1, 2]) == 3\n')


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def test_an_untested_piece_in_a_latin1_file_is_still_found(tmp_path):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "shop.py").write_bytes(OLD)
    (root / "tests" / "test_shop.py").write_text(TESTS)
    commit(root, "start")
    (root / "shop.py").write_bytes(NEW)
    with open(root / "tests" / "test_shop.py", "a") as f:
        f.write("\n\ndef test_total_rounds():\n    assert total([0.1, 0.2]) == 0.3\n")
    commit(root, "Fix total rounding and label spaces")
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json"], cwd=root, capture_output=True, text=True,
                         timeout=300)
    c = json.loads(out.stdout)["commits"][0]
    assert c["label"] == "PART NOT NOTICED" and "label()" in c["detail"], c
    sha = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    kept = (root / "bite_proof" / f"{sha[:8]}_part_shop.py").read_bytes()
    assert b"caf\xe9 " in kept and kept == NEW.replace(b"return str(x).strip()", b"return str(x)")


def test_a_piece_taken_out_keeps_every_other_byte():
    a = OLD.decode("utf-8", "surrogateescape").splitlines(keepends=True)
    b = NEW.decode("utf-8", "surrogateescape").splitlines(keepends=True)
    ops = [op for op in difflib.SequenceMatcher(None, a, b).get_opcodes() if op[0] != "equal"]
    assert recent.without(a, b, ops) == OLD
    assert recent.without(a, b, []) == NEW


def test_rust_and_doc_copies_keep_every_byte():
    old = b'// caf\xe9\n/// Adds.\npub fn add(a: i32) -> i32 { a }\n'
    new = (b'// caf\xe9\n/// Adds one.\n///\n/// ```\n/// assert_eq!(add(1), 2);\n/// ```\npub fn add(a: i32) -> i32 { a + 1 }\n'
           b'\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn one() { assert_eq!(super::add(1), 2); }\n}\n')
    assert b"// caf\xe9\n" in recent.keep_docs(old, new)
    assert recent.keep_rust_tests(old, new).startswith(b"// caf\xe9\n")


def test_a_doctest_in_a_latin1_file_only_notices_what_it_checks(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider --doctest-modules\n")
    greet = '# -*- coding: latin-1 -*-\n\ndef greet(name):\n    return "caf\xe9 " + name\n'
    (root / "test_shop.py").write_text('from shop import greet\n\n\ndef test_greet():\n    assert greet("a") == "caf\\xe9 a"\n')
    (root / "shop.py").write_bytes((greet + "\n\ndef total(xs):\n    return sum(xs)\n").encode("latin-1"))
    commit(root, "start")
    fixed = '\n\ndef total(xs):\n    """\n    >>> total([1, 2])\n    3\n    """\n    return round(sum(xs), 2)\n'
    (root / "shop.py").write_bytes((greet + fixed).encode("latin-1"))
    commit(root, "Fix total rounding")
    out = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json"], cwd=root, capture_output=True, text=True,
                         timeout=300)
    c = json.loads(out.stdout)["commits"][0]
    assert c["result"] == "no_test_noticed", c
