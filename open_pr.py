"""The Action's open-pr step: puts the tests Bite wrote (bite_proof/missing_tests/) on a branch of their own and opens a
pull request with them into the checked pull request's branch, so the owner adds them with one click on Merge.
Runs with the workflow's own token (contents and pull-requests write), never the bite-check app's. Talks to GitHub
through the `gh` command; standard library only. Never fails the check: a problem is a warning."""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

TESTS = Path("bite_proof/missing_tests")
COMMENT = Path("bite_proof/COMMENT.md")


def api(method: str, path: str, body=None):
    r = subprocess.run(["gh", "api", "-X", method, path] + (["--input", "-"] if body is not None else []),
                       input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr).strip()[:300])
    return json.loads(r.stdout or "null")


def add_to_comment(line: str) -> None:
    """One line in Bite's comment, above its closing "How Bite checks" fold."""
    if not COMMENT.is_file():
        return
    text = COMMENT.read_text(encoding="utf-8")
    fold = "\n<details><summary>How Bite checks</summary>"
    COMMENT.write_text(text.replace(fold, f"\n{line}\n{fold}", 1) if fold in text else text + f"\n{line}\n",
                       encoding="utf-8")


def main() -> int:
    files = sorted(p.relative_to(TESTS).as_posix() for p in TESTS.rglob("*") if p.is_file()) if TESTS.is_dir() else []
    if not files:
        return 0
    repo, pr = os.environ["GITHUB_REPOSITORY"], os.environ["PR"]
    head_sha, head_ref = os.environ["HEAD_SHA"], os.environ["HEAD_REF"]
    if os.environ.get("HEAD_REPO", repo) != repo:
        print("::warning::Bite: this pull request comes from a fork, so Bite can't open a pull request into its branch. "
              "The test is in the comment and in the download.")
        return 0
    one = len(files) == 1
    try:
        tree = api("GET", f"repos/{repo}/git/commits/{head_sha}")["tree"]["sha"]
        tree = api("POST", f"repos/{repo}/git/trees", {"base_tree": tree, "tree": [
            {"path": f, "mode": "100644", "type": "blob", "content": (TESTS / f).read_text(encoding="utf-8")}
            for f in files]})["sha"]
        commit = api("POST", f"repos/{repo}/git/commits", {
            "message": f"Add the missing test{'' if one else 's'} Bite wrote for #{pr}\n\n"
                       "Bite ran each one: it passes with the change and fails with the change taken out.",
            "tree": tree, "parents": [head_sha]})["sha"]
        branch = f"bite/missing-tests-{pr}"
        try:  # Bite's own branch: a later push to the pull request moves it onto the newest commit
            api("PATCH", f"repos/{repo}/git/refs/heads/{branch}", {"sha": commit, "force": True})
        except RuntimeError:
            api("POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
    except (RuntimeError, KeyError, TypeError) as e:
        print(f"::warning::Bite couldn't put the test on a branch (the workflow needs permissions: contents: write): {e}")
        return 0
    it, them = ("it", "the test") if one else ("them", "the tests")
    owner = repo.split("/")[0]
    try:
        open_now = api("GET", f"repos/{repo}/pulls?state=open&head={quote(owner)}:{quote(branch, safe='')}")
        num = open_now[0]["number"] if open_now else api("POST", f"repos/{repo}/pulls", {
            "title": f"Bite: add the missing test{'' if one else 's'} for #{pr}", "head": branch, "base": head_ref,
            "body": f"Bite found {'a change' if one else 'changes'} in #{pr} that no test noticed, and wrote {them}. "
                    f"Bite ran {'it' if one else 'each one'} itself: it passes with the change and fails with the "
                    "change taken out.\n\n" + "\n".join(f"- `{f}`" for f in files) + "\n\n"
                    f"Merging this adds {it} to the branch of #{pr}. GitHub doesn't start checks on a pull request "
                    f"that a workflow opened, so your checks run on #{pr} once you merge this.\n\n"
                    "[What is Bite?](https://github.com/connabyss/bite)"})["number"]
    except (RuntimeError, KeyError, TypeError, IndexError) as e:
        url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/compare/{quote(head_ref, safe='')}...{quote(branch, safe='')}?expand=1"
        print(f"::warning::Bite put {them} on branch {branch} but couldn't open the pull request. It needs "
              "permissions: pull-requests: write, and Settings, Actions, General: \"Allow GitHub Actions to create "
              f"and approve pull requests\". {e}")
        add_to_comment(f"🧪 Bite put {them} on branch `{branch}`: [open a pull request from it]({url}).")
        return 0
    print(f"Bite opened #{num} with {them}.")
    add_to_comment(f"🧪 Bite opened #{num} with {them}: merge it to add {it} to this branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
