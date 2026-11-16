<!-- Thanks for the PR! Tick what applies, or write n/a on a line that doesn't.
     The checklist check never blocks your PR; it only reminds you of anything left. -->

**What was wrong, what you changed, how you checked:**

Fixes #

- [ ] The title says what changed, in the Conventional Commit style: `fix(recent): refuse --jobs 0 instead of quietly using 1`. It becomes the line in the release notes.
- [ ] It links the issue it fixes (a small fix can skip this).
- [ ] For a bug fix: a test that fails without the change and passes with it (docs and looks can skip this). `bite live` tells you if any test notices your change.
- [ ] `python -m pytest` passes (it runs `tests/selftest.py` too), and CI is green. Changed a message? Search `tests/` for its old wording.

Nice to have, never required: light and dark screenshots if it changes how something looks (we can take them for you), and an `Assisted-by: <tool>` line in the commit or here if an AI helped.
