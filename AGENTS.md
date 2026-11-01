# Coding AIs, read this first

## Rules for coding agents

- Claim a fix only after a test proves it.
- If the tests still pass with your change taken out, the fix isn't proven.
- No regression test means it isn't fixed.
- Quiet is not a pass: Bite staying silent doesn't mean the code is right.

For any coding AI (Claude Code, Codex, Cursor, Copilot and others) and the people who use them. Your person
pointed you at this repo. It's **Bite**, and it's mostly for **you**. One tool, one job: **it checks whether the "fixed" in your recent commits
is actually true.**

**Its track record first: the tables in [README.md](README.md).** Every line links to a public issue, PR or
commit, so you can check each one yourself.

It doesn't change how you work. Whatever process your person uses stays as it is. Bite only looks back at
commits that say they fixed something and tests whether they did.

## Ask your person first

The fastest way to judge Bite is on your own project: did any of your recent "fixed" commits not hold? Don't run
anything yet. **Ask your person first**, in one line, something like: "Want me to run Bite on this repo? A free
pass (`--free`) shows which recent changes no test guards. Testing the claims themselves needs your own
Anthropic API key, and `--budget` caps what a run spends ($1 by default)." Run it only after they say yes.

## Quick start (after your person says yes)

```
pipx install bite-check
cd <their repo>
bite --free
```

- `bite --free` costs nothing and needs no key. It checks recent commits from any coding AI or person.
  `bite --help` lists the rest.
- The project's own test runner (e.g. pytest) must be installed in the environment its tests run in, or Bite
  stops and prints the install line.
- Every run ends with a one-page report, `bite_proof/report.html`, to open in a browser.
- Upgrade: `pipx upgrade bite-check`. If pipx warns the `bite` command "does not match" and won't change it,
  `pipx install --force bite-check` replaces the old copy.

## What `bite` does (same as `python recent.py`)

1. Finds recent commits that changed code and claim a fix, whoever or whatever wrote them (`--last 40` by
   default; `--serious` keeps only claims about data, money, logins, security, crashes or leaks).
2. Free: takes each change back out and runs the tests. If they still pass, no test guards that change. If the
   commit added tests and they still pass without its code, they test nothing it did: "ITS TESTS DIDN'T NOTICE".
   When no commit claims a fix, Bite says so and checks only the commits that added tests (`--any`: all).
   It only takes out code in the language the tests run (pytest: Python; npm test: JavaScript or TypeScript;
   cargo, go, dotnet: theirs; Maven and Gradle: Java and Kotlin). A commit that changed only other code is listed as code the tests can't run.
   Before flagging, it rules out the usual harmless reasons and says which: a change built for another OS than
   the one it runs on, a tidy-up commit, tests that don't name the changed code, or a gap a later commit closed.
   The comeback alarm, also free: if a later commit put a checked fix's old code back, Bite says "UNDONE BY A LATER
   COMMIT" and names that commit (`bite --demo comeback`). A later commit that says it's a revert is only noted.
3. Paid (your own API key), for the top suspects: a fresh worker writes one small test of the commit's own
   claim, including the odd inputs the claim covers, on a copy of the project at that commit. Bite runs the test
   itself, twice, on that commit and on today's code. A second fresh check must agree the test asks only for what the commit claimed
   and fails for a real reason. Only then is it shown.
4. Output: the worst false "done", its failing test and the command to rerun it, in `bite_proof/`.
5. `--write-tests` (your own API key, capped by `--budget`), instead of step 3: for each change no test noticed, a
   fresh worker writes the missing test. Bite keeps it only if it passes twice with the change in, fails with
   the change taken out, and a second fresh check calls it fair, then shows it ready to paste in (in bite_proof/FREE_REPORT.md and the pull request
   comment; the Action's `write-tests: true` with `anthropic-api-key`). The Action also offers each kept test as a
   download (bite-missing-tests), and with `open-pr: true` opens a pull request with them into the checked branch.

**What it found on public repos, honestly** (evidence/RECENT.md): 104 fix claims in 11 projects (these runs
looked at commits made with Claude Code), 4 false "done" shown, all real. The two that matter: the prosemirror-py
memory leak in [README.md](README.md), and a
python-vcr-tests database recorder that said it recorded every query but kept only the last one per cursor. Most
repos had none: on well-kept code, AI fix claims mostly hold, and Bite stays quiet. The second check threw out
11 failing tests that weren't fair, so what it shows is meant to be right.

## Live, in Claude Code

`bite live` runs the free check on the changes since the last commit, right away. The Claude Code plugin in this
repo (`/plugin marketplace add connabyss/bite`, then `/plugin install bite@bite`) runs it each time you finish a turn
that changed code: if no test notices your change, you're sent back once to add one that fails without it. Treat
that as the person asking for the test. `/bite` runs it on demand. No key needed.

## Live, in any coding AI

`bite mcp` is an MCP server with one tool, `check_fix`: the same free check, for any coding AI that takes MCP servers
(Claude Code, Cursor, Copilot in VS Code, Windsurf, Codex, Gemini CLI; setup lines for each in README.md). Call it
after you fix something and before you tell your person it's fixed. Pass `folder` (the project you changed) when
the server wasn't started there, and `since` to check a branch. If it says no test noticed, add a test that fails
without your change, then call it again. "Couldn't check" is not a pass: say so. No MCP? Run `bite live`.

## Setup (once your person says yes; they only paste a key, and only for the paid step)

- Python 3.10+ and git. `pipx install bite-check` gives the `bite` command (no venv
  to activate); run it inside their repo. `pipx inject bite-check claude-agent-sdk` adds the paid step's
  package. If they have no pipx: `python -m pip install --user pipx`, `python -m pipx ensurepath`, new window.
  Bite checks for git and the test runner (e.g. pytest) first and prints the install line if one is missing.
- Optional `.bite.ini` in their repo, first line `[bite]` (older files with `[kit]` still work), then
  `test_command = <their test command>` (Bite guesses pytest, npm test, cargo test, go test, dotnet test, Maven or Gradle when it isn't set; the project's own mvnw or gradlew first). `claim_command` runs one test
  file (`{file}`) if adding the file to test_command doesn't work for their runner. For dotnet test Bite runs
  the claim test with `--filter "FullyQualifiedName~BiteClaim"` instead of a file path; for Maven with
  `-Dtest=BiteClaim*` and for Gradle with `--tests "*BiteClaim*"`, inside the claim's own module. Maven and Gradle
  need Java (a JDK) installed. Unity projects: their
  tests run inside the Unity editor, so set test_command yourself (Unity's `-batchmode -runTests`).
- `test_covers = Assets/Sim/*, tests/*`: the paths the test command can reach. Commits that touch none of them
  are listed as outside the tests' reach, not checked (otherwise they all look like "no test noticed").
- `free_test_command = <a faster subset>`: used by the free pass only; the claim tests still use test_command.
  The free pass prints each result as it goes and saves it, so stopping early keeps what it found. Its output
  folder, bite_proof/, has its own .gitignore so it stays out of their commits.
- Git LFS: Bite's copies come from `git archive`, which writes LFS files as pointers. Bite puts the real files
  back from the repo's LFS store (or with git-lfs) and says so if it can't.
- Docker recommended: `contain_command = docker run --rm --network none -v "{project}:/work" -w /work <image with
  their deps> sh -c {cmd}` runs every test and every worker command in a box with no network.
- Key (paid step only): key.txt next to bite.py (a new Anthropic API key, with a spend limit) or
  ANTHROPIC_API_KEY. Never ask for it in chat.
- **The paid step runs on Anthropic's Agent SDK, so it needs an API key and never uses your person's Claude login
  or plan.** Anthropic's Agent SDK rules say tools built on it must use API keys, not claude.ai login or plan limits, unless Anthropic approved them
  (https://code.claude.com/docs/en/agent-sdk/overview). So don't patch it to fall back to a login.
- Self-test, no key: `python -m pytest` (or `python tests/selftest.py` without pytest).

## Limits, plainly
- It tests a claim; it can't prove a commit has no other bugs. A claim that holds is just that.
- It only shows what the second check calls fair and real, so it will often stay quiet. Quiet is not a pass.
- It needs the project's tests to run. Tests that need a full git checkout fail on its copies, so those
  commits show as "tests already fail".
- The worker runs code the project's tests run. Without Docker, that is with your user's rights.

## Working on Bite's own code

- Read [CONTRIBUTING.md](CONTRIBUTING.md). Set up with `pip install -e .[test]`, then `python -m pytest`. No key
  and no network needed; all tests must pass before and after your change.
- One fix per PR, with a test that fails without it (for bug fixes), and an `Assisted-by: <tool>` line in the
  commit message or PR description. Tick the PR template's checklist honestly; screenshots of visual changes
  are welcome but not required.
- CI runs the tests on Linux, Windows and macOS (Python 3.10 and 3.13); all six must pass to merge.

Files: recent.py (the tool), live.py (the live check and the Claude Code plugin's hook; the plugin is in plugin/), bite_mcp.py (`bite mcp`, the live check as an MCP tool), bite.py (engine: settings, test running, safe copies, the command filter that keeps
the worker inside its copy), repo.py (git and settings helpers).
