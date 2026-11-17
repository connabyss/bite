"""Tests for --roast wording on results that previously had no roast line (#203)."""

import pytest
import recent


def test_roast_lines_for_uncovered_results():
    try:
        # Case 1: guard gone since (ITS TEST IS GONE)
        c_gone = {"sha": "a" * 40, "undo": "guard gone since", "gone": ["tests/test_foo.py"]}
        recent.ROAST[0] = False
        _, label_plain, text_plain = recent.say(c_gone)
        assert label_plain == "⚠️ ITS TEST IS GONE"
        assert "A test noticed it when it was made" in text_plain
        assert "**Next:** put back a test that fails without it." in text_plain

        recent.ROAST[0] = True
        _, label_roast, text_roast = recent.say(c_gone)
        assert label_roast == "⚠️ ITS TEST IS GONE"
        assert "The test that watched this fix was deleted later, so nothing catches it now." in text_roast
        assert "**Next:** put back a test that fails without it." in text_roast

        # Case 2: unguarded: part (PART NOT NOTICED)
        c_part = {"sha": "b" * 40, "undo": "unguarded: part", "part": "the boundary check"}
        recent.ROAST[0] = False
        _, label_plain, text_plain = recent.say(c_part)
        assert label_plain == "⚠️ PART NOT NOTICED"
        assert "Your tests noticed part of this change" in text_plain
        assert "**Next:** add a test that fails without it." in text_plain

        recent.ROAST[0] = True
        _, label_roast, text_roast = recent.say(c_part)
        assert label_roast == "⚠️ PART NOT NOTICED"
        assert "Your tests noticed part of this change, but gave the rest a free pass: if that part breaks, nothing warns you." in text_roast
        assert "**Next:** add a test that fails without it." in text_roast

        # Case 3: tests fail at this commit (tests already fail)
        c_fail = {"sha": "c" * 40, "undo": "tests fail at this commit"}
        recent.ROAST[0] = False
        _, label_plain, text_plain = recent.say(c_fail)
        assert label_plain == "❌ tests already fail"
        assert "Your tests fail at this commit before Bite takes anything out" in text_plain
        assert "**Next:** fix them first." in text_plain

        recent.ROAST[0] = True
        _, label_roast, text_roast = recent.say(c_fail)
        assert label_roast == "❌ tests already fail"
        assert "Your tests were already broken before Bite touched anything, so Bite can't test this fix." in text_roast
        assert "**Next:** fix them first." in text_roast

        # Case 4: no tests ran at this commit (no tests found)
        c_none = {"sha": "d" * 40, "undo": "no tests ran at this commit"}
        recent.ROAST[0] = False
        _, label_plain, text_plain = recent.say(c_none)
        assert label_plain == "⚠️ no tests found"
        assert "Bite couldn't find any tests to run." in text_plain
        assert "**Next:** add one, or" in text_plain

        recent.ROAST[0] = True
        _, label_roast, text_roast = recent.say(c_none)
        assert label_roast == "⚠️ no tests found"
        assert "Bite went looking for tests to run and came back empty-handed." in text_roast
        assert "**Next:** add one, or" in text_roast

    finally:
        recent.ROAST[0] = False
