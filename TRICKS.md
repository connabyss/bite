# Try to trick Bite

Bite asks one question: **if this change disappeared, would a test notice?** So we tried to make it answer wrong.
Each trick below is a tiny made-up repo whose newest commit is the trick. We ran `bite --free` on it and wrote down
what Bite said next to the honest answer.

**Before:** 18 of 28 tricks fooled Bite (2 more were plain controls, and it got those right).
**After this round:** 2 still do, and one of them (the flaky test) gets through half as often. Each fixed one has a test in [tests/test_tricks.py](tests/test_tricks.py) that
failed before its fix.

"Fooled" means Bite gave the wrong answer: it said a test noticed when none really did, it skipped a real fix, or it
flagged something that isn't a fix claim.

## Fixed

| Trick | Honest answer | Bite before | Bite now |
|---|---|---|---|
| One commit fixes `total()` (no test) and tweaks the tested `label()` | the fix is unguarded | ✅ noticed by `test_label` | ⚠️ PART NOT NOTICED: `total()` |
| The fix adds a helper `cents()`; the new test only checks `cents` exists | the fix is unguarded | ✅ noticed | ⚠️ PART NOT NOTICED: `total()` |
| Same, but the test calls `cents(1.2)` and checks nothing | the fix is unguarded | ✅ tests crash without it | ⚠️ PART NOT NOTICED: `total()` |
| Move `shop.py` to `store.py` and slip the fix in | the fix is unguarded | ✅ tests crash without it | ⚠️ its tests didn't notice |
| A fix whose title starts `chore:` | checked | ➖ skipped as a tidy-up | ⚠️ NO TEST NOTICED |
| "Refactor total and fix rounding bug" | checked | ➖ skipped as a tidy-up | ⚠️ NO TEST NOTICED |
| "Make total faster and correct its rounding" | checked | ➖ skipped as a speed-up | ⚠️ NO TEST NOTICED |
| "Fix rounding (reported by a Windows user)", no Windows-only code | checked | ➖ skipped: built for Windows | ⚠️ NO TEST NOTICED |
| "Fix rounding, first seen on Python 3.8", no version check in the code | checked | ➖ skipped: built for Python 3.8 | ⚠️ NO TEST NOTICED |
| The change sits after a `#` inside a triple-quoted string (a colour `#fff`) | checked | not checked (read as a comment) | ⚠️ NO TEST NOTICED |
| The change sits after `//` inside a JavaScript template string (a URL) | checked | not checked (read as a comment) | ⚠️ NO TEST NOTICED |
| The fix is in a docstring the code reads (`__doc__`) | checked | not checked (docstring only) | ⚠️ NO TEST NOTICED |
| The fix is in a type hint the code reads (`get_type_hints`) | checked | not checked (hint only) | ⚠️ NO TEST NOTICED |
| Every test is marked skip | no tests ran | ⚠️ NO TEST NOTICED | ⚠️ no tests found |
| `Revert "Fix total rounding"` | not a fix claim | read as a fix claim | not a claim |
| The fix's test file is deleted in a later commit | the fix is unguarded today | ✅ noticed (by a test that's gone) | ⚠️ ITS TEST IS GONE |
| An unrelated test that fails half the time | the fix is unguarded | ✅ noticed by the flaky test, 1 run in 2 | 1 run in 4 (see below) |

How the big one works: when the whole change is noticed, Bite now also takes out each piece of it alone (one piece
per function it touched, up to 6). A piece no test notices on its own is named. If no piece is noticed alone, the
pieces only count together and Bite says nothing new. This costs one more test run per piece, only for commits a
test noticed. When test files were deleted after a noticed commit, Bite also takes the change out of today's
code and runs today's tests (two more runs, only then). A piece that only changes a docstring or type hint isn't named on its own.

To check this doesn't add false alarms, we ran the new and the old Bite on Bite's own last 10 code commits. With
Bite's full test suite, every piece of every commit was noticed, the same 10 of 10 as before.

## Still fools Bite

| Trick | Why it still works |
|---|---|
| A flaky test, failing by luck twice in a row | Bite now runs the tests a second time when one fails without the change, and a pass the second time means it didn't really notice. A test that fails half the time still gets through about 1 time in 4. |
| A test that reads the code as text (`assert "round(" in open("shop.py").read()`) | The test really does fail without the change. Telling "checks the text" from "checks what it does" isn't something Bite can see from a test run. The paid step, which reads the claim, is where this gets caught. |

## Not fooled (it already got these right)

A test that calls `pytest.skip()`, a test that swallows its own failure with `try/except`, a test that compares the
code with itself, a test file pytest never collects, a test that hangs or exits the process when the fix is gone,
an empty commit, a whitespace-only commit, a fix in a language the tests don't run, and a fix split over two
commits (code first, test next: "a later test notices").
