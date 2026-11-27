# The bite-check app's welcome bot

`welcome.py` runs once an hour (`.github/workflows/bot.yml`). For each repo the bite-check app was newly installed
on, it opens one issue with an "Add Bite" link. The link opens GitHub's new-file page with `.github/workflows/bite.yml`
filled in for the repo's main language; the owner reads it and clicks **Commit changes**.

## Safety

- The app has one permission: **Issues: read and write**. Each run also asks GitHub for an issues-only token.
- The app's private key (`BITE_APP_KEY`) lives only in this repo's **bot** environment, which only `main` can use.
  Pull request checks and forks can't read it. It is not a repository secret.
- The workflow has no token permissions of its own, uses only `actions/checkout` pinned to an exact commit, and the
  script uses only Python's standard library and the `openssl` command.
- Installs on more than 10 repos at once get no issues, so nobody gets flooded. A repo never gets a second issue,
  even after the first is closed.
- Try it safely: Actions, **bot**, **Run workflow** with "Only print what it would post" checked (the default).

## If the key leaks

1. App settings (github.com/settings/apps/bite-check), private keys: **Generate a private key**. A .pem file downloads.
2. Delete the old key there.
3. Repo Settings, Environments, **bot**, edit `BITE_APP_KEY`, paste the whole new .pem file.
4. Delete the downloaded .pem from your computer.

With issues-only permission, the worst a leaked key could do is post issues on repos where the app is installed.

# Bite checks Bite

`self_check.py` runs every Monday and on **Run workflow** (`.github/workflows/self-check.yml`). Bite runs its free
check on this repo's own recent commits. When a change no test noticed turns up, it opens an issue about it. With the
repository secret `ANTHROPIC_API_KEY` set, Bite also writes the missing test (`--write-tests --budget 0.50`), keeps it
only if it fails with the change taken out, and opens a pull request into `main` that adds it and closes the issue.

- It uses the workflow's own token, never the app's key. It needs Settings, Actions, General: "Allow GitHub Actions to
  create and approve pull requests".
- Before opening the pull request, Bite asks its own test its own question: on today's `main` (or at the gap's own
  commit, when the code has moved on), the test passes, and with the gap's change taken out, it fails. The answer
  shows on the pull request as the check **Bite / own test**. A test that doesn't notice gets no pull request.
- GitHub doesn't start checks on a pull request a workflow opened, so `self_check.py` starts the tests workflow on it.
- Each gap is reported once, even after its issue is closed. While its issue is still open, a later run that writes
  the test (say `ANTHROPIC_API_KEY` was added since) opens the pull request that closes it. No gap: nothing opened, and nothing spent.
