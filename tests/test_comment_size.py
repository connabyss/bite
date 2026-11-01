"""GitHub refuses a pull request comment over 65,536 characters, and then the Action posts nothing at all. Found by
the overnight stress test (2026-11-01): a 200,000-character commit title made a 201 KB COMMENT.md, and a few long
tests written by --write-tests can pass the limit too. Each test here failed before its fix. No key, no network."""

import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402


def gap(i, **kw):
    return {"sha": f"{i:x}" * 40, "subject": f"Fix thing {i}", "undo": "unguarded", "code": ["shop.py"], **kw}


def written(i, lines):
    test = "def test_it():\n" + "    assert total([0.1, 0.2]) == 0.3  # check the rounding\n" * lines
    return gap(i, guard={"status": "WRITTEN", "test_file": f"tests/test_bite_claim_{i}.py", "run": "pytest", "test": test})


def comment(cs):
    root = Path(tempfile.mkdtemp())
    return recent.write_comment(root, cs).read_text(encoding="utf-8")


def test_a_huge_commit_title_is_cut():
    body = comment([gap(1, subject="Fix label " + "very long " * 20000)])
    assert len(body) <= 65536 and "very long very long" in body and "…”" in body


def test_long_written_tests_leave_their_code_out_until_the_comment_fits():
    cs = [written(i, 400) for i in range(1, 6)]  # five tests of 400 lines: about 130,000 characters
    body = comment(cs)
    assert len(body) <= 65536
    assert "assert total([0.1, 0.2]) == 0.3" in body  # the first tests are still shown whole
    assert "bite_proof/missing_tests/tests/test_bite_claim_5.py" in body  # the last one says where it is
    assert body.rstrip().endswith("</details>")  # nothing cut mid-way


def test_a_short_comment_is_left_as_it_was():
    body = comment([written(1, 3)])
    assert "missing_tests" not in body.split("Artifacts")[0] and body.count("assert total") == 3
