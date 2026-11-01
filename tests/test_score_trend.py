"""The score's trend: Bite remembers each run's score and says whether it went up, down, or stayed Bite-proof."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402


def test_up_down_same_and_streak():
    root = Path(tempfile.mkdtemp())
    first = recent.remember_score(root, 1, 4, "a")
    assert first == {"before": None, "streak": 0} and recent.trend_words(1, 4, first) == ""
    t = recent.remember_score(root, 3, 4, "b")
    assert recent.trend_words(3, 4, t) == "up from 1/4 last run"
    t = recent.remember_score(root, 2, 4, "c")
    assert recent.trend_words(2, 4, t) == "down from 3/4 last run"
    t = recent.remember_score(root, 4, 8, "d")
    assert recent.trend_words(4, 8, t) == "last run: 2/4"  # same share, different size
    t = recent.remember_score(root, 4, 8, "e")
    assert recent.trend_words(4, 8, t) == "same as last run"
    recent.remember_score(root, 5, 5, "f")
    t = recent.remember_score(root, 6, 6, "g")
    assert t["streak"] == 2 and recent.trend_words(6, 6, t) == "Bite-proof 2 runs in a row"


def test_rerun_at_the_same_commit_replaces_it():
    root = Path(tempfile.mkdtemp())
    recent.remember_score(root, 1, 4, "a")
    recent.remember_score(root, 2, 2, "b")
    t = recent.remember_score(root, 2, 2, "b")  # the same commit again: no longer streak, still compared with a
    assert t == {"before": (1, 4), "streak": 1}
    assert [x["head"] for x in json.loads((root / "bite_proof" / "scores.json").read_text(encoding="utf-8"))] == ["a", "b"]


def test_a_broken_file_starts_over():
    root = Path(tempfile.mkdtemp())
    recent.proof_dir(root).joinpath("scores.json").write_text("not json", encoding="utf-8")
    assert recent.remember_score(root, 1, 2, "a") == {"before": None, "streak": 0}


def test_report_shows_the_trend():
    root = Path(tempfile.mkdtemp())
    cs = [{"sha": "a" * 40, "subject": "Fix x", "undo": "guarded", "caught": "`t`"},
          {"sha": "b" * 40, "subject": "Fix y", "undo": "unguarded"}]
    page = recent.write_html(root, cs, [], 1.0, {"before": (0, 2), "streak": 0}).read_text(encoding="utf-8")
    assert '<span class="trend up">↑ up from 0/2 last run</span>' in page


def test_share_card():
    import xml.dom.minidom
    root = Path(tempfile.mkdtemp(prefix="my&shop"))
    card = recent.write_card(root, 3, 4, "Up from 1/4 last run")
    text = card.read_text(encoding="utf-8")
    xml.dom.minidom.parseString(text)  # a well-formed picture, even with & in the folder's name
    assert ">3/4</text>" in text and "Up from 1/4 last run" in text and 'width="1200" height="630"' in text
    assert 'font-size="130"' in recent.write_card(root, 100, 120).read_text(encoding="utf-8")  # long scores fit
    assert recent.write_card(root, 0, 0) is None
