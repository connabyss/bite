"""The Bite score: of the changes Bite could check, how many a test noticed, with a badge that can follow it."""

import json
import subprocess
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


def test_badge_color_and_url():
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

def test_report_badges_have_copy_buttons():
    root = Path(tempfile.mkdtemp())

    # Test the Bite score badge
    cs = [c("guarded", caught="`test_x`"), c("unguarded")]
    page = recent.write_html(root, cs, [], 1.0).read_text(encoding="utf-8")

    expected_score_badge = recent.score_badge(1, 2)
    assert f'data-copy="{expected_score_badge}"' in page

    # Test the Bite-proof badge
    cs = [c("guarded", caught="`test_x`")]
    page = recent.write_html(root, cs, [], 1.0).read_text(encoding="utf-8")

    assert f'data-copy="{recent.BADGE}"' in page
    assert page.count('class="copy-badge"') >= 1


def test_cat_prints_only_on_bite_proof(tmp_path):
    kit = Path(__file__).resolve().parent.parent
    py = sys.executable

    # Contract verification: plain ASCII, 3 to 5 lines
    assert recent.CAT_ASCII.isascii()
    assert 3 <= len(recent.CAT_ASCII.splitlines()) <= 5

    # 1. Run that is not Bite-proof (bite --demo): the cat should not appear
    demo = subprocess.run([py, str(kit / "recent.py"), "--demo"], capture_output=True, text=True)
    assert demo.returncode == 0
    assert recent.CAT_ASCII not in demo.stdout

    # 2. Bite-proof run: a tiny repo where every change checked is noticed by a test
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".bite.ini").write_text(f'[bite]\ntest_command = "{py}" -m pytest -q -p no:cacheprovider\n')
    (root / "shop.py").write_text("def total(xs):\n    return sum(xs)\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_shop.py").write_text("from shop import total\n\ndef test_total():\n    assert total([1, 2]) == 3\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "start"], cwd=root, check=True)

    # Change code and add a test that guards the change
    (root / "shop.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    (root / "tests" / "test_shop.py").write_text("from shop import total\n\ndef test_total():\n    assert total([0.1, 0.2]) == 0.3\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "Fix total rounding"], cwd=root, check=True)

    # Standard run: cat appears on a Bite-proof run
    p = subprocess.run([py, str(kit / "recent.py"), "--free", "--last", "1"], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0
    assert recent.CAT_ASCII in p.stdout
    assert "Bite-proof. Nice work." in p.stdout

    # 3. --json run: cat never appears in --json stdout or stderr
    p_json = subprocess.run([py, str(kit / "recent.py"), "--free", "--last", "1", "--json"], cwd=root, capture_output=True, text=True)
    assert p_json.returncode == 0
    assert recent.CAT_ASCII not in p_json.stdout
    assert recent.CAT_ASCII not in p_json.stderr
    res = json.loads(p_json.stdout)
    assert res["score"]["noticed"] == 1 and res["score"]["out_of"] == 1
