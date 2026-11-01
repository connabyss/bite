"""The Bite score: of the changes Bite could check, how many a test noticed, with a badge that can follow it."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402


def c(undo, **kw):
    return {"sha": "a" * 40, "subject": "Fix x", "undo": undo, **kw}


def test_only_checkable_changes_count():
    # noticed, two gaps, a comeback; a skip, failing tests and "no tests found" don't count either way
    kinds = ["held", "gap", "odd", "back", "skip", "fail", "none"]
    assert recent.score(kinds) == (1, 4)
    assert recent.score(["skip", "fail"]) == (0, 0)


def test_badge_colour_and_url():
    assert recent.score_color(3, 3) == "brightgreen" and recent.score_color(3, 4) == "yellowgreen"
    assert recent.score_color(1, 2) == "yellow" and recent.score_color(1, 4) == "orange" and recent.score_color(0, 4) == "red"
    b = recent.score_badge(7, 9)
    # the slash is encoded, or shields.io would read it as a new part of the path
    assert "img.shields.io/badge/Bite%20score-7%2F9%20noticed-yellowgreen)" in b and b.startswith("[![Bite score: 7 of 9")


def test_results_and_badge_json_carry_the_score():
    cs = [c("guarded", caught="`test_x`"), c("unguarded"), c("not flagged: a tidy-up commit")]
    r = recent.results(cs)
    assert r["score"]["noticed"] == 1 and r["score"]["out_of"] == 2 and "1%2F2" in r["score"]["badge"]
    assert "score" not in recent.results([c("not flagged: a tidy-up commit")])
    assert "score" not in recent.results(cs, error="no tests")
    root = Path(tempfile.mkdtemp())
    recent.write_results(root, cs)
    badge = root / "bite_proof" / "badge.json"
    assert json.loads(badge.read_text(encoding="utf-8")) == {"schemaVersion": 1, "label": "Bite score",
                                                             "message": "1/2 noticed", "color": "yellow"}
    recent.write_results(root, [c("not flagged: a tidy-up commit")])  # nothing counted: no stale badge left behind
    assert not badge.exists()


def test_report_and_comment_show_the_score():
    root = Path(tempfile.mkdtemp())
    cs = [c("guarded", caught="`test_x`"), c("unguarded")]
    page = recent.write_html(root, cs, [], 1.0).read_text(encoding="utf-8")
    assert "Bite score: 1 of 2" in page and 'aria-label="Bite score 1 of 2"' in page
    comment = recent.write_comment(root, cs).read_text(encoding="utf-8")
    assert "Bite score for these commits: **1/2**" in comment
    # all noticed: the comment already says Bite-proof, so no score line there
    assert "Bite score for these" not in recent.write_comment(root, [c("guarded", caught="`test_x`")]).read_text(encoding="utf-8")
