"""The Action's badge step: puts bite_proof/badge.json (the Bite score, in shields.io's endpoint format) on a branch of
its own, so a README badge can follow the newest run:

    https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/OWNER/REPO/BRANCH/badge.json

Runs with the workflow's own token (contents write). Talks to GitHub through the `gh` command; standard library only.
Never touches a branch that holds anything but badge.json, and never fails the check: a problem is a warning."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

BADGE = Path("bite_proof/badge.json")


def api(method: str, path: str, body=None):
    r = subprocess.run(["gh", "api", "-X", method, path] + (["--input", "-"] if body is not None else []),
                       input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr).strip()[:300])
    return json.loads(r.stdout or "null")


def badge_url(repo: str, branch: str) -> str:
    raw = f"https://raw.githubusercontent.com/{repo}/{quote(branch, safe='')}/badge.json"
    return f"https://img.shields.io/endpoint?url={quote(raw, safe='')}"


def publish(repo: str, branch: str, text: str, call=api) -> str:
    """Commits text as badge.json on branch (made if missing, with no history of the project's own). Returns what
    happened, in words: "unchanged", "updated" or "made"."""
    ref = f"repos/{repo}/git/ref/heads/{quote(branch, safe='/')}"
    try:
        head = call("GET", ref)["object"]["sha"]
    except RuntimeError as err:
        if "404" not in str(err) and "Not Found" not in str(err):
            raise
        head = None
    if head:
        tree = call("GET", f"repos/{repo}/git/trees/{head}")["tree"]
        names = {t["path"] for t in tree}
        if names - {"badge.json"}:
            raise RuntimeError(f"the branch {branch} holds other files, so Bite leaves it alone: pick a new "
                               "badge-branch name (Bite makes it)")
        old = next((t for t in tree if t["path"] == "badge.json"), None)
        was = call("GET", f"repos/{repo}/git/blobs/{old['sha']}").get("content", "") if old else ""
        if old and base64.b64decode(was).decode("utf-8", "replace") == text:
            return "unchanged"
    new_tree = call("POST", f"repos/{repo}/git/trees",
                    {"tree": [{"path": "badge.json", "mode": "100644", "type": "blob", "content": text}]})["sha"]
    msg = "Bite score: " + json.loads(text).get("message", "")
    commit = call("POST", f"repos/{repo}/git/commits",
                  {"message": msg, "tree": new_tree, "parents": [head] if head else []})["sha"]
    if head:
        call("PATCH", ref, {"sha": commit})
        return "updated"
    call("POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
    return "made"


def main() -> int:
    repo, branch = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("BADGE_BRANCH", "")
    if not (repo and branch):
        return 0
    if not BADGE.is_file():
        print("Bite: no score this run (nothing it could check), so the badge stays as it was.")
        return 0
    try:
        done = publish(repo, branch, BADGE.read_text(encoding="utf-8"))
    except (RuntimeError, KeyError, ValueError) as err:
        print(f"::warning::Bite couldn't update its badge: {err}")
        return 0
    url = badge_url(repo, branch)
    print(f"Bite: score badge {done} on branch {branch}. For your README:\n"
          f"[![Bite score]({url})](https://github.com/connabyss/bite)")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"\nBite score badge ({done}), for your README:\n\n```\n[![Bite score]({url})]"
                    "(https://github.com/connabyss/bite)\n```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
