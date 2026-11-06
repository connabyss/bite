# Bite on every pull request

[← Back to the README](https://github.com/connabyss/bite#readme)

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
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      # install what your tests need here, e.g. for Python:
      - uses: actions/setup-python@v7
      - run: python -m pip install pytest -r requirements.txt
      - uses: connabyss/bite@v1.0.7
```

Options go under `with:`: `args` (extra `bite` options, e.g. `--serious`), `max-commits` (default 20),
`fail-on-gap` (set to `false` to report without failing) and `comment` (set to `false` for no comment). It posts one comment on the pull request that says, per
commit, whether a test noticed the change being taken out, and updates that same comment on later pushes. The
rerun steps for each flagged commit are on the job's summary page.

### Have Bite write the missing test (opt-in, your own key)

When no test noticed a change, Bite can write that test for you. Add your Anthropic API key as a repository secret
named `ANTHROPIC_API_KEY`, then:

```yaml
      - uses: connabyss/bite@v1.0.7
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
