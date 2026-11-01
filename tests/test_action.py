"""Runs the pull request check's own script from action.yml with a stand-in `bite`, so the check's color is tested
against what the comment says. Needs bash and git; no network."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).parent.parent
BASH = shutil.which("bash")


def action_script():
    lines = (KIT / "action.yml").read_text(encoding="utf-8").splitlines()
    start = max(i for i, ln in enumerate(lines) if ln.strip() == "run: |") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("    - ")), len(lines))  # the next step
    return "\n".join(ln[8:] for ln in lines[start:end])


def run_check(tmp_path, heading, report=False, wrote=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "change")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "bite.py").write_text(
        "import pathlib\n"
        "p = pathlib.Path('bite_proof'); p.mkdir(exist_ok=True)\n"
        f"(p / 'COMMENT.md').write_text('<!-- bite-check -->\\n### {heading}\\n', encoding='utf-8')\n"
        + ("(p / 'FREE_REPORT.md').write_text('gap', encoding='utf-8')\n" if report else "")
        + ("(p / 'missing_tests').mkdir(); (p / 'missing_tests' / 'test_bite_claim.py').write_text('x')\n" if wrote else ""))
    (fake / "bite").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{(fake / "bite.py").as_posix()}"\n')
    (fake / "bite").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", BASE=base, MAX="20", ARGS="", FAIL="true",
               COMMENT="false", PR="1", GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"),
               GITHUB_OUTPUT=str(tmp_path / "output.txt"))
    return subprocess.run([BASH, "-e", "-o", "pipefail", "-c", action_script()], cwd=repo, env=env,
                          capture_output=True, text=True)


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_tests_already_failing_turn_the_check_red(tmp_path):
    r = run_check(tmp_path, "❌ Bite: your tests already fail")
    assert r.returncode == 1 and "couldn't check it" in r.stdout


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_green_comment_keeps_the_check_green(tmp_path):
    r = run_check(tmp_path, "✅ Bite-proof. Nice work.")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_gap_still_turns_the_check_red(tmp_path):
    r = run_check(tmp_path, "⚠️ Bite: no test noticed 1 change", report=True)
    assert r.returncode == 1 and "isn't guarded" in r.stdout


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_write_tests_without_a_key_runs_the_free_check_only(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITE", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = run_check(tmp_path, "✅ Bite-proof. Nice work.")
    assert r.returncode == 0 and "no anthropic-api-key" in r.stdout, r.stdout + r.stderr


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_written_test_is_flagged_for_the_download_and_the_check_stays_red(tmp_path):
    r = run_check(tmp_path, "⚠️ Bite: no test noticed 1 change", report=True, wrote=True)
    assert r.returncode == 1 and "tests=true" in (tmp_path / "output.txt").read_text()


def test_the_download_step_runs_after_a_red_check():
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load((KIT / "action.yml").read_text(encoding="utf-8"))["runs"]["steps"]
    up = steps[-1]
    assert up["uses"].startswith("actions/upload-artifact@") and "steps.bite.outputs.tests == 'true'" in up["if"]
    assert up["with"]["path"] == "bite_proof/missing_tests/" and "always()" in up["if"]


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_no_written_test_means_no_download(tmp_path):
    r = run_check(tmp_path, "⚠️ Bite: no test noticed 1 change", report=True)
    assert r.returncode == 1 and not (tmp_path / "output.txt").exists()


def test_descriptions_hold_no_expressions():
    # GitHub reads ${{ }} even inside an input's description, and only github.* works in action.yml: one line
    # mentioning secrets.X there stops the action from loading at all.
    text = (KIT / "action.yml").read_text(encoding="utf-8")
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(text)["inputs"]["write-tests"]["default"] == "false"
    assert not [ln for ln in text.splitlines() if ln.strip().startswith("description:") and "${{" in ln]


def test_marketplace_description_reads_cleanly():
    # The Marketplace listing showed "each commit s code change": it dropped the apostrophe. Keep the line free of
    # apostrophes, ending in a full stop, and within the 125 characters the listing shows.
    yaml = pytest.importorskip("yaml")
    line = yaml.safe_load((KIT / "action.yml").read_text(encoding="utf-8"))["description"]
    assert "'" not in line and "\u2019" not in line
    assert line.endswith(".") and len(line) <= 125


def test_readme_links_work_on_pypi():
    # PyPI shows the README too, but not the repo's files: a relative image or link there is broken.
    import re
    text = (KIT / "README.md").read_text(encoding="utf-8")
    relative = [t for t in re.findall(r'(?:src|srcset)="([^"]+)"|\]\(([^)]+)\)', text) for t in t if t
                and not t.startswith(("http://", "https://", "#", "mailto:"))]
    assert relative == []
