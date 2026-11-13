# CLAUDE.md

The instructions for Claude and every other coding AI live in AGENTS.md:

@AGENTS.md

## When you work for the maintainer (connabyss)

These rules are for Claude sessions run by the repo's owner, on top of AGENTS.md. Contributors can skip them.

- Commit as `CH <340279802+connabyss@users.noreply.github.com>` (the GitHub no-reply address), never a personal email.
- Fewer PRs with more changes each. Batch related work into one PR instead of opening many small ones in a row;
  overlapping fixes always go in ONE PR.
- Don't merge. Open the PR, assign connabyss, request their review, and let them merge.
- No PRs, issues or comments on other people's repos unless connabyss picked that repo. Draft the text for them to post.
- Nothing goes live or public without connabyss's OK: releases, posts, badge or README changes on other sites.
  Publishing a GitHub release uploads to PyPI (`.github/workflows/publish.yml`), so never create one; releases are
  planned first.
- Before a PR: `pip install -e .[test]`, then `python -m pytest` (no key, no network). A bug fix needs a test that
  fails without it. Fill in `.github/pull_request_template.md`.
