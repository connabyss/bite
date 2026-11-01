# Contributing to Bite

Thanks for helping. Bite is small on purpose, so the best PRs are small too.

## Set up (one minute)

```
git clone https://github.com/connabyss/bite && cd bite
pip install -e .[test]
python -m pytest
```

The tests need no key and no network. They should all pass before and after your change.

## What helps most

- **Bite was wrong about your repo.** It flagged a fix that holds, or stayed quiet about one that doesn't. Open
  an issue with the commit link and what Bite printed. These reports make Bite better than anything else.
- **Fixes.** Something crashes, a message is confusing, a test runner isn't guessed right, a path breaks on
  Windows. Issues labeled "good first issue" are a good place to start.
- Bite's scope is deliberately narrow: it checks "fixed" claims in commits. Please open an issue before
  building something bigger, so we can talk first.

## PR checklist

Opening a PR fills in a short checklist for you. Its check never blocks your PR; it only reminds you of a box
left unticked. The one real ask:

- **For a bug fix, a test that fails without your change.** That's Bite's whole point, so we hold ourselves to
  it too. Not sure your test catches it? Run `bite live` before you commit: it tells you whether any test
  notices your change.
- `python -m pytest` passes, and CI is green (those checks do block the merge).
- One fix per PR, with plain words in the description: what was wrong, what you changed, how you checked.

Nice to have, never required: light and dark screenshots if it changes how something looks (we can take them).
If a small piece is left over, a maintainer may finish it for you and keep you as co-author.

## AI-assisted PRs

Welcome. Bite exists to check AI-written fixes, so it would be odd to turn them away. Please add an
`Assisted-by: <tool>` line (for example `Assisted-by: Claude Code`) to the commit message or the PR
description, and make sure you've read and run the change yourself. Bite will probably be run on your PR.
