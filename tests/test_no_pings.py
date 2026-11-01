"""A commit title that names someone ("thanks @alice", "Bump @types/node") must not notify them when Bite's pull
request comment quotes it (found by the overnight stress test, 2026-11-01)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402


def test_a_quoted_title_pings_nobody(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subject = "Fix rounding, thanks @alice (Bump @types/node)"
    cs = [{"sha": "a" * 40, "subject": subject, "undo": "unguarded", "code": ["shop.py"]},
          {"sha": "b" * 40, "subject": "Fix totals", "undo": "undone since", "code": ["x.py"],
           "undone_by": {"sha": "c" * 40, "subject": "Simplify, cc @bob"}}]
    text = recent.write_comment(tmp_path, cs, newest="a" * 40).read_text(encoding="utf-8")
    for name in ("@alice", "@types", "@bob"):
        assert name not in text  # GitHub would notify them
        assert name.replace("@", "@⁠") in text  # still there to read


def test_code_and_addresses_are_left_alone():
    lines = ["Commit “mail me at a@b.org”", "`@pytest.fixture`", "~~~~python", "@pytest.fixture", "def x(): pass",
             "~~~~", "thanks @carol"]
    out = recent.no_pings(lines)
    assert out[:6] == lines[:6] and out[6] == "thanks @⁠carol"
