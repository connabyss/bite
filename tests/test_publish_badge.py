"""The live score badge: on a push with badge-branch set, the Action checks the newest commits and keeps
bite_proof/badge.json on a branch of its own. GitHub is a stand-in here; no network."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import publish_badge  # noqa: E402
from test_action import BASH, action_script  # noqa: E402

TEXT = json.dumps({"schemaVersion": 1, "label": "Bite score", "message": "3/4 noticed", "color": "yellowgreen"})


class FakeGitHub:
    def __init__(self, branch=None):
        self.branch, self.calls = branch, []  # branch: {"files": {path: text}} or None

    def __call__(self, method, path, body=None):
        self.calls.append((method, path.split("/git/")[-1] if "/git/" in path else path, body))
        if method == "GET" and "/git/ref/heads/" in path:
            if self.branch is None:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            return {"object": {"sha": "head1"}}
        if method == "GET" and "/git/trees/" in path:
            return {"tree": [{"path": p, "sha": "blob-" + p} for p in self.branch["files"]]}
        if method == "GET" and "/git/blobs/" in path:
            return {"content": base64.b64encode(self.branch["files"]["badge.json"].encode()).decode()}
        return {"sha": method + "-new"}


def test_makes_the_branch_with_only_the_badge():
    gh = FakeGitHub()
    assert publish_badge.publish("o/r", "bite-badge", TEXT, gh) == "made"
    tree = next(b for m, p, b in gh.calls if p == "trees")
    assert tree == {"tree": [{"path": "badge.json", "mode": "100644", "type": "blob", "content": TEXT}]}
    commit = next(b for m, p, b in gh.calls if p == "commits")
    assert commit["parents"] == [] and commit["message"] == "Bite score: 3/4 noticed"
    assert ("POST", "refs", {"ref": "refs/heads/bite-badge", "sha": "POST-new"}) in gh.calls


def test_updates_it_and_skips_when_nothing_changed():
    gh = FakeGitHub({"files": {"badge.json": TEXT.replace("3/4", "1/4")}})
    assert publish_badge.publish("o/r", "bite-badge", TEXT, gh) == "updated"
    assert next(b for m, p, b in gh.calls if p == "commits")["parents"] == ["head1"]
    assert gh.calls[-1][0] == "PATCH"
    same = FakeGitHub({"files": {"badge.json": TEXT}})
    assert publish_badge.publish("o/r", "bite-badge", TEXT, same) == "unchanged"
    assert not [c for c in same.calls if c[0] != "GET"]


def test_never_touches_a_branch_with_other_files():
    gh = FakeGitHub({"files": {"badge.json": TEXT, "app.py": "x"}})
    with pytest.raises(RuntimeError, match="leaves it alone"):
        publish_badge.publish("o/r", "main", TEXT, gh)
    assert not [c for c in gh.calls if c[0] != "GET"]


def test_badge_url_points_shields_at_the_raw_file():
    assert publish_badge.badge_url("o/r", "bite-badge") == (
        "https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fo%2Fr%2Fbite-badge%2Fbadge.json")


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_push_with_badge_branch_runs_bite_and_publishes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "base"], check=True)
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "bite").write_text('#!/bin/sh\necho "bite $*" >> ../calls.txt\n')
    (fake / "bite").chmod(0o755)
    (tmp_path / "publish_badge.py").write_text("open('../calls.txt', 'a').write('publish\\n')\n")
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", BASE="", MAX="7", ARGS="", FAIL="true",
               COMMENT="false", BADGE_BRANCH="bite-badge", GITHUB_ACTION_PATH=str(tmp_path),
               GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"))
    r = subprocess.run([BASH, "-e", "-o", "pipefail", "-c", action_script()], cwd=repo, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "calls.txt").read_text().splitlines() == ["bite --free --last 7 --free-checks 7", "publish"]


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_push_without_badge_branch_still_says_pull_requests_only(tmp_path):
    env = dict(os.environ, BASE="", BADGE_BRANCH="", MAX="7")
    r = subprocess.run([BASH, "-c", action_script()], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "on: pull_request" in r.stdout
