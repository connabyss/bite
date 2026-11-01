<p>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-header-dark.png">
    <img alt="Bite" src="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-header-light.png" width="300">
  </picture>
</p>

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Bite%20free%20check-blue?logo=github)](https://github.com/marketplace/actions/bite-free-check)

**Bite checks whether an AI coding agent's "fixed" is actually true.**

<img alt="bite --demo: one fix is noticed by a test, the other has no test at all" src="assets/bite-demo.svg" width="760">

It takes each recent fix back out of your code and runs your tests. If they still pass, nothing guards that fix,
and Bite tells you which one. That free check needs no key and works with pytest, npm test, cargo test, go test and
dotnet test:

```
pipx install bite-check
bite --free
```

With your own API key it goes one step further: it writes one small test of the commit's exact claim and runs it.
That is how it found a memory leak in [prosemirror-py](#the-catch-that-shows-what-its-for) that a commit said it
had fixed.

> "Reverting the claimed fix and making the change prove itself under a real test is exactly the kind of check that
> should exist for every "fixed" commit."
>
> — [Ivan Zdravkov](https://zdravkov.info), [on DEV](https://dev.to/izdravkov/comment/3jdej)

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
cd /path/to/your-repo
bite --free
```

`bite` now works in any terminal window. `bite --free` needs no key and costs nothing. It takes each recent
change back out, runs your tests, and lists the changes no test guards, plus any new test that still passes
without its commit's code (it tests nothing). If something it needs is missing, like git or pytest, it says
so and gives you the line that installs it. Each run ends with a one-page report, `bite_proof/report.html`, to open in your browser. To update Bite later: `pipx upgrade bite-check` (if it warns that `bite.exe` or `bite` "does not match" and
won't change it, an older copy is in the way: `pipx install --force bite-check` replaces it).

To test the claims themselves (the paid step), add one extra package and set `ANTHROPIC_API_KEY`, then run `bite`:

```
pipx inject bite-check claude-agent-sdk
```

This step uses your own API key, and `--budget` caps what a run spends ($1 by default). It runs on Anthropic's
Agent SDK, so it needs an API key and never uses a Claude login or plan (Anthropic's Agent SDK rule:
https://code.claude.com/docs/en/agent-sdk/overview). The commits Bite checks can come from any coding AI or person.

Works with pytest, npm test, cargo test, go test and dotnet test. Settings and limits: [AGENTS.md](https://github.com/connabyss/bite/blob/main/AGENTS.md),
written so your coding AI (Claude Code, Codex, Cursor, Copilot) can set Bite up for you. To work on Bite itself: clone it, `pip install -e .[test]`, then `python -m pytest`.

## Check Claude's "fixed" live, in Claude Code

Bite can also check the moment Claude says it fixed something, before you read "fixed!". Each time Claude finishes
a turn that changed code, Bite takes the change back out of a copy of your project and runs your tests. If none of
them notice, Claude is sent back once to add a test that fails without its change. If it stops again and still no
test notices, you get a warning instead, so it never goes round in circles. It's the free check: no API key.

In Claude Code, type:

```
/plugin marketplace add connabyss/bite
/plugin install bite@bite
```

and install Bite itself if you haven't:

```
pipx install bite-check
```

`/bite` checks the changes since your last commit whenever you like. In a trial, Claude fixed a discount and then
wrote `assert total([50, 50], 10) == 90`. That passes with or without the fix (100 - 10 and 100 × 90% are both
90), and Bite said so:

```
Bite ⚠️ the tests that came with this change (test_cart.py) don't notice it: with the change to cart.py taken out,
they still pass. The "fixed" isn't proven yet.
```

Without the plugin, run `bite live` yourself after a change, or `bite live --hook` from any tool that runs a
command when the AI stops (it reads Claude Code's Stop hook JSON).

## Check the "fixed" live, in any coding AI

`bite mcp` gives your coding AI the same free check as a tool it can call, `check_fix`, through MCP, the plug most
coding AIs share. Its description tells the AI to call it after fixing a bug and before saying "fixed". If no test
notices the change, the AI is told to add one that fails without it. No API key; it works in a copy, so your files
are never touched. It needs Bite 0.8.0 or newer (`pipx upgrade bite-check`).

Add it once, in the place your coding AI keeps its MCP servers:

| Coding AI | Where | What to add |
|---|---|---|
| Claude Code | a terminal | `claude mcp add bite -- bite mcp` |
| Cursor | `.cursor/mcp.json` in the project (or `~/.cursor/mcp.json` for all) | `{"mcpServers": {"bite": {"command": "bite", "args": ["mcp"]}}}` |
| Copilot in VS Code | `.vscode/mcp.json` in the project | `{"servers": {"bite": {"type": "stdio", "command": "bite", "args": ["mcp"]}}}` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `{"mcpServers": {"bite": {"command": "bite", "args": ["mcp"]}}}` |
| Codex CLI | a terminal | `codex mcp add bite -- bite mcp` |
| Gemini CLI | `.gemini/settings.json` in the project (or `~/.gemini/settings.json`) | `{"mcpServers": {"bite": {"command": "bite", "args": ["mcp"]}}}` |

Any other AI that takes MCP servers: the command is `bite`, the argument is `mcp`. If yours says it can't start
`bite` (apps opened from the Dock or Start menu don't always see the folder pipx put it in), use the full path
instead: `~/.local/bin/bite` on Mac and Linux, `C:\Users\<you>\.local\bin\bite.exe` on Windows (`pipx list`
shows it). The tool checks the folder Bite was started in; the AI can pass `folder` for another one, and `since`
(for example `main`) to check a whole branch, not just what changed since the last commit.

An AI that can run commands but takes no MCP servers can run `bite live` itself: it prints the same answer and
exits with 1 when no test noticed the change. Put a line like "After you fix a bug, run `bite live` before you
say it's fixed" in its rules file (AGENTS.md, .cursorrules, .github/copilot-instructions.md).

## Ask in plain words

```
bite ask "is last week's login fix guarded?"
```

Bite finds the commit(s) that match your words (their message and the files they changed, and the time if you
name one: today, yesterday, this week, last week, the last 10 days) and runs its free check on each. The answer
is one plain sentence per commit:

```
Yes. "Fix login letting an empty password in" (3f2a9c1, Oct 27) is guarded: with it taken out, the test
test_empty_password_is_refused fails.
```

Matching is free. Only when your words match nothing clearly, and you have an API key, a small AI call picks the
commit instead (about a cent); `--free` never uses the key. `--last 200` looks further back. Coding AIs get the
same thing through `bite mcp`, as the tool `ask_bite`.

## Run it on every pull request

Easiest: [install the bite-check app](https://github.com/apps/bite-check) on the repos you want. Within an hour it
opens one issue there with an "Add Bite" link that fills in the file below for you; you read it and click
**Commit changes**. The app can only open issues: it can't read or change your code or workflows.

Or add this file to your repo yourself as `.github/workflows/bite.yml`. On each pull request it runs the free check on that
pull request's commits and shows a pass or fail check next to your other CI. It fails when a commit's change
can be taken back out and your tests still pass. No key, no cost. It's also listed on the GitHub Marketplace as
[Bite free check](https://github.com/marketplace/actions/bite-free-check).

```yaml
name: bite
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  bite:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      # install what your tests need here, e.g. for Python:
      - uses: actions/setup-python@v5
      - run: python -m pip install pytest -r requirements.txt
      - uses: connabyss/bite@v0.8.0
```

Options go under `with:`: `args` (extra `bite` options, e.g. `--serious`), `max-commits` (default 20),
`fail-on-gap` (set to `false` to report without failing) and `comment` (set to `false` for no comment). It posts one comment on the pull request that says, per
commit, whether a test noticed the change being taken out, and updates that same comment on later pushes. The
rerun steps for each flagged commit are on the job's summary page.

### Have Bite write the missing test (opt-in, your own key)

When no test noticed a change, Bite can write that test for you. Add your Anthropic API key as a repository secret
named `ANTHROPIC_API_KEY`, then:

```yaml
      - uses: connabyss/bite@v0.8.0
        with:
          write-tests: true
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          args: --budget 0.50
```

For each change no test noticed (3 at most, `--suspects` changes that), a fresh AI worker writes one small test on a
copy of the project. Bite then runs it itself: it must pass twice with the change in, and fail with the change
taken out. Only then does it show up in the comment, folded, ready to paste in. Otherwise Bite throws it away and
says so. `--budget` caps what a run spends ($1 by default). Pull requests from forks don't get secrets, so on those
Bite runs the free check only. On your own computer: `bite --write-tests`.

Every test Bite keeps is also a download: **bite-missing-tests** under Artifacts on the run's page, each file already
in the folder it belongs in.

**One click instead of a paste (opt-in):** add `open-pr: true` and Bite opens a small pull request into your pull
request's branch with the test in it. Click **Merge** there and the test is in. It runs on your workflow's own token,
not on any app, so your workflow needs:

```yaml
permissions:
  contents: write        # Bite puts the test on a branch of its own, bite/missing-tests-<number>
  pull-requests: write
```

and, in your repository, Settings, Actions, General: tick **Allow GitHub Actions to create and approve pull
requests**. Without that tick, Bite still puts the test on its branch and the comment links to open the pull request
yourself. GitHub doesn't run your checks on a pull request a workflow opened, so they run once you merge it into your
branch; Bite has already run the test both ways. Not on pull requests from forks.

## Results for other tools

`bite --json` prints the results as JSON, for scripts, dashboards and other bots; everything else Bite says goes to
stderr. Every run also saves them in `bite_proof/results.json`. These names stay the same from release to release
(a change to them would bump `schema`):

- `outcome`: `noticed` (a test noticed every change), `gaps` (no test noticed at least one), `tests_fail`,
  `no_tests`, `nothing_checked` or `error` (`message` says why).
- `commits`: one per commit checked, with `sha`, `subject`, `result` (`noticed`, `no_test_noticed`,
  `its_tests_didnt_notice`, `tests_fail`, `no_tests` or `skipped`), `label` and `detail` (the words Bite shows),
  and `why` or `missing_test` when there is one.
- `false_done`: each claim the paid step proved false, with `sha`, `subject`, `bug` and `today`.

## Bite-proof badge

When every change Bite checked had a test that noticed it, Bite ends with "Bite-proof. Nice work." and prints a
badge line you can paste into your README:

[![Bite-proof ✅](https://img.shields.io/badge/Bite--proof-%E2%9C%85-black)](https://github.com/connabyss/bite)

Prefer a gentler wording for the warnings? `bite --roast` gives the same results, phrased differently.

## Famous repos Bite has checked

| Project | Language | Changes checked | Noticed by a test | Real gaps |
|---|---|---|---|---|
| [Rich](https://github.com/Textualize/rich) | Python | 37 | 15 | 1 small: [`<kbd>` keys in Markdown](https://github.com/Textualize/rich/commit/a9c4aaba) |
| [Click](https://github.com/pallets/click) | Python | 37 | 30 | 1 small: [`help` on custom setting types](https://github.com/pallets/click/commit/405a5481) |
| [qs](https://github.com/ljharb/qs) | JavaScript | 40 | 40 | none ✅ |
| [chi](https://github.com/go-chi/chi) | Go | 27 | 21 | 2 small: [a test that only works in a terminal](https://github.com/go-chi/chi/commit/878fe71f), [XML compression](https://github.com/go-chi/chi/commit/d7b767bc) |
| [serde_json](https://github.com/serde-rs/json) | Rust | 16 | 12 | none ✅ |
| [FluentValidation](https://github.com/FluentValidation/FluentValidation) | C# | 9 | 5 | none ✅ |

Checked Oct 30-31, 2026 with `bite --free`. Every bug fix Bite could check had a test (one of chi's only works in a terminal). We read each unnoticed change
by hand. Apart from the gaps above, they were things a test can't catch, like type hints, speed-ups, Windows-only
code or rewrites that work the same.

**[The full scoreboard](SCOREBOARD.md)** has 20 projects in 5 languages, with a link to every gap.

## The catch that shows what it's for

In [fellowapp/prosemirror-py](https://github.com/fellowapp/prosemirror-py), commit `3614c96` (co-authored by Claude) says:

> fix: add weakref callback to clean up resolve cache entries
>
> The cache used dict keyed by id(doc) with no cleanup, causing a slow memory leak in long-running processes. Added a weakref finalizer callback that removes the cache entry when the doc is garbage collected.

Bite wrote this test of that claim and ran it:

```python
def test_cache_entry_removed_after_doc_gc():
    resolvedpos._resolve_cache.clear()
    d = doc(p("hello"))
    ResolvedPos.resolve_cached(d, 2)
    assert len(resolvedpos._resolve_cache) == 1
    del d
    gc.collect()
    assert len(resolvedpos._resolve_cache) == 0   # fails: 1 == 0
```

It fails on that commit and on today's code. The cache keeps each document alive through its cached positions, so the cleanup never runs. After 20,000 documents are resolved and dropped, the cache still holds all 20,000, using 35 MB. The commit looked right, read right, and passed its own tests. Reported with a repro in [#335](https://github.com/fellowapp/prosemirror-py/issues/335); a tested fix is open as [#336](https://github.com/fellowapp/prosemirror-py/pull/336).

## Fixed or merged upstream

Each bug was reproduced with a standalone script in a clean environment before it was reported.

| Project | What happened |
|---|---|
| pyclibrary | 7 bugs reported in [#92](https://github.com/MatthieuDartiailh/pyclibrary/issues/92). All 7 fixes reviewed and merged: [#93](https://github.com/MatthieuDartiailh/pyclibrary/pull/93), [#94](https://github.com/MatthieuDartiailh/pyclibrary/pull/94), [#95](https://github.com/MatthieuDartiailh/pyclibrary/pull/95), [#96](https://github.com/MatthieuDartiailh/pyclibrary/pull/96), [#97](https://github.com/MatthieuDartiailh/pyclibrary/pull/97), [#98](https://github.com/MatthieuDartiailh/pyclibrary/pull/98), [#99](https://github.com/MatthieuDartiailh/pyclibrary/pull/99). The maintainer [wrote](https://github.com/MatthieuDartiailh/pyclibrary/issues/92): "Thanks for the small and focused PR very nice to review." |
| django-tailwind-cli | With one stylesheet, `tailwind watch` hid rebuild messages and build errors. Fix [#232](https://github.com/django-commons/django-tailwind-cli/pull/232) merged and released in [4.8.2](https://github.com/django-commons/django-tailwind-cli/releases/tag/v4.8.2). The maintainer [wrote](https://github.com/django-commons/django-tailwind-cli/pull/232): "Just about to release 4.8.2 with the fix included. Thanks for the contribution." |
| srptools | 4 bugs reported in [#13](https://github.com/idlesign/srptools/issues/13). The maintainer fixed all 4 and closed it the same day. |
| resolve-robotics-uri-py | URI lookup depended on the hash seed ([#26](https://github.com/gbionics/resolve-robotics-uri-py/issues/26)). Fixed by the maintainers in [#27](https://github.com/gbionics/resolve-robotics-uri-py/pull/27). The maintainer [wrote](https://github.com/gbionics/resolve-robotics-uri-py/issues/26): "Thanks a lot for the detailed issue report!" |
| text-to-cad | A Claude commit added a Python 3.11 syntax check that can't catch the exact bug it was written for (nested same-quote f-strings). Bite sent a test that does catch it, [#708](https://github.com/earthtojake/text-to-cad/pull/708), was merged and released in [0.8.2](https://github.com/earthtojake/text-to-cad/releases/tag/v0.8.2); the maintainer then closed the remaining gaps in [#712](https://github.com/earthtojake/text-to-cad/pull/712). |
| west | Loading a manifest from data with a reserved project name crashed. Fix [#1013](https://github.com/zephyrproject-rtos/west/pull/1013) approved by two maintainers and merged. |
| midea-lan | A message encoder got the frame length wrong when no padding was needed. Fix [#251](https://github.com/wuwentao/midea-lan/pull/251) merged. The maintainer [wrote](https://github.com/wuwentao/midea-lan/pull/251): "Thank you @connabyss for submitting this PR and for finding and fixing the 8370 framing bug." |
| mizani | Number labels picked too few decimals when values were close together (`[0, 10, 10.5]` showed as `10, 10`). Fix [#90](https://github.com/has2k1/mizani/pull/90) merged. The maintainer [wrote](https://github.com/has2k1/mizani/pull/90): "@connabyss, thank you." |
| pamqp | Bite's free check found three past fixes that no test would notice breaking, including one where `Basic.Reject(requeue=False)` was flipped back to `True`. Tests for all three ([#86](https://github.com/gmr/pamqp/pull/86)) merged. |

## Sent, waiting for review

| Project | Link | What happened |
|---|---|---|
| prosemirror-py | [#335](https://github.com/fellowapp/prosemirror-py/issues/335), [#336](https://github.com/fellowapp/prosemirror-py/pull/336), [#337](https://github.com/fellowapp/prosemirror-py/pull/337) | The leak above. A second Claude commit (`1e3339e`) let `Mapping` change a list the caller still owned; fix in #337. |
| python-vcr-tests | [#18](https://github.com/keboola/python-vcr-tests/issues/18), [#19](https://github.com/keboola/python-vcr-tests/pull/19) | A Claude commit said its database recorder captures every query; only the last per cursor is saved. |
| ChatSBOM | [#217](https://github.com/WangYihang/ChatSBOM/issues/217) | A Claude commit's stale-result guard is reset on every walk page, so a repo can be collected twice. |
| llm | [#1828](https://github.com/simonw/llm/pull/1828) | A Claude commit fixed per-turn tool ids in `llm logs`, but its test never made a tool call, so it passed even with the bug. |
| treg | [#1237](https://github.com/superdesigndev/treg/pull/1237) | A Claude commit's test for an org header passes even with the fix removed, so it guards nothing. |
| claude-seo | [#392](https://github.com/AgriciDaniel/claude-seo/pull/392) | A Claude commit's `--release` check let a value with a trailing newline through. |
| marshmallow-fastoneofschema | [#1](https://github.com/Kalepa/marshmallow-fastoneofschema/issues/1), [#2](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/2), [#3](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/3), [#4](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/4) | 3 bugs, one fix each. |
| django-modeltranslation | [#831](https://github.com/deschler/django-modeltranslation/pull/831) | Nested `auto_populate()` and `fallbacks()` blocks reset the setting to nothing on exit instead of restoring it. |
| mypy_boto3_builder | [#395](https://github.com/youtype/mypy_boto3_builder/issues/395) | Reported, no reply yet. |
| drf-pydantic | [#51](https://github.com/georgebv/drf-pydantic/issues/51) | Reported, no reply yet. |

## Limits, plainly

- **Most claims hold.** Across all rounds so far, Bite tested 137 "fixed" claims that it could run tests for (all from commits made with Claude Code, the AI those rounds looked at). 8 were false (about 1 in 17), and 4 of those were still broken on today's code. On well-reviewed projects it usually finds nothing, and that's the right answer.
- **Quiet is not a pass.** Bite only shows a failing test that the second check calls fair and real. That second check has thrown out more than 10 failing tests that weren't. A claim that holds proves that one claim, not that the commit has no other bugs.
- **It needs the project's tests to run.** If they don't run on a clean copy, Bite can't check that commit.
- **Bug hunting is weaker than claim checking.** In a 10-project overnight hunt, two blind AI judges rated 21 of 22 proven fixes as real bugs and none as wrong, but Bite found only 1 of the 10 bugs the maintainers fixed soon after.
- **Small samples, AI judges.** The judges read code without running it. The human checks are the maintainers' fixes and merges listed above.

## Contributing

Bug reports, fixes and AI-assisted PRs are all welcome. See [CONTRIBUTING.md](https://github.com/connabyss/bite/blob/main/CONTRIBUTING.md). If Bite flagged
something wrongly, or missed a claim you know was false, please [open an issue](https://github.com/connabyss/bite/issues/new/choose).

Thank you to Bite's first contributors:

- [@snehaapratap](https://github.com/snehaapratap) made the setup error messages point to steps that exist ([#18](https://github.com/connabyss/bite/pull/18)).
- [@gauravjangra3165](https://github.com/gauravjangra3165) added macOS to the tests ([#19](https://github.com/connabyss/bite/pull/19)).
- [@bfs2021](https://github.com/bfs2021) made the "check it yourself" steps work for commits that add a new file ([#37](https://github.com/connabyss/bite/pull/37), fixing [#27](https://github.com/connabyss/bite/issues/27)).

MIT licensed.
