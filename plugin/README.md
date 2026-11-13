# Bite for Claude Code

Bite checks Claude's "fixed" the moment it says it. When Claude finishes a turn that changed code, Bite takes
that change back out of a copy of your project and runs your tests. If the tests still pass without the change,
no test guards it, and Claude is sent back once to add a test that fails without it. You see "fixed" only after
a test proves it.

## What's in this plugin

- **A Stop hook** that runs `bite live --hook` each time Claude finishes a turn. Same changes are never checked twice.
- **The `/bite` command**, which runs `bite live` on demand and tells you the result.
- **The `bite-verify-fix` skill**, which teaches Claude when and how to prove a fix before claiming it.

## Install

The plugin calls the `bite` command from the `bite-check` package on PyPI, so install that first:

```
pipx install bite-check
```

Then add the plugin in Claude Code:

```
/plugin install bite --marketplace connabyss/bite
```

On older Claude Code: `/plugin marketplace add connabyss/bite`, then `/plugin install bite@bite`.

No pipx: `python -m pip install bite-check`. Bite needs Python 3.10 or newer, git, and your project's own test
runner (pytest, npm test, cargo, go, dotnet, Maven or Gradle).

## What it runs, reads and sends

- It runs your project's own test command, twice per check: once as is and once with the change taken out.
  The tests run in a temporary copy of the project, so your files are never changed. Tests run with your
  user's rights; set `contain_command` in `.bite.ini` to run them inside Docker with no network.
- It reads your git history and the files that changed since the last commit or since the turn started.
- It writes a small state file inside your `.git` folder (`.git/bite/live.json`) so it doesn't repeat itself.
- It sends nothing anywhere. The live check makes no network calls and needs no API key or account.

## Limits

Bite tests one thing: whether a test notices this change. It can't prove the code has no other bugs. "Couldn't
check" is not a pass, and Bite says so plainly.

Source, track record and the full docs: [github.com/connabyss/bite](https://github.com/connabyss/bite).
License: MIT.
