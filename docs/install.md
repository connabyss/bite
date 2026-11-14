# Install, the paid step, speed and updates

[← Back to the README](https://github.com/connabyss/bite#readme)

## Try it in a minute

Install once with [pipx](https://pipx.pypa.io), which gives Bite its own space so there's no venv to set up or
activate:

```
python -m pip install --user pipx
python -m pipx ensurepath
```

Close the terminal window and open a new one, then:

```
pipx install bite-check
bite --demo
```

`bite --demo` builds a tiny made-up shop project in a temporary folder and runs the free check on it. Two of
its commits say they fixed something: one added a test for its fix, the other didn't. Bite takes each fix back
out and runs the tests, and you see the difference:

```
  9661edcf ✅ noticed by test_discount_never_below_zero Fix discounts over 100% making the price negative
  e5c329ec ⚠️ NO TEST NOTICED           Fix totals showing long decimals like 0.30000000000000004
```

It needs nothing besides git, takes a few seconds, and doesn't touch your files. Then try it on your own project:

```
bite --free /path/to/your-repo
```

(Or type `bite --free ` and drag the project's folder into the window. From inside the project's folder, plain
`bite --free` works too.)

A project you haven't cloned works from its link, as copied from the browser:

```
bite --free https://github.com/pallets/click
```

Bite clones it (GitHub, GitLab, Codeberg, Bitbucket, or any address ending in `.git`) into a `bite-projects`
folder in your computer's temporary folder, and keeps it, so a second run only downloads what's new. It runs that
project's tests there, which runs its code on your computer: check only projects you'd run yourself. If its tests
need their own setup first (`pip install -e .`, `npm install`), Bite says the tests already fail; go into the
folder it names, do the setup, and run Bite again.

No Python on this computer? [Open Bite in GitHub Codespaces](https://codespaces.new/connabyss/bite?quickstart=1):
a terminal in your browser with Bite installed, where both lines above work.

`bite` now works in any terminal window. `bite --free` needs no key and costs nothing. It takes each recent
change back out, runs your tests, and lists the changes no test guards, plus any new test that still passes
without its commit's code (it tests nothing). If something it needs is missing, like git or pytest, it says
so and gives you the line that installs it. Each run ends with a one-page report, `bite_proof/report.html`, to open in your browser. To update Bite later, see [Updating Bite](#updating-bite).

To test the claims themselves (the paid step), add one extra package and set `ANTHROPIC_API_KEY`, then run `bite`:

```
pipx inject bite-check claude-agent-sdk
```

This step uses your own API key, and `--budget` caps what a run spends ($1 by default). It runs on Anthropic's
Agent SDK, so it needs an API key and never uses a Claude login or plan (Anthropic's Agent SDK rule:
https://code.claude.com/docs/en/agent-sdk/overview). The commits Bite checks can come from any coding AI or person.

Works with pytest, npm test, cargo test, go test, dotnet test, Maven and Gradle. Settings and limits: [AGENTS.md](https://github.com/connabyss/bite/blob/main/AGENTS.md),
written so your coding AI (Claude Code, Codex, Cursor, Copilot) can set Bite up for you. To work on Bite itself: clone it, `pip install -e .[test]`, then `python -m pytest`.

## When a check is slow

Bite runs your tests several times for each change, so a slow test suite makes a slow check. Four ways to speed it up:

- `bite --free --jobs 4` checks 4 changes at a time. If two checks get in each other's way (a shared file, a port),
  Bite runs the failed one again on its own before it counts, so a clash never shows up as a result.
  Skip it when your test command already runs the tests side by side (pytest `-n auto`): the checks then fight
  for the same cores and get slower, and Bite says so.
- Bite remembers the changes it checked with ✅ in `bite_proof/checked.json`, and skips them next time when the
  settings and dependency files (requirements.txt, package-lock.json, go.sum, ...) are the same. Bite checks each
  change on a copy of its own commit, so tests added or changed later don't undo a ✅; a test file deleted since,
  a new library version or a changed test command does. A ✅ that leaned on later tests (a piece of the change
  only a later test notices) is checked again whenever any test changes. `--again` checks everything anyway. The
  Action keeps that memory between runs for you, so a new push to a pull request checks only its new commits.
- `bite --free --shard 2/5` runs part 2 of 5. Run parts 1/5 to 5/5 on 5 machines at once and together they check
  every change, in about a fifth of the time. On GitHub Actions that's a matrix:

  ```yaml
  strategy:
    matrix:
      part: [1, 2, 3, 4, 5]
  steps:
    # ... check out and install, as usual
    - run: bite --free --shard ${{ matrix.part }}/5
  ```

- pytest: install pytest-xdist and put `test_command = python -m pytest -n auto` in `.bite.ini` to run the tests
  themselves 4 at a time. Or point `free_test_command` at a faster part of your tests.
- If your tests only reach part of the project (a Unity game whose tests cover `Assets/Sim`, say), put
  `test_covers = Assets/Sim/*, tests/*` in `.bite.ini`. Commits that touch none of those paths are listed as
  outside the tests' reach instead of being checked, so they don't each take a test run and come back as
  "no test noticed".

When each change takes over 3 minutes, Bite prints these tips at the end of the run.

## Updating Bite

`bite --version` prints your version, and when a newer one is out it says so and gives you the line to paste.
That line always gets the newest version:

```
pipx install --force bite-check --pip-args="--no-cache-dir"
```

Installed with pip instead of pipx? `python -m pip install --upgrade --no-cache-dir bite-check`

Why not just `pipx upgrade bite-check`? Right after a release, pip can keep using the list of versions it saved
earlier and say you're already on the latest. `--no-cache-dir` makes it ask PyPI fresh, and `--force` also replaces
an older `bite` or `bite.exe` that's in the way.

What changed in each version: [CHANGELOG.md](https://github.com/connabyss/bite/blob/main/CHANGELOG.md). Which languages,
test runners and places Bite works in: [SUPPORTS.md](https://github.com/connabyss/bite/blob/main/SUPPORTS.md).
