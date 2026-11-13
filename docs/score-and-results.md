# Score, badges and results for other tools

[← Back to the README](https://github.com/connabyss/bite#readme)

## Bite-proof badge

When every change Bite checked had a test that noticed it, Bite ends with "Bite-proof. Nice work." and prints a
badge line you can paste into your README:

[![Bite-proof ✅](https://img.shields.io/badge/Bite--proof-%E2%9C%85-black)](https://github.com/connabyss/bite)

## Bite score

Every run ends with a score: of the changes Bite could check, how many a test noticed ("Bite score: 7/9"). Changes
it skipped, or couldn't check because the tests already fail, don't count either way. The report page shows it as
a ring, and the pull request comment adds it in one small line. Bite also prints a badge line with the score, for
your README:

[![Bite score: 7 of 9 changes noticed by a test](https://img.shields.io/badge/Bite%20score-7%2F9%20noticed-yellowgreen)](https://github.com/connabyss/bite)

Next to the report page, `bite_proof/card.svg` is the score as a picture (1200x630, the size link previews use), with
the Bite cat, to drop into a post or a chat.

Bite remembers each run's score in `bite_proof/scores.json` and says how it moved: "up from 5/9 last run", "down
from 8/9 last run", or "Bite-proof 3 runs in a row". A rerun at the same commit doesn't count twice, and pull request
checks (`--since`) aren't remembered, since they look at different commits.

Each run also saves `bite_proof/badge.json` in [shields.io's endpoint format](https://shields.io/badges/endpoint-badge),
so a badge can follow your newest run wherever you publish that file.

**A badge that keeps itself up to date (the Action, opt-in):** on every push to main, Bite checks your newest commits
and keeps the score on a branch of its own, `bite-badge`, which holds only `badge.json`. Add this as
`.github/workflows/bite-badge.yml`:

```yaml
name: bite-badge
on:
  push:
    branches: [main]
permissions:
  contents: write        # only for the bite-badge branch
jobs:
  badge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      # install what your tests need here, as in the pull request check
      - uses: connabyss/bite@v1.0.8
        with:
          badge-branch: bite-badge
          max-commits: 10
```

The job's summary page then shows the badge line for your README (put your own owner/repo in it):

```
[![Bite score](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FOWNER%2FREPO%2Fbite-badge%2Fbadge.json)](https://github.com/connabyss/bite)
```

Bite makes the branch on the first run, and never touches a branch that holds anything else. On a push run the check
never fails; it only updates the badge.

Prefer a gentler wording for the warnings? `bite --roast` gives the same results, phrased differently.

In a hurry? `bite --quick` checks each change with two test runs, as older versions did: it skips the piece-by-piece
check, the flaky-test rerun and the deleted-test check ([TRICKS.md](https://github.com/connabyss/bite/blob/main/TRICKS.md) says what those catch).

## Results for other tools

`bite --json` prints the results as JSON, for scripts, dashboards and other bots; everything else Bite says goes to
stderr. Every run also saves them in `bite_proof/results.json`. These names stay the same from release to release
(a change to them would bump `schema`):

- `outcome`: `noticed` (a test noticed every change), `gaps` (no test noticed at least one), `undone_later` (a
  later commit put the old code back for at least one fix), `tests_fail`, `no_tests`, `nothing_checked` or `error`
  (`message` says why).
- `commits`: one per commit checked, with `sha`, `subject`, `result` (`noticed`, `no_test_noticed`,
  `its_tests_didnt_notice`, `undone_later`, `tests_fail`, `no_tests` or `skipped`), `label` and `detail` (the words
  Bite shows), and `why`, `missing_test` or `undone_by` (`sha` and `subject` of the commit that undid it) when there
  is one.
- `false_done`: each claim the paid step proved false, with `sha`, `subject`, `bug` and `today`.
- `score`: the Bite score (above), with `noticed`, `out_of` and `badge` (a README badge line). Left out when no
  change could be checked.

A commit that bundles a tested change with an untested one gets `no_test_noticed` with the label PART NOT NOTICED,
and its `detail` names the part. [TRICKS.md](https://github.com/connabyss/bite/blob/main/TRICKS.md) has that and the other tricks we tried on Bite.
