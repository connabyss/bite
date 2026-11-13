# Fixed or Not

A Claude Code plugin from [Bite](https://github.com/connabyss/bite). It makes Claude prove a bug fix before it
says "fixed". Bite takes Claude's change back out of a copy of your project and runs your tests. If the tests
still pass without the change, no test guards it, and Claude adds a test that fails without it before telling
you the fix is done.

## What's in this plugin

- **The `bite-verify-fix` skill**, which teaches Claude when and how to prove a fix before claiming it. Claude
  uses it on its own after fixing a bug.
- **The `/bite` command**, which asks Claude to run `bite live` on the changes since the last commit and tell
  you the result.

Claude runs `bite live` with its own Bash tool, so Claude Code asks you first unless you have allowed it.

## Install

The plugin uses the `bite` command from the `bite-check` package on PyPI, so install that first:

```
pipx install bite-check
```

Then add the plugin in Claude Code:

```
/plugin install fixed-or-not --marketplace connabyss/bite
```

On older Claude Code: `/plugin marketplace add connabyss/bite`, then `/plugin install fixed-or-not@bite`.

No pipx: `python -m pip install bite-check`. Bite needs Python 3.10 or newer, git, and your project's own test
runner (pytest, npm test, cargo, go, dotnet, Maven or Gradle).

Want the check to run by itself every time Claude finishes a turn? The same marketplace has `bite-check@bite`,
a Stop hook that does exactly that ([docs/live.md](https://github.com/connabyss/bite/blob/main/docs/live.md)).

## What it runs, reads and sends

- `bite live` runs your project's own test command, twice per check: once as is and once with the change taken
  out. The tests run in a temporary copy of the project, so your files are never changed. Tests run with your
  user's rights; set `contain_command` in `.bite.ini` to run them inside Docker with no network.
- It reads your git history and the files that changed since the last commit.
- It writes a small state file inside your `.git` folder (`.git/bite/live.json`).
- It sends nothing anywhere. The live check makes no network calls and needs no API key or account.

## Limits

Bite tests one thing: whether a test notices this change. It can't prove the code has no other bugs. "Couldn't
check" is not a pass, and Bite says so plainly.

Source, track record and the full docs: [github.com/connabyss/bite](https://github.com/connabyss/bite).
License: MIT.
