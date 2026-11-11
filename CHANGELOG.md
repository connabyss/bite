# Changelog

What changed in each Bite release, newest first. Numbers link to the pull request on
github.com/connabyss/bite. Install or update: `pipx install --force bite-check --pip-args="--no-cache-dir"`.

## Unreleased

Both found while testing Bite on [Plexito-de/spantruth](https://github.com/Plexito-de/spantruth):

- A test command with `--deselect tests/x.py::test_slow` (or `--ignore`, `--rootdir` and other options that take a
  path) no longer swallows the commit's own test file. The path was dropped as "a folder to test", so `--deselect`
  took the file Bite added instead, the commit's own tests never ran, and Bite could say "noticed" for the wrong
  reason.
- A test that fails at an older commit but passes today, in a file that hasn't changed (like a check that the
  installed package's version matches `__version__`), no longer makes Bite skip that commit as "tests fail at this
  commit". Bite sets up to 3 such tests aside, checks with the rest, and says which: "set aside (already failing at
  this commit): test_version". It can't notice anything either way, since it fails with the change still in.

Also:

- `--jobs` beside a test command that already runs the tests side by side (pytest `-n auto`) now says so: the runs
  fight for the same cores. On Bite's own repo (4 cores, `-n auto`) `--jobs 2` took 22 minutes against 14 one at a
  time. The slow-run tip no longer suggests `--jobs` there.
- README and docs refresh: says Bite needs Python 3.10+ and git, fixes the chi row to match the scoreboard,
  moves claude-seo #392 to merged in the track record, and explains `test_covers` in the install guide.

## 1.0.7 (2026-11-06)

Thanks to [@SatriaBagusNurhadianto](https://github.com/SatriaBagusNurhadianto) and
[@hamid-digitalmarketer](https://github.com/hamid-digitalmarketer) for their first pull requests, put together
in #218, and to [@zheng-guannan577](https://github.com/zheng-guannan577) for their first pull request (#193):

- On a repository with fewer commits than `--last`, Bite says "1 commit changed code in all 2 commits." instead
  of "in the last 999", as if it had looked at 999 (#161). Satria wrote the fix (#162), Hamid wrote its test (#170).
- `bite live` stops on an option it doesn't know, like `--sinse`, instead of quietly checking the wrong base, and
  `bite live --since` with nothing after it says what's missing. Both exit 2 (#172, #193).
- Branch checks (`--since main`, what the GitHub Action runs) say "1 commit changed code since main." instead of
  "in the last 40", and the totals line lists only the counts that aren't zero (#219).
- A small Hack Week easter egg: when a commit sounds very sure ("for real this time") or not sure at all
  ("hopefully"), its free-check result adds one line saying whether a test agrees. It only appears when that line
  is true, and it never changes the result (#217).
- The README points to Cold Case Unit, another project by Bite's maintainer (#216).

## 1.0.6 (2026-11-05)

- `bite mcp`: the check_fix and ask_bite tool descriptions now say which tool to use when, what each answer
  means (including "couldn't check", which isn't a pass) and how many test runs each takes. The settings they
  take have examples and defaults (#214).
- New pages and files in the repository: a short comparison of Bite with mutmut and coverage.py (#212),
  SECURITY.md and a Code of Conduct (#209), glama.json for Bite's Glama listing (#211), and CONTRIBUTORS.md
  crediting Bite's contributors (#213). The README and CONTRIBUTING are shorter, with the
  details moved to docs/ (#207, #208), and the README has a "Fooled Bite" box (#206).

## 1.0.5 (2026-11-05)

Thanks to [@phsecx](https://github.com/phsecx) for their first pull request: `--only` with a commit id that
isn't in the repository now says so (#192). And thanks again to
[@hrithiksaini99](https://github.com/hrithiksaini99) for three more: "Did you mean" for a misspelled option
(#180), `bite live` in a repository with no commits yet (#181) and "1 matching commit" in `bite ask` (#182).

- `bite --only zzzz` says "there's no commit zzzz in this repository" and stops (exit code 2). It used to say
  "Nothing to check" and end as if all was well. With several ids, it names only the missing ones (#192).
- A misspelled option gets a suggestion: `bite --fre` says "Did you mean --free?" (#180).
- `bite live` in a repository with no commits yet says to make a first commit, instead of naming `--since HEAD`
  (#181).
- `bite ask` says "1 matching commit", not "1 matching commit(s)" (#182).
- A test-run line full of `::` (like `FAILED ::::::...`) could make Bite hang while reading which tests failed:
  the pattern for pytest's test names could try exponentially many ways to match it. It now reads such a line at
  once, with the same names as before. Found by GitHub's CodeQL scan (#198).
- Bite's own workflows run with read-only access to the repository unless a job asks for more (#198).
- Bite's own tests on Windows and Mac run on 2 machines at once, each taking every other test (`--part K/2`, the
  slowest first), so those jobs take about half as long. Every test still runs on every OS and Python; their
  checks are named "tests part 1/2 (os, python)".
- Bite asks git each question about a fixed commit once per run: it read the same file of the same commit up to 7
  times, and each git start costs tens of milliseconds on Windows. Anything that can move (HEAD, a branch, the
  working tree) is still asked every time.
- Bite's quick one-process rerun drops `-n` only when pytest itself runs the tests (not `tox -e pytest -- -n 4`).
- Bite's own tests: the practice projects' pytest runs load no installed plugins (each start was a third slower
  with pytest-xdist), and Bite's own pull request check uses at most 10 machines (2 commits each past 10). On
  Windows CI the tests write their temp files to the runner's faster D: drive.
- Bite starts faster: asyncio (2/3 of its start-up) loads only for the paid step. The quick reruns of a few tests
  (the commit's own tests, the tests that failed) run in one process instead of starting pytest-xdist's workers
  for them. Same tests, same results; about a second saved per commit, more on Windows.
- Bite's own pull request check: a one-commit pull request is checked by the bite job alone, without a part
  machine first (~20 sec of set-up).
- Bite's own self-test (tests/selftest.py, 139 checks) runs in 10 parts side by side under pytest instead of one
  50-second process; `python tests/selftest.py` still runs it all at once. CI prints the 20 slowest tests.
- Bite's own pull request check gives each commit a machine of its own (up to 20) instead of 6 shared ones, so
  it takes about as long as its slowest commit, however many commits the pull request has.
- Bite's own pull request check splits the commits across 6 machines at once (`--shard`, like the weekly
  self-check), then one last job gathers what they remembered and writes the comment. One machine couldn't go
  faster: its 4 cores were already busy with the tests. A 17-commit pull request took about 30 minutes; split, it
  takes about as long as 3 commits. The recipe is in .github/workflows/bite.yml for any project with a slow suite.
- A new push to a pull request checks only its new commits. Bite remembered each commit it checked with ✅, but
  forgot every one of them as soon as any test file changed, so a pull request whose every commit adds a test (as
  it should) started over from zero on each push: 17 commits, about 30 minutes, every time. Bite checks each
  change on a copy of its own commit, so a test added or changed later can't undo that ✅. Now only a test file
  deleted since, a changed setting or a new library version asks again, plus any test change for a ✅ that
  leaned on a later test.

## 1.0.4 (2026-11-04)

Thanks to [@hrithiksaini99](https://github.com/hrithiksaini99) for seven merged
pull requests: "1 commit", not "1 commits" (#163); refuse `--last 0` (#164); "under 1 sec" instead of "0 sec" (#165);
a missing folder is called a folder (#166); name the two demos on a wrong `--demo` name (#167); say what Bite
looks for when no test command is found (#168); and a two-minute walkthrough on a toy repo (#169).

- `--free-checks 0` is refused with a plain message. It used to check nothing and end as if all was well.
- A test the commit added inside a parent test that is skipped on this system counts as skipped too, not as
  "didn't notice". tap names only the skipped parent (dotenv 7c675904 on Windows).
- A commit that changed only TypeScript declaration files (`.d.ts`) is listed as code the tests can't run, not
  flagged: those files hold types only (dayjs).
- `why:` lines no longer end in a literal `\r` or start with a `+` taken from tap's escaped diff dump of the error
  (node-semver on Windows).
- When a commit turns out "rewritten later", Bite prints a line saying it's not flagged after all, so the list matches
  the summary.
- `--only` finds the commits named wherever they are in the history. It used to look only among the last 40,
  so an older commit got "Nothing to check".
- JavaScript projects: Bite's copies now sit outside the project, with a link to its `node_modules`, instead of
  inside `node_modules`. Tools that skip anything under `node_modules` (jest, `@babel/register`, tap) skipped the
  copies too, so on validator.js every commit showed as "tests already fail" though its tests pass.
- npm projects: checking a change on today's code (the "its test is gone" check) really takes the change out now.
  Bite's copies sit inside the project's git folder there, and `git apply` changed nothing while saying it worked,
  so every "its test is gone" on an npm project was false (found on dotenv).
- `--keep-output` saves what the tests printed for each commit, with the change in and taken out, in
  `bite_proof/output/<commit>.txt`, so you can see why Bite read a run the way it did (asked for while checking
  eemeli/yaml).
- A change no test noticed, whose code a later commit in the same run rewrote, is no longer flagged when a test
  notices that rewrite ("rewritten later by <commit>"). A pull request's early drafts no longer look like gaps
  (found on h2 #1329). If the rewrite isn't noticed either, the flag stays.
- When your tests already fail before Bite changes anything, Bite now says so once and stops. If the first 2
  commits it checks fail with nothing taken out, it runs the tests on the newest commit, and when they fail there
  too it stops instead of running every other check the same way (on validator.js that was 40 checks, because
  the test command skipped a build step), and names the test command it ran. When the newest commit's tests pass, it goes on as before.
- A test the commit added that is skipped on this system (marked: `{ skip: process.platform === 'win32' }`) no
  longer makes Bite say "its tests didn't notice". It says the test was skipped here, so it couldn't notice. Read
  from node --test, TAP, go test -v, cargo test and pytest -rs output.
- On Windows, output sent to a file (`bite --free > run.log`) is now UTF-8: the ✅ and ⚠️ marks came out as "?"
  and a cut-off subject's "…" as a stray byte.
- The comeback alarm no longer goes off for a replacement fix: when the later commit that put the old code back
  also took out the fix's tests and added tests of its own (dayjs b575c81a fixed d0e6738a's bug in the timezone
  plugin instead), Bite says "➖ replaced by a later fix", a note instead of "🔁 UNDONE BY A LATER COMMIT".
- Git submodules are in Bite's copies now. git archive leaves them out, so a project whose tests read one (tomlkit's
  toml-test cases) showed "tests already fail" on every commit. Each is filled from its checkout; Bite says once if
  one isn't checked out (`git submodule update --init`).
- When the tests fail with nothing taken out, Bite runs them once more before skipping that commit: a test that
  fails now and then (h2's Hypothesis test, on a cold copy) skipped 2 commits whose tests pass.
- README: a short "Bite does this, you decide that" box, and a link to the Fool Bite challenge (#156).
- Faster when a commit brings its own test (pytest). With the change taken out, Bite runs that commit's own test
  files first. When they notice (fail again, and pass with the change back in), the whole suite doesn't run a
  second time. Otherwise the whole suite decides, as before. Bite's check of its own 3-commit pull request #155 went
  from 15 min 41 sec to 5 min 56 sec on a 4-core machine, with the same results.
- Bite's own pull request check no longer runs 2 commits at once (`--jobs 2`): on a 4-core machine whose tests
  already run 4 at a time, that made every run wait on the other.
- Faster for pytest projects. Once a test notices a change is gone, the luck check (run once more) and the piece
  check (each piece of the change taken out alone) run only the tests that noticed, not the whole suite. A commit
  with 2 pieces used to cost 5 whole-suite runs and now costs 2, plus a few runs of just those tests. Results stay
  the same: those tests also run once with the change back in, where they must pass, and whenever they pass with a
  piece out, the whole suite decides as before.
- The same speed-up for Go, Rust and .NET (`go test`, `cargo test`, `dotnet test`): only the tests that noticed
  rerun. npm test, Maven, Gradle and any test command of more than one step still run the whole suite, since
  their failures can't be picked out safely.
- Clearer results for newcomers: when a test fails with the change taken out, Bite now says that's the good result
  (the test caught it), in the terminal, the report page, `bite live` and `bite mcp`.
- Fool Bite: TRICKS.md invites you to sneak a "fix" past Bite, with an "I fooled Bite" issue form for entries.

## 1.0.3 (2026-11-03)

For someone who has only Python and has never used a terminal much. A walk-through on Windows found two dead ends:
`uvx` and `pipx` aren't there on a fresh PC, and the terminal opens in C:\WINDOWS\system32, where Bite only said
"not inside a git repository".
- `python -m bite_check --free` runs Bite after a plain `python -m pip install bite-check`, even when pip's command
  folder isn't on PATH. It ignores a project's own file named recent.py.
- Run outside a project, Bite shows its demo on a made-up project instead of stopping, then says how to check your
  own: type the same line and drag the project's folder into the window.
- A folder after the options checks that project without `cd` first: `bite --free C:\code\my-app`. A folder that
  has no git history gets a plain "nothing to check there". `--json` outside a project still answers with an error.
- The log is calm by default: one line per finished check, and every 30 seconds one line like "still checking:
  1 of 4 done, 2 min so far...". The line before every test run (change in, change out, the rerun, each piece) is
  now behind `--verbose`, and there the rerun reads as the good news it is: "good sign, a test noticed the change was
  gone: running them once more to make sure it wasn't luck".
- Times in the log are in words: "they took 1 min 25 sec with it in" (was "1m 25s"), and the last line says
  "Took 3 min 30 sec, spent $0.00." (was "210s, $0.00").

## 1.0.2 (2026-11-03)

For a newcomer's first run on their own repo. Each of these was a dead end in a walk-through on a small fresh repo:
- `uvx bite-check --free` and `pipx run bite-check --free` now work: the package name is also a command.
- Run through uvx, Bite ran the tests with uvx's private Python, which has no pytest and none of the project's
  packages, and stopped with "pytest isn't installed". It now steps around its own Python and uses the project's.
- When no commit says it fixed something and none added tests, Bite prints the command that checks them anyway
  (`bite --free --any`) instead of a hint in brackets.
- A small repo whose commits changed no code was told "Try a larger --last", though Bite had already seen every
  commit. It now says so, and what to do next.

## 1.0.1 (2026-11-02)

Fixed:
- A hung test run stops early. Undoing a fix that bounds a loop can make the tests loop forever, and Bite used to wait
  out the full test_timeout (10 minutes) several times for one change. Now, once the tests have passed with the change
  in, a run without it stops at 5 times that length (at least 60 seconds). That counts as the tests noticing the
  change, and the report says so: "Without this change your tests hang (stopped after 66s; they take 13s with it)".
  Same in `bite live` and `bite mcp`. On Scrapling, two loop fixes went from most of an hour to 3.6 minutes (#145).
- With `--jobs`, a failing run is repeated alone only if another run overlapped it, and the flaky rerun serves as that
  repeat. A noticed change costs three test runs again, not five (#145).
- The log says what each test run is ("running the tests with the change taken out (they took 1m 25s with it
  in)..."), so a long check no longer goes quiet (#145).

## 1.0.0 (2026-11-02)

The first stable release. The names in results.json and `--json` stay as they are from here on.

New:
- Bite score: every run says how many of the checked changes a test noticed (7/9), on the report as a ring, in the
  PR comment and results.json, with a README badge and bite_proof/badge.json (#118).
- When several changes have no test, Bite names the one to write first, and why (#119).
- Bite remembers each run's score: "up from 5/9 last run", "Bite-proof 3 runs in a row" (#121).
- Action `badge-branch`: a score badge that updates itself on each push (#123).
- bite_proof/card.svg: the score as a picture to share (#125).
- `bite ask` finds a fix by the function it changed: "is the make_metavar fix guarded?" (#128).
- Python doctests (pytest --doctest-modules) a fix wrote count as its test, like Rust doc examples (#124).
- Rust: a fix tested by a unit test in the same file (`#[cfg(test)] mod tests`) counts as noticed. Go: a change only
  to files built for another system (`x_windows.go`) is skipped, not flagged (#120).
- README: "Why you need this", in plain words, for people who code with an AI (#129).
- Faster checks. `--shard 2/5` runs one part of a check, so 5 machines can split it (#137). `--jobs 4` checks 4 changes
  at a time, and a run that failed alongside others counts only if it fails again on its own. Bite remembers the
  changes it checked with ✅ and skips them next time, unless a test, setting or dependency changed (`--again` checks them all);
  the Action keeps that memory between runs. A slow run ends with tips to speed it up (#138).
- Bite's own weekly check runs on 20 machines at once, and its tests run 4 at a time (#137).
- The Action and the workflows Bite suggests use the newest GitHub actions (checkout v7, setup-python v7,
  upload-artifact v7, cache v6, ...), so they no longer warn that Node.js 20 is deprecated (#22).
- `--write-tests` says what it's doing at each step in plain words ("Asking Claude to write the missing test…",
  "Running it with the change taken out (it must fail)…", "✅ Test written" or why none was kept), with a line every
  minute while a step runs. On GitHub Actions the job page gets a table of every change checked, and the weekly
  self-check gathers one table from all its machines (#140).

Fixed:
- The comeback alarm stays quiet when a later commit did the fix another way, a revert came undone, or a tidy-up
  came undone, and it names the commit that put the old code back instead of a merge (#116).
- A link to a code file no longer stops the whole run, and a file error in one commit's copy only stops that
  commit's check (#117).
- A fix that also deletes a file no longer stops the whole run with an error, and putting the deleted file back
  no longer counts as a piece of the change on its own (#122).
- A source file that isn't UTF-8 (Latin-1, Windows-1252) no longer hides an untested piece of a fix: Bite keeps
  every byte of it when it takes a piece out (#126).
- A fix in a big generated file (a 60,000-line bundle.js) no longer takes minutes to check: Bite reads code
  for comments about 50 times faster and stops splitting a change once it has more pieces than it can test (#127).
- Plain answers for odd inputs: an option with no value, a negative `--last`, a folder that isn't there given to
  `bite mcp`, and links in `bite live` (#130).
- A submodule whose folder is named like a code file (vendor/chart.js) no longer stops a check or bite live (#130).
- Bite's pull request comment no longer pings people named in a commit title ("thanks @alice") (#131).
- The pull request comment stays under GitHub's 65,536-character limit (over it, the Action posted nothing): very
  long commit titles are cut, and long tests Bite wrote point to their file instead (#131).
- `.bite.ini` saved by Windows Notepad works; a setting Bite can't use is named in a sentence instead of a Python
  error (#132).
- A test Bite or its worker wrote now runs when the project's pytest command has an option with a value: `-n auto`
  (pytest-xdist) lost its `auto`, so every claim test and every `--write-tests` test failed to start and was
  thrown out (#143).
- A tidy-up right next to a fix (removing an import beside it) no longer hides a later test that guards it: the
  fix showed NO TEST NOTICED. The comeback alarm also notices an undo that tidied the line beside the fix (#141).
- The self-check's issue no longer asks for the API key when Bite has one but didn't keep the test it wrote; it
  says why the test was thrown out (#140).
- The "check it yourself" steps quote file paths with spaces, so they work when pasted (#133).
- On Windows, Bite's copies keep file names that aren't plain ASCII (`café.py`); before, such a project read as
  "tests already fail" (#134).
- In a shallow clone (git clone --depth 1) Bite says so and gives `git fetch --unshallow`, instead of "try a larger
  --last" (#135).

## 0.11.0 (2026-11-01)
- Harder to trick: 16 of the tricks we threw at Bite no longer fool it. That includes a tested change that vouches
  for an untested one in the same commit, a test deleted later, flaky tests, and `#` inside strings. See
  TRICKS.md (#112).
- Quicker: the piece-by-piece check has one budget for the whole run (`--part-runs`, 6 by default), and `--quick`
  skips the extra checks (#113).
- Plain words when the tests already fail, and the right newest commit (#114).
- One line to update that always works, and `bite --version` says when a new one is out (#111).

## 0.10.0 (2026-11-01)
- Java and Kotlin: Maven and Gradle projects, with the project's own mvnw or gradlew first (#106).
- The comeback alarm: "UNDONE BY A LATER COMMIT" names a later commit that quietly put a fix's old code back
  (`bite --demo comeback`) (#108).
- `bite ask` answers are easier to read (#107), and a crash on an undone fix is fixed (#110).
- Clearer text for people finding Bite on the Marketplace and PyPI (#109). Logo on the report (#90, #105).

## 0.9.0 (2026-11-01)
- `bite --json`, and bite_proof/results.json on every run: results other tools can read, under names that won't
  change (#102).
- `bite ask "is last week's login fix guarded?"`: ask in plain words (#100).
- One set of names for 1.0: NO TEST NOTICED, ITS TESTS DIDN'T NOTICE; `.bite.ini` starts with `[bite]` (old
  `[kit]` still works) (#101).

## 0.8.0 (2026-10-31)
- `bite mcp`: the live check as a tool any coding AI can call (Claude Code, Cursor, Copilot in VS Code, Windsurf,
  Codex, Gemini CLI) (#97).
- Rust doc examples a commit wrote count as its test (#96).

## 0.7.0 (2026-10-31)
- `bite live` and a Claude Code plugin: the free check on your coding AI's changes as it finishes each turn (#70).
- Bite checks Bite: a weekly self-check opens an issue for each gap, and a PR with the test (#71, #73, #79, #81, #84).
- `--write-tests` keeps a written test only if a second fresh check calls it fair (#83).
- The scoreboard: Bite's free check on 20 well-known projects (#82, #85).
- Fewer false alarms: a passing test named "parse error" (#78), JavaScript copies in hidden folders (#74).

## 0.6.0 (2026-10-31)
- `bite --write-tests` and the Action's `write-tests`: write the missing test for each change no test noticed (#66).
- Go: a written test runs as its own package (#67). Release commits and Go `interface{}` to `any` swaps are skipped (#64).

## 0.5.1 (2026-10-30)
- Says why pytest crashed, and turns the check red when the tests already fail (#63).

## 0.5.0 (2026-10-30)
- `bite --demo`: try Bite on a tiny made-up project first (#58).
- tape, tap, ava, uvu, jasmine, nyc and c8 known as JavaScript runners (#59).

## 0.4.1 (2026-10-30)
- On PyPI as `bite-check` (#56).
- Only takes out code in the language the tests run (#55).
- Skips type-hint-only, other-Python-version and speed-up commits (#52).
- `--roast` and the Bite-proof badge (#50). Option values are checked (#47).

## 0.4.0 (2026-10-30)
- Checks every commit by default, whoever or whatever wrote it (#45).

## 0.3.0 (2026-10-30)
- Plain words for what Bite found, naming the test that noticed (#43). Three false flags stopped (#42).

## 0.2.0 (2026-10-30)
- The GitHub Action: Bite's free check on every pull request, with one plain-words comment (#33, #34, #36).
- AGENTS.md, so any coding AI can run Bite (#32).

## 0.1.0 (2026-10-29)
- First release: one-line install, first-run checks that name the fix, and a one-page report after every run.
