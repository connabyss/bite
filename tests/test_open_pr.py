"""open_pr.py, the Action's open-pr step, against a stand-in `gh` that records each call and answers like GitHub.
No network. Skipped on Windows: the step runs on GitHub's Linux runners."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the Action runs on Linux")
KIT = Path(__file__).parent.parent

FAKE_GH = r'''
import json, os, sys
a = sys.argv[1:]
method, path = a[a.index("-X") + 1], a[a.index("-X") + 2]
body = json.loads(sys.stdin.read()) if "--input" in a else None
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps([method, path, body]) + "\n")
fail = os.environ.get("GH_FAIL", "")
if fail and fail in f"{method} {path}":
    print("HTTP 403: GitHub Actions is not permitted to create or approve pull requests.")
    sys.exit(1)
if path.endswith("/git/commits/headsha"):
    print(json.dumps({"tree": {"sha": "basetree"}}))
elif path.endswith("/git/trees"):
    print(json.dumps({"sha": "newtree"}))
elif path.endswith("/git/commits"):
    print(json.dumps({"sha": "newcommit"}))
elif method == "PATCH" and "/git/refs/" in path:
    print("HTTP 422: Reference does not exist"); sys.exit(1)
elif path.endswith("/git/refs"):
    print(json.dumps({"ref": body["ref"]}))
elif method == "GET" and "/pulls?" in path:
    print(json.dumps(json.loads(os.environ.get("GH_OPEN", "[]"))))
elif method == "POST" and path.endswith("/pulls"):
    print(json.dumps({"number": 9}))
'''


def run(tmp_path, **env):
    work = tmp_path / "work"
    (work / "bite_proof" / "missing_tests" / "tests").mkdir(parents=True)
    (work / "bite_proof" / "missing_tests" / "tests" / "test_bite_claim.py").write_text("def test_x():\n    pass\n")
    (work / "bite_proof" / "COMMENT.md").write_text(
        "<!-- bite-check -->\n### ⚠️ Bite: no test noticed 1 change\n\n<details><summary>How Bite checks</summary>\n</details>\n",
        encoding="utf-8")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "gh.py").write_text(FAKE_GH)
    (fake / "gh").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake / "gh.py"}" "$@"\n')
    (fake / "gh").chmod(0o755)
    log = tmp_path / "gh.log"
    e = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", GH_LOG=str(log), GITHUB_REPOSITORY="o/r",
             PR="5", HEAD_SHA="headsha", HEAD_REF="my-fix")
    e.update({"HEAD_REPO": "o/r", **env})
    r = subprocess.run([sys.executable, str(KIT / "open_pr.py")], cwd=work, env=e, capture_output=True, text=True)
    calls = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return r, calls, (work / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8")


def test_opens_a_pull_request_with_the_test_into_the_checked_branch(tmp_path):
    r, calls, comment = run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    tree = next(b for m, p, b in calls if p.endswith("/git/trees"))
    assert tree["base_tree"] == "basetree" and tree["tree"][0]["path"] == "tests/test_bite_claim.py"
    assert "def test_x" in tree["tree"][0]["content"]
    commit = next(b for m, p, b in calls if p.endswith("/git/commits"))
    assert commit["parents"] == ["headsha"]
    assert ["POST", "repos/o/r/git/refs", {"ref": "refs/heads/bite/missing-tests-5", "sha": "newcommit"}] in calls
    pr = next(b for m, p, b in calls if m == "POST" and p.endswith("/pulls"))
    assert pr["head"] == "bite/missing-tests-5" and pr["base"] == "my-fix" and "fails with the change taken out" in pr["body"]
    # The line sits above the closing fold, so the comment still ends the same way.
    assert "🧪 Bite opened #9 with the test" in comment.split("How Bite checks")[0]


def test_a_later_push_reuses_the_open_pull_request(tmp_path):
    r, calls, comment = run(tmp_path, GH_OPEN='[{"number": 4}]')
    assert not [c for c in calls if c[0] == "POST" and c[1].endswith("/pulls")]
    assert "Bite opened #4" in comment


def test_without_permission_to_open_it_the_comment_links_the_branch(tmp_path):
    r, calls, comment = run(tmp_path, GH_FAIL="POST repos/o/r/pulls")
    assert r.returncode == 0
    assert "Allow GitHub Actions to create and approve pull requests" in r.stdout
    assert "compare/my-fix...bite%2Fmissing-tests-5?expand=1" in comment


def test_a_fork_gets_no_branch(tmp_path):
    r, calls, comment = run(tmp_path, HEAD_REPO="someone/r")
    assert r.returncode == 0 and not calls and "fork" in r.stdout and "🧪 Bite" not in comment
