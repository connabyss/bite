# Bite Check: the automatic check

Each time Claude finishes a turn that changed code, this plugin's Stop hook (`hooks/stop.js`, run with node)
hands the turn to `bite live --hook`. Bite takes the change back out of a copy of your project and runs your
tests. If they still pass, no test guards the change, and Claude is sent back once to add a test that fails
without it. The same changes are never checked twice, and if Bite isn't installed the hook stays quiet.

Install Bite (`pipx install bite-check`), then in Claude Code: `/plugin marketplace add connabyss/bite` and
`/plugin install bite-check@bite`. For the skill and the `/bite` command, add `fixed-or-not@bite` too.

It runs your project's tests in a temporary copy (your files are never changed), reads your git history, writes
`.git/bite/live.json`, and sends nothing anywhere. Docs: [docs/live.md](https://github.com/connabyss/bite/blob/main/docs/live.md).
License: MIT.
