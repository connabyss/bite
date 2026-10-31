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

Opening a PR fills in a short checklist for you. In short:

- One fix per PR, linked to its issue, with a test that fails without your change.
- Screenshots in light and dark mode if it changes how something looks.
- `python -m pytest` passes, and CI is green.
- Plain words in the PR description: what was wrong, what you changed, how you checked.

## AI-assisted PRs

Welcome. Bite exists to check AI-written fixes, so it would be odd to turn them away. Please add an
`Assisted-by: <tool>` line to the commit message (for example `Assisted-by: Claude Code`), and make sure
you've read and run the change yourself. Bite will probably be run on your PR.
