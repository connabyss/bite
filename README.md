<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-header-dark.png">
  <img alt="Bite" src="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-header-light.png" width="280">
</picture>

### Would your tests catch it if the bug came back?

Bite checks whether an AI coding agent's "fixed" is actually true.<br>
It takes each fix back out of a copy of your project and runs your tests. Free, no key.

[![PyPI](https://img.shields.io/pypi/v/bite-check?label=PyPI&color=24292f)](https://pypi.org/project/bite-check/)
[![Python](https://img.shields.io/badge/python-3.10%2B-24292f)](https://pypi.org/project/bite-check/)
[![Tests](https://img.shields.io/github/actions/workflow/status/connabyss/bite/tests.yml?branch=main&label=tests)](https://github.com/connabyss/bite/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-24292f)](https://github.com/connabyss/bite/blob/main/LICENSE)

[Try it](#try-it-now) · [Install guide](https://github.com/connabyss/bite/blob/main/docs/install.md) · [GitHub Action](https://github.com/connabyss/bite/blob/main/docs/pull-requests.md) · [Changelog](https://github.com/connabyss/bite/blob/main/CHANGELOG.md) · [Discussions](https://github.com/connabyss/bite/discussions) · [Contribute](https://github.com/connabyss/bite/blob/main/CONTRIBUTING.md)

<sub>Read this in: [Tiếng Việt](https://github.com/connabyss/bite/blob/main/docs/i18n/README.vi.md) · [Español](https://github.com/connabyss/bite/blob/main/docs/i18n/README.es.md) · [简体中文](https://github.com/connabyss/bite/blob/main/docs/i18n/README.zh-CN.md)</sub>

</div>

<br>

<img alt="bite --demo: one fix is noticed by a test, the other has no test at all" src="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-demo.svg" width="760">

## Try it now

Free, no key, and it never changes your files. You need Python 3.10 or newer and git. Paste these two lines into
any terminal (PowerShell, cmd, Terminal):

```
python -m pip install bite-check
python -m bite_check --free
```

Outside a project, Bite first shows a demo on a tiny made-up one. To check your own project, type the second line
and a space, drag your project's folder into the window (that types its path), and press Enter.

Other ways: `pipx run bite-check --free` or `uvx bite-check --free` (one line, no install; on Linux or a Mac, use one
of these if pip says "externally managed"). Commits never say "fix"? Add `--any`. To keep a `bite` command installed:
[install guide](https://github.com/connabyss/bite/blob/main/docs/install.md).

## Why you need this

When an AI fixes a bug for you, it often says "Fixed, and I added a test." If you don't read code, you can't tell
if that's true.

A test is a tiny robot that checks one thing and shouts when it's wrong. Bite puts the old bug back on purpose and
watches whether any test shouts. It's like testing a smoke alarm with real smoke instead of trusting the little
green light.

If a test shouts, that fix is guarded. If they all stay quiet, the bug could come back and nobody would notice.
Bite names that fix, so you can tell your AI: "add a test that fails without this fix."

`bite --demo` shows both cases on a tiny made-up shop:

```
  9661edcf ✅ noticed by test_discount_never_below_zero Fix discounts over 100% making the price negative
  e5c329ec ⚠️ NO TEST NOTICED           Fix totals showing long decimals like 0.30000000000000004
```

> **Bite does this:** takes each recent fix back out of a copy of your project, runs your tests, and tells you
> whether any test noticed. It never changes your files or pushes anything.
>
> **You decide that:** whether to add the missing test, or leave it because the change didn't need one (a rename,
> a tidy-up). A ✅ means a test would catch that fix breaking. It doesn't prove the code has no other bugs.

Works with pytest, npm test, cargo test, go test, dotnet test, Maven and Gradle (Java and Kotlin).
Full list: [SUPPORTS.md](https://github.com/connabyss/bite/blob/main/SUPPORTS.md).
How Bite differs from coverage and mutation testing: [Bite, mutmut and coverage](https://github.com/connabyss/bite/blob/main/docs/comparison.md).

## Everything else Bite can do

| What | How | More |
|---|---|---|
| Check every pull request | Add the GitHub Action (below) or the [bite-check app](https://github.com/apps/bite-check) | [Pull requests](https://github.com/connabyss/bite/blob/main/docs/pull-requests.md) |
| Check Claude's "fixed" the moment it says it | `/plugin marketplace add connabyss/bite`, then `/plugin install bite-check@bite` (and `fixed-or-not@bite` for the skill and `/bite`) | [Live checks](https://github.com/connabyss/bite/blob/main/docs/live.md) |
| Same, in Cursor, Copilot, Codex, Windsurf, Gemini CLI | `bite mcp` | [Live checks](https://github.com/connabyss/bite/blob/main/docs/live.md#check-the-fixed-live-in-any-coding-ai) |
| Teach any coding AI to prove its fixes (a free skill) | `npx skills add connabyss/bite` | [The skill](https://github.com/connabyss/bite/blob/main/skills/bite-verify-fix/SKILL.md) · also [on Agensi](https://www.agensi.io/skills/bite-verify-ai-fixes) |
| Ask in plain words | `bite ask "is last week's login fix guarded?"` | [Ask](https://github.com/connabyss/bite/blob/main/docs/ask.md) |
| Catch a fix a later commit quietly undid | Built into every free check | [Comeback alarm](https://github.com/connabyss/bite/blob/main/docs/comeback.md) |
| Write the missing test (your own key) | `bite --write-tests` | [Write tests](https://github.com/connabyss/bite/blob/main/docs/pull-requests.md#have-bite-write-the-missing-test-opt-in-your-own-key) |
| Score, badge, JSON for scripts | `bite --json` | [Score and results](https://github.com/connabyss/bite/blob/main/docs/score-and-results.md) |
| Speed up a slow check | `bite --free --jobs 4` (not with pytest `-n auto`: it's slower) | [When a check is slow](https://github.com/connabyss/bite/blob/main/docs/install.md#when-a-check-is-slow) |

**The pull request check.** Add this as `.github/workflows/bite.yml`. It runs the free check on each pull
request's commits and fails when a change can be taken back out and your tests still pass. No key, no cost.

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
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      # install what your tests need here, e.g. for Python:
      - uses: actions/setup-python@v7
      - run: python -m pip install pytest -r requirements.txt
      - uses: connabyss/bite@v1.0.8
```

**The paid step (optional).** With your own Anthropic API key, Bite writes one small test of a commit's exact
claim and runs it; `--budget` caps what a run spends ($1 by default). It runs on Anthropic's Agent SDK, so it needs
an API key and never uses a Claude login or plan (Anthropic's Agent SDK rule:
https://code.claude.com/docs/en/agent-sdk/overview). Setup: [install guide](https://github.com/connabyss/bite/blob/main/docs/install.md).

## Updating Bite

`bite --version` says when a newer one is out. This line always gets the newest version:

```
pipx install --force bite-check --pip-args="--no-cache-dir"
```

Installed with pip? `python -m pip install --upgrade --no-cache-dir bite-check`. Why not `pipx upgrade`:
[install guide](https://github.com/connabyss/bite/blob/main/docs/install.md#updating-bite). What changed: [CHANGELOG.md](https://github.com/connabyss/bite/blob/main/CHANGELOG.md).

## Does it work?

In [prosemirror-py](https://github.com/fellowapp/prosemirror-py), a Claude commit said it fixed a memory leak.
Bite wrote a test of that claim: it fails on that commit and on today's code. After 20,000 documents the cache
still held all 20,000, using 35 MB. The tested fix was merged upstream. ([The full story](https://github.com/connabyss/bite/blob/main/docs/track-record.md#the-catch-that-shows-what-its-for).)

> "Reverting the claimed fix and making the change prove itself under a real test is exactly the kind of check that
> should exist for every "fixed" commit."
>
> — [Ivan Zdravkov](https://zdravkov.info), [on DEV](https://dev.to/izdravkov/comment/3jdej)

Famous repos Bite has checked with `bite --free` (Oct 30-31, 2026):

| Project | Language | Changes checked | Noticed by a test | Real gaps |
|---|---|---|---|---|
| [Rich](https://github.com/Textualize/rich) | Python | 37 | 15 | 1 small: [`<kbd>` keys in Markdown](https://github.com/Textualize/rich/commit/a9c4aaba) |
| [Click](https://github.com/pallets/click) | Python | 37 | 30 | 1 small: [`help` on custom setting types](https://github.com/pallets/click/commit/405a5481) |
| [qs](https://github.com/ljharb/qs) | JavaScript | 40 | 40 | none ✅ |
| [chi](https://github.com/go-chi/chi) | Go | 27 | 22 | 1 small: [XML compression](https://github.com/go-chi/chi/commit/d7b767bc) |
| [serde_json](https://github.com/serde-rs/json) | Rust | 16 | 12 | none ✅ |
| [FluentValidation](https://github.com/FluentValidation/FluentValidation) | C# | 9 | 5 | none ✅ |

More: [the full scoreboard](https://github.com/connabyss/bite/blob/main/SCOREBOARD.md) (20 projects, 5 languages),
and [bugs fixed or merged upstream](https://github.com/connabyss/bite/blob/main/docs/track-record.md#fixed-or-merged-upstream) in pyclibrary,
drf-pydantic, django-tailwind-cli, west, mizani, pamqp and more.

Bite is listed on [awesome-python-testing](https://github.com/cleder/awesome-python-testing) and
[awesome-testing](https://github.com/TheJambo/awesome-testing).

## Limits, plainly

- **Most claims hold.** Across all rounds so far, Bite tested 137 "fixed" claims that it could run tests for (all from commits made with Claude Code, the AI those rounds looked at). 8 were false (about 1 in 17), and 4 of those were still broken on today's code. On well-reviewed projects it usually finds nothing, and that's the right answer.
- **Quiet is not a pass.** Bite only shows a failing test that the second check calls fair and real. That second check has thrown out more than 10 failing tests that weren't. A claim that holds proves that one claim, not that the commit has no other bugs.
- **It needs the project's tests to run.** If they don't run on a clean copy, Bite can't check that commit.
- **Bug hunting is weaker than claim checking.** In a 10-project overnight hunt, two blind AI judges rated 21 of 22 proven fixes as real bugs and none as wrong, but Bite found only 1 of the 10 bugs the maintainers fixed soon after.
- **Small samples, AI judges.** The judges read code without running it. The human checks are the maintainers' fixes and merges listed above.

## Join in

**Looking for your first open-source PR?** These [good first issues](https://github.com/connabyss/bite/labels/good%20first%20issue)
are small, and each one says where to look and when it's done. Comment on one to claim it. Or try to
[fool Bite](https://github.com/connabyss/bite/issues/156): sneak a "fix" past it.

> 🏆 **Fooled Bite: nobody yet.** Be the first: your name, your trick, and the test that now catches it go right
> here. ([How to enter](https://github.com/connabyss/bite/blob/main/TRICKS.md#your-turn-fool-bite). Bite's own 2 known blind spots are in
> [Still fools Bite](https://github.com/connabyss/bite/blob/main/TRICKS.md#still-fools-bite), so they don't count.)

Bug reports, fixes and AI-assisted PRs are all welcome: [CONTRIBUTING.md](https://github.com/connabyss/bite/blob/main/CONTRIBUTING.md)
has the one-minute setup. If Bite flagged something wrongly, or missed a claim you know was false, please
[open an issue](https://github.com/connabyss/bite/issues/new/choose). Questions and ideas go in
[Discussions](https://github.com/connabyss/bite/discussions).

## Made by these people

Thank you to everyone who has helped make Bite. Want to be here? Pick a
[good first issue](https://github.com/connabyss/bite/labels/good%20first%20issue).

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/snehaapratap"><img src="https://avatars.githubusercontent.com/u/170080122?v=4?s=80" width="80px;" alt="snehaapratap"/><br /><sub><b>snehaapratap</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=snehaapratap" title="Code">💻</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/gauravjangra3165"><img src="https://avatars.githubusercontent.com/u/300753752?v=4?s=80" width="80px;" alt="gauravjangra3165"/><br /><sub><b>gauravjangra3165</b></sub></a><br /><a href="#infra-gauravjangra3165" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/bfs2021"><img src="https://avatars.githubusercontent.com/u/101915083?v=4?s=80" width="80px;" alt="bfs2021"/><br /><sub><b>bfs2021</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=bfs2021" title="Code">💻</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/HarshRajSinghania"><img src="https://avatars.githubusercontent.com/u/40535627?v=4?s=80" width="80px;" alt="HarshRajSinghania"/><br /><sub><b>HarshRajSinghania</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=HarshRajSinghania" title="Code">💻</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/hrithiksaini99"><img src="https://avatars.githubusercontent.com/u/49943287?v=4?s=80" width="80px;" alt="hrithiksaini99"/><br /><sub><b>hrithiksaini99</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=hrithiksaini99" title="Code">💻</a> <a href="https://github.com/connabyss/bite/commits?author=hrithiksaini99" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/The-Aizen-404"><img src="https://avatars.githubusercontent.com/u/245661236?v=4?s=80" width="80px;" alt="The-Aizen-404"/><br /><sub><b>The-Aizen-404</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=The-Aizen-404" title="Code">💻</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/SatriaBagusNurhadianto"><img src="https://avatars.githubusercontent.com/u/237350863?v=4?s=80" width="80px;" alt="SatriaBagusNurhadianto"/><br /><sub><b>SatriaBagusNurhadianto</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=SatriaBagusNurhadianto" title="Code">💻</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/hamid-digitalmarketer"><img src="https://avatars.githubusercontent.com/u/341071524?v=4?s=80" width="80px;" alt="hamid-digitalmarketer"/><br /><sub><b>hamid-digitalmarketer</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=hamid-digitalmarketer" title="Code">💻</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/zheng-guannan577"><img src="https://avatars.githubusercontent.com/u/349123998?v=4?s=80" width="80px;" alt="zheng-guannan577"/><br /><sub><b>zheng-guannan577</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=zheng-guannan577" title="Code">💻</a></td>
      <td align="center" valign="top" width="16.66%"><a href="https://github.com/AneesFathima-A"><img src="https://avatars.githubusercontent.com/u/158535421?v=4?s=80" width="80px;" alt="AneesFathima-A"/><br /><sub><b>AneesFathima-A</b></sub></a><br /><a href="https://github.com/connabyss/bite/commits?author=AneesFathima-A" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

---

Also by me: [Cold Case Unit](https://connabyss.github.io/cold-case/), which opens a murder case on every GitHub project its owner walked away from.

MIT licensed.
