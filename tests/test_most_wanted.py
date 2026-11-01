"""Most wanted: when several changes have no test, Bite names the one test to write first, and why."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402


def c(sha, undo="unguarded", subject="Tidy x", **kw):
    return {"sha": sha * 40, "subject": subject, "undo": undo, "body": "", **kw}


def test_picks_undone_then_serious_then_claim_then_smallest():
    small, big = c("a", lines=3), c("b", lines=90)
    claim = c("c", subject="Fix the totals", claims=True, lines=50)
    serious = c("d", subject="Fix login accepting any token", claims=True, serious=True, lines=80)
    back = c("e", undo="undone since", subject="Fix the cache")
    held = c("f", undo="guarded", caught="`test_x`")
    assert recent.most_wanted([held, big, small])[0] is small
    assert "smallest" in recent.most_wanted([big, small])[1]
    assert recent.most_wanted([small, claim])[0] is claim
    pick, why = recent.most_wanted([small, claim, serious])
    assert pick is serious and "about login" in why
    assert recent.most_wanted([small, claim, serious, back])[0] is back
    assert recent.most_wanted([held]) is None


def test_trailers_dont_make_it_serious_words():
    w = c("d", subject="Fix the thing", claims=True, serious=True, body="Co-Authored-By: someone")
    assert "about what matters most" in recent.most_wanted([w, c("a")])[1]  # not "about authored"


def test_shown_only_when_there_is_a_choice():
    root = Path(tempfile.mkdtemp())
    one = [c("a", subject="Fix x", claims=True), c("f", undo="guarded", caught="`test_x`")]
    assert "Most wanted" not in recent.write_html(root, one, [], 1.0).read_text(encoding="utf-8")
    two = one + [c("b", subject="Fix login accepting any token", claims=True, serious=True)]
    page = recent.write_html(root, two, [], 1.0).read_text(encoding="utf-8")
    assert "Most wanted" in page and "bbbbbbbb</code> Fix login accepting any token" in page
