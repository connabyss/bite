"""Tricks that once fooled Bite (see TRICKS.md): each test here failed before the fix it guards.
No key, no network: tiny repos made on the spot, and Bite's own --json output."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
SHOP = "def total(prices):\n    return sum(prices)\n\n\ndef label(name):\n    return name.title()\n"
ROUNDED = SHOP.replace("return sum(prices)", "return round(sum(prices), 2)")
LABEL_TEST = "from shop import label\n\n\ndef test_label():\n    assert label('tea') == 'Tea'\n"


def git(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)


def write(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text))


def make(tmp_path, files=None):
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q")
    write(root, {".bite.ini": f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n",
                 "shop.py": SHOP, "tests/test_shop.py": LABEL_TEST, **(files or {})})
    commit(root, "start")
    return root


def bite(root, last=1):
    p = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json", "--last", str(last)], cwd=root,
                       capture_output=True, text=True, timeout=600)
    return json.loads(p.stdout)


def only(root, last=1):
    rows = bite(root, last)["commits"]
    assert len(rows) == 1, rows
    return rows[0]


# ---- words in the commit message --------------------------------------------------

def test_fix_words_outweigh_tidy_and_speed_words():
    for subject in ("chore: fix login crash in total", "Refactor total and fix rounding bug",
                    "Make total faster and correct its rounding"):
        assert recent.skip_reason(subject, subject, "") == "", subject
    # Without a fix word they're still a tidy-up and a speed-up.
    assert "tidy-up" in recent.skip_reason("refactor: split total", "refactor: split total", "")
    assert "speed-up" in recent.skip_reason("perf: faster total", "perf: faster total", "")


def test_naming_an_os_or_python_skips_only_code_that_checks_for_one():
    other = "macOS" if recent.HERE != "mac" else "Windows"
    said = f"Fix total rounding (reported on {other})"
    assert recent.skip_reason(said, said, "shop.py\ndef total(p):\n    return round(sum(p), 2)\n") == ""
    assert "built for" in recent.skip_reason(said, said, "shop.py\nimport sys\nif sys.platform == 'darwin':\n    pass\n")
    other_py = 8 if sys.version_info[1] != 8 else 9
    said = f"Fix total rounding, first seen on Python 3.{other_py}"
    assert recent.skip_reason(said, said, "shop.py\ndef total(p):\n    return round(sum(p), 2)\n") == ""
    assert "built for Python" in recent.skip_reason(said, said, "shop.py\nimport sys\nif sys.version_info < (3, 9):\n    pass\n")


def test_a_revert_does_not_claim_the_fix_it_quotes(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "revert", "--no-edit", "HEAD")
    c = recent.commits(root, 1)[0]
    recent.files_of(root, c, recent.repo.load_cfg(root))
    assert c["subject"].startswith('Revert "Fix') and not c["claims"]


# ---- code that looks like a comment ------------------------------------------------

def test_a_hash_or_slashes_inside_a_long_string_is_code():
    page = 'STYLE = """\nbody {{ color: #{} }}\n"""\n'
    assert not recent.same_code(page.format("000").encode(), page.format("fff").encode(), ".py")
    api = "const U = `\n  http://{}.example.com\n`;\n"
    assert not recent.same_code(api.format("old").encode(), api.format("new").encode(), ".js")
    # Real comments are still not code.
    assert recent.same_code(b"x = 1  # one\n", b"x = 1  # uno\n", ".py")
    assert recent.same_code(b"const x = 1; // one\n", b"const x = 1; // uno\n", ".js")


def test_docstrings_and_hints_count_when_the_file_reads_them():
    cli = '"""usage: cli --{}"""\n\n\ndef flag():\n    return __doc__.split()[-1]\n'
    assert not recent.same_code(cli.format("colour").encode(), cli.format("color").encode(), ".py")
    conv = "import typing\n\n\ndef parse(x: {}):\n    return typing.get_type_hints(parse)['x'](x)\n"
    assert not recent.same_code(conv.format("int").encode(), conv.format("float").encode(), ".py")
    # A file that doesn't read them: still only docs and hints.
    plain = '"""{}"""\n\n\ndef f(x: {}):\n    return x\n'
    assert recent.same_code(plain.format("Old.", "int").encode(), plain.format("New.", "float").encode(), ".py")


# ---- test runs that prove nothing --------------------------------------------------

def test_a_run_where_every_test_skipped_ran_nothing():
    assert recent.all_skipped("ss    [100%]\n2 skipped in 0.01s\n")
    assert recent.all_skipped("Ran 2 tests in 0.000s\n\nOK (skipped=2)\n")
    assert recent.all_skipped("Tests:       2 skipped, 2 total\n")
    assert recent.all_skipped("# tests 2\n# skipped 2\n")
    assert recent.ran_nothing("mvn test", "Tests run: 3, Failures: 0, Errors: 0, Skipped: 3\n")
    assert not recent.all_skipped("1 passed, 1 skipped in 0.01s\n")
    assert not recent.all_skipped("Ran 2 tests in 0.000s\n\nOK (skipped=1)\n")
    assert not recent.ran_nothing("mvn test", "Tests run: 3, Failures: 0, Errors: 0, Skipped: 1\n")


def test_every_test_skipped_is_no_tests_not_a_gap(tmp_path):
    root = make(tmp_path, {"tests/test_shop.py": "import pytest\n\npytestmark = pytest.mark.skip('off')\n\n\ndef test_a():\n    pass\n"})
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    assert only(root)["result"] == "no_tests"


def test_a_test_that_fails_only_once_does_not_count_as_noticing(tmp_path):
    # Fails on the second run in this copy (the first run with the fix taken out), passes on every other.
    flaky = ("from pathlib import Path\n\n\ndef test_sometimes():\n    f = Path(__file__).with_name('runs.txt')\n"
             "    n = int(f.read_text()) + 1 if f.exists() else 1\n    f.write_text(str(n))\n    assert n != 2\n")
    root = make(tmp_path, {"tests/test_flaky.py": flaky})
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    r = only(root)
    assert r["result"] == "no_test_noticed" and "fails now and then" in r["detail"], r


# ---- a tested piece vouching for an untested one -----------------------------------

def test_a_moved_file_keeps_its_new_name_when_the_change_comes_out(tmp_path):
    root = make(tmp_path)
    git(root, "mv", "shop.py", "store.py")
    write(root, {"store.py": ROUNDED, "tests/test_shop.py": LABEL_TEST.replace("from shop", "from store")})
    commit(root, "Fix total rounding and move shop.py to store.py")
    c = recent.commits(root, 1)[0]
    recent.files_of(root, c, recent.repo.load_cfg(root))
    assert c["code"] == ["store.py"] and c["moved"] == {"store.py": "shop.py"}
    assert only(root)["result"] != "noticed"  # the tests only crashed on the missing new name before


def test_a_tested_change_does_not_vouch_for_an_untested_one(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix total rounding")
    r = only(root)
    assert r["label"] == "PART NOT NOTICED" and "total() in shop.py" in r["detail"] and "label()" not in r["detail"], r


def test_a_test_that_only_calls_the_new_helper_does_not_vouch_for_the_fix(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": "def cents(x):\n    return round(x, 2)\n\n\n" + SHOP.replace("sum(prices)", "cents(sum(prices))"),
                 "tests/test_cents.py": "from shop import cents\n\n\ndef test_cents():\n    cents(1.234)\n"})
    commit(root, "Fix total rounding")
    r = only(root)
    assert r["label"] == "PART NOT NOTICED" and "total() in shop.py" in r["detail"], r


def test_every_piece_tested_is_still_noticed(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")
                 + "\n\ndef test_total():\n    from shop import total\n    assert total([0.1, 0.2]) == 0.3\n"})
    commit(root, "Fix total rounding and labels")
    assert only(root)["result"] == "noticed"


def test_pieces_that_only_count_together_are_still_noticed(tmp_path):
    # Either check alone keeps the test passing; only both out together lets the negative through.
    root = make(tmp_path)
    write(root, {"shop.py": SHOP.replace("return sum(prices)", "return max(0, sum(prices))")
                 + "\n\ndef pay(prices):\n    return max(0, total(prices))\n",
                 "tests/test_pay.py": "from shop import pay, total\n\n\ndef test_pay():\n    assert pay([-5]) == 0\n"})
    commit(root, "add pay")
    write(root, {"shop.py": SHOP + "\n\ndef pay(prices):\n    return total(prices)\n"})
    commit(root, "start over")  # (the test now fails here; the next commit puts both checks back)
    write(root, {"shop.py": SHOP.replace("return sum(prices)", "return max(0, sum(prices))")
                 + "\n\ndef pay(prices):\n    return max(0, total(prices))\n"})
    commit(root, "Fix negative payments")
    assert only(root)["result"] == "noticed"


def test_bite_ask_and_the_free_report_name_the_part(tmp_path):
    import ask
    _, label, why = ask.verdict({"undo": "unguarded: part", "part": "`total()` in shop.py"})
    assert label.endswith("PART NOT NOTICED") and "total() in shop.py" in why
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix total rounding")
    only(root)
    report = (root / "bite_proof" / "FREE_REPORT.md").read_text(encoding="utf-8")
    kept = next((root / "bite_proof").glob("*_part_shop.py")).read_text()
    assert "_part_shop.py shop.py" in report and "return sum(prices)" in kept and "strip()" in kept


def test_a_piece_that_only_changes_a_docstring_is_not_named(tmp_path):
    # The file prints its docstring as help, so the docstring counts as code for the whole commit; but a commit that
    # also changes tested code isn't flagged just because nothing tests the help text.
    cli = '"""usage: shop {}"""\n\n\ndef helptext():\n    return __doc__\n\n\n' + SHOP
    root = make(tmp_path, {"shop.py": cli.format("total")})
    write(root, {"shop.py": cli.format("total|label").replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix labels with spaces")
    assert only(root)["result"] == "noticed"


TOTAL_TEST = "from shop import total\n\n\ndef test_total():\n    assert total([0.1, 0.2]) == 0.3\n"


def test_a_fix_whose_test_was_deleted_later_is_not_called_guarded(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED, "tests/test_total.py": TOTAL_TEST})
    commit(root, "Fix total rounding")
    (root / "tests" / "test_total.py").unlink()
    commit(root, "Remove slow test")
    r = [x for x in bite(root, 2)["commits"] if x["subject"] == "Fix total rounding"][0]
    assert r["result"] == "no_test_noticed" and r["label"] == "ITS TEST IS GONE" and "tests/test_total.py" in r["detail"], r
    import ask
    _, label, why = ask.verdict({"undo": "guard gone since", "gone": ["tests/test_total.py"]})
    assert label.endswith("ITS TEST IS GONE") and "tests/test_total.py" in why


def test_a_deleted_test_file_with_another_test_still_guarding_is_noticed(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED, "tests/test_total.py": TOTAL_TEST})
    commit(root, "Fix total rounding")
    (root / "tests" / "test_total.py").rename(root / "tests" / "test_money.py")
    commit(root, "Move the total test")
    r = [x for x in bite(root, 2)["commits"] if x["subject"] == "Fix total rounding"][0]
    assert r["result"] == "noticed", r


def test_a_piece_a_later_test_notices_is_not_named(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix total rounding")
    write(root, {"tests/test_total.py": TOTAL_TEST})
    commit(root, "Test the rounding")
    assert only(root, 2)["result"] == "noticed"


def test_a_deleted_test_is_not_called_gone_when_bite_cant_tell(tmp_path):
    # Today's code moved on (the fix no longer comes out cleanly), so Bite can't check today: it keeps "noticed".
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED, "tests/test_total.py": TOTAL_TEST})
    commit(root, "Fix total rounding")
    (root / "tests" / "test_total.py").unlink()
    write(root, {"shop.py": ROUNDED.replace("round(sum(prices), 2)", "round(sum(prices), 2) or 0")})
    commit(root, "Remove slow test and tidy total")
    r = [x for x in bite(root, 2)["commits"] if x["subject"] == "Fix total rounding"][0]
    assert r["result"] == "noticed", r


def test_today_takes_out_only_the_piece_not_the_whole_change(tmp_path):
    # With a later commit on top, Bite checks the unnoticed piece on today's code too. Taking the whole change out
    # there would let test_label vouch for total() again.
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix total rounding")
    write(root, {"README.md": "shop\n"})
    commit(root, "Add a readme")
    r = only(root, 2)
    assert r["label"] == "PART NOT NOTICED" and "total() in shop.py" in r["detail"], r


def test_two_unnoticed_pieces_in_one_file_come_out_together(tmp_path):
    root = make(tmp_path, {"shop.py": SHOP + "\n\ndef tax(x):\n    return x\n"})
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()") + "\n\ndef tax(x):\n    return x * 1.2\n",
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix total rounding and tax")
    c = recent.commits(root, 1)[0]
    recent.files_of(root, c, recent.repo.load_cfg(root))
    ps = [p for p in recent.parts(root, c) if p[1] in ("total", "tax")]
    recent.set_part(c, ps)
    both = c["part_undo"]["shop.py"].decode()
    assert "return sum(prices)" in both and "return x\n" in both and "strip()" in both
    r = only(root)
    assert "total() in shop.py" in r["detail"] and "tax() in shop.py" in r["detail"], r


def bundled(tmp_path):
    root = make(tmp_path)
    write(root, {"shop.py": ROUNDED.replace("name.title()", "name.strip().title()"),
                 "tests/test_shop.py": LABEL_TEST.replace("label('tea')", "label(' tea ')")})
    commit(root, "Fix total rounding")
    return root


def run_with(root, *extra):
    p = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json", "--last", "1", *extra], cwd=root,
                       capture_output=True, text=True, timeout=600)
    return json.loads(p.stdout)["commits"][0], p.stderr


def test_quick_skips_the_piece_check(tmp_path):
    r, _ = run_with(bundled(tmp_path), "--quick")
    assert r["result"] == "noticed", r


def test_the_piece_check_keeps_to_its_run_budget(tmp_path):
    root = bundled(tmp_path)
    r, err = run_with(root, "--part-runs", "1")  # the commit has 2 pieces: not enough runs left to split it
    assert r["result"] == "noticed" and "weren't checked piece by piece" in err, (r, err)
    r, _ = run_with(root, "--part-runs", "2")
    assert r["label"] == "PART NOT NOTICED", r


def test_quick_skips_the_flaky_rerun_and_the_deleted_test_check(tmp_path):
    flaky = ("from pathlib import Path\n\n\ndef test_sometimes():\n    f = Path(__file__).with_name('runs.txt')\n"
             "    n = int(f.read_text()) + 1 if f.exists() else 1\n    f.write_text(str(n))\n    assert n != 2\n")
    root = make(tmp_path / "a", {"tests/test_flaky.py": flaky})
    write(root, {"shop.py": ROUNDED})
    commit(root, "Fix total rounding")
    assert run_with(root, "--quick")[0]["result"] == "noticed"  # one failure is taken at its word
    root = make(tmp_path / "b")
    write(root, {"shop.py": ROUNDED, "tests/test_total.py": TOTAL_TEST})
    commit(root, "Fix total rounding")
    (root / "tests" / "test_total.py").unlink()
    commit(root, "Remove slow test")
    p = subprocess.run([PY, str(KIT / "recent.py"), "--free", "--json", "--last", "2", "--quick"], cwd=root,
                       capture_output=True, text=True, timeout=600)
    r = [x for x in json.loads(p.stdout)["commits"] if x["subject"] == "Fix total rounding"][0]
    assert r["result"] == "noticed", r
