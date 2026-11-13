---
name: bite-verify-fix
description: Prove a bug fix is real before saying "fixed". Bite takes your change back out of a copy of the project and reruns the tests; if they still pass, no test guards the fix. Use after fixing a bug or before claiming a fix is done, tested or proven. Free, no API key.
license: MIT
---

# Verify a fix with Bite

A green test run doesn't prove a fix. If the tests also pass with your change taken out, nothing guards it, and
the bug can come back without anyone noticing. Bite checks exactly that, for free, in a copy of the project. It
never touches the user's files.

## When to use

- You just changed code to fix a bug, and you are about to tell the user it's fixed.
- The user asks whether a fix is tested, proven or guarded.
- The user asks about an earlier fix ("is last week's login fix covered?").

Skip it for changes that aren't fixes: docs, renames, formatting.

## Setup (once)

Check for `bite --version`. If it's missing, ask the user before installing anything:

```
pipx install bite-check
```

No pipx: `python -m pip install bite-check`, then run `python -m bite_check` wherever this skill says `bite`.
Bite needs Python 3.10+, git, and the project's own test runner (pytest, npm test, cargo, go, dotnet, Maven or
Gradle) installed where the tests run.

## Check your fix

From inside the project, after the fix and its test are in place:

```
bite live
```

It checks the changes since the last commit, committed or not. To check a whole branch, use
`bite live --since main`. It takes about twice as long as one test run.

| Bite says | What it means | What you do |
|---|---|---|
| ✅ a test noticed | With your change out, a test failed. The fix is guarded. | Tell the user, and name the test. |
| ⚠️ no test noticed | The tests pass with or without your change. | Add a test that fails without your change and passes with it. Run `bite live` again. |
| ⚠️ the tests that came with this change don't notice it | Your new test passes even with the fix taken out, so it tests nothing the fix did. | Make the test check the behaviour the fix changed. Run `bite live` again. |
| couldn't check | Something stopped the check, for example the tests already fail with your change in. | This is not a pass. Tell the user the reason. |
| nothing to check | No code the tests run has changed. | Say so. Don't claim it was checked. |

`bite live` exits with 1 only when no test noticed the change, so a script can use it as a gate.

## Rules

- Say "fixed" only after Bite says a test noticed.
- If you add a test after a ⚠️, run `bite live` again. Don't assume the new test works.
- Never weaken, skip or delete a test to make Bite happy.
- Quiet is not a pass. "Couldn't check" is not a pass. Report both plainly.
- Bite tests one thing: whether a test guards this change. It can't prove the code has no other bugs.

## Earlier fixes

```
bite ask "is last week's login fix guarded?"
```

Name the fix with words from its commit message or a file or function it changed. It answers Yes, No or Partly
for up to 3 matching commits.

## More

- A free scan of recent "fixed" commits: `bite --free` (writes `bite_proof/report.html`).
- As an MCP tool (`check_fix`) for Cursor, Copilot, Windsurf, Codex, Gemini CLI:
  [docs/live.md](https://github.com/connabyss/bite/blob/main/docs/live.md).
- Source, track record and limits: [github.com/connabyss/bite](https://github.com/connabyss/bite).
- This skill is also listed on Agensi: [agensi.io/skills/bite-verify-ai-fixes](https://www.agensi.io/skills/bite-verify-ai-fixes).
