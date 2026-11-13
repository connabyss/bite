# Contributing to Bite

Welcome, and thanks for helping. First open-source PR? You're in the right place: each
[good first issue](https://github.com/connabyss/bite/labels/good%20first%20issue) says where to look and when
it's done, and if you get stuck we'll help you finish. Bite is small on purpose, so the best PRs are small too.

Questions, ideas, or not sure where to start? Ask in [Discussions](https://github.com/connabyss/bite/discussions).

## Set up (one minute)

```
git clone https://github.com/connabyss/bite && cd bite
pip install -e .[test]
python -m pytest -n auto
```

`-n auto` runs the tests several at a time (pytest-xdist, in `[test]`): about a minute instead of three, and
much faster on Windows. Plain `python -m pytest` runs them one at a time.

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
Once it's merged, you're credited by name in [CONTRIBUTORS.md](CONTRIBUTORS.md) and in the next release's notes.

## AI-assisted PRs

Welcome. Bite exists to check AI-written fixes, so it would be odd to turn them away. Please add an
`Assisted-by: <tool>` line (for example `Assisted-by: Claude Code`) to the commit message or the PR
description, and make sure you've read and run the change yourself. Bite will probably be run on your PR.

## Try Bite by hand

`bite --demo` shows Bite on a made-up project in a few seconds. To build one yourself, step by step, with a
fix no test covers and then the test that catches it (Linux, macOS and Windows PowerShell):
[docs/try-it-by-hand.md](docs/try-it-by-hand.md).
