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
left unchecked. The one real ask:

- **For a bug fix, a test that fails without your change.** That's Bite's whole point, so we hold ourselves to
  it too. Not sure your test catches it? Run `bite live` before you commit: it tells you whether any test
  notices your change.
- `python -m pytest` passes, and CI is green (those checks do block the merge).
- One fix per PR, with plain words in the description: what was wrong, what you changed, how you checked.
- A short title in the [Conventional Commit](https://www.conventionalcommits.org/) style, like
  `fix(recent): refuse --jobs 0 instead of quietly using 1`. The title becomes your line in the release notes, so
  make it say what changed. The maintainer writes CHANGELOG.md; you don't need to.

Nice to have, never required: light and dark screenshots if it changes how something looks (we can take them).
If a small piece is left over, a maintainer may finish it for you and keep you as co-author.
Once it's merged, you're credited by name in [CONTRIBUTORS.md](CONTRIBUTORS.md) and in the next release's notes.

## Where things are

| | |
|---|---|
| `recent.py` | the `bite` command: finds fix claims, the free pass, the report |
| `live.py` | `bite live` and the Claude Code plugin's hook |
| `bite_mcp.py` | `bite mcp`, the live check as an MCP tool |
| `bite.py` | the engine: settings, running tests, safe copies, the command filter for the paid step's worker |
| `repo.py` | git and settings helpers |
| `ask.py` | `bite ask`, questions about a fix in plain words |
| `open_pr.py`, `action.yml`, `bot/` | the GitHub Action and the repo's own bots (like the PR checklist check) |
| `tests/` | the tests; `tests/selftest.py` is the big one and runs inside `python -m pytest` |
| `plugin/`, `plugin-live/`, `skills/` | the Claude Code plugins and the agent skill |
| `docs/` | the longer guides |

## How we review

You should never have to guess when you're done. So a review of your PR follows these rules:

1. **The first review is complete.** It names every change that blocks the merge, in one comment. Anything not in
   it doesn't block.
2. **Later rounds check only those changes**, plus anything the new code itself breaks. A new idea after the first
   review is not a new condition: the maintainer opens an issue for it or does it after the merge. The one
   exception is a real problem the first review missed, like a wrong verdict. It may still block, and the review
   says plainly that it should have come up the first time.
3. **A conflict caused by changes on `main` is ours to fix**, not yours.
4. **Optional suggestions say "optional"**, and they never hold up a merge.

## AI-assisted PRs

Welcome. Bite exists to check AI-written fixes, so it would be odd to turn them away. Please add an
`Assisted-by: <tool>` line (for example `Assisted-by: Claude Code`) to the commit message or the PR
description, and make sure you've read and run the change yourself. Bite will probably be run on your PR.

Coding agents: read [AGENTS.md](AGENTS.md#working-on-bites-own-code) too. It has the extra rules for working on
Bite's own code.

## Try Bite by hand

`bite --demo` shows Bite on a made-up project in a few seconds. To build one yourself, step by step, with a
fix no test covers and then the test that catches it (Linux, macOS and Windows PowerShell):
[docs/try-it-by-hand.md](docs/try-it-by-hand.md).
