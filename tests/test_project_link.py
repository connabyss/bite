"""`bite --free https://github.com/owner/name`: a link copied from the browser checks that project, without
cloning it by hand first. Before this, a link was "there's no folder at https://github.com/...". No network: the
"project on the web" here is a repository in a temporary folder."""

import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402
import repo  # noqa: E402

PY = sys.executable


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


@pytest.mark.parametrize("arg, url", [
    ("https://github.com/pallets/click", "https://github.com/pallets/click.git"),
    ("https://github.com/pallets/click/", "https://github.com/pallets/click.git"),
    ("https://github.com/pallets/click.git", "https://github.com/pallets/click.git"),
    ("github.com/pallets/click", "https://github.com/pallets/click.git"),
    ("https://www.github.com/pallets/click/tree/main/src", "https://github.com/pallets/click.git"),
    ("https://github.com/pallets/click/pull/12", "https://github.com/pallets/click.git"),
    ('"https://github.com/pallets/click"', "https://github.com/pallets/click.git"),
    ("https://gitlab.com/group/sub/proj/-/tree/main", "https://gitlab.com/group/sub/proj.git"),
    ("https://codeberg.org/forgejo/forgejo", "https://codeberg.org/forgejo/forgejo.git"),
    ("https://bitbucket.org/team/repo", "https://bitbucket.org/team/repo.git"),
    ("https://git.example.com/team/repo.git", "https://git.example.com/team/repo.git"),
    ("git@github.com:pallets/click.git", "git@github.com:pallets/click.git"),
])
def test_links_copied_from_a_browser_become_clone_addresses(arg, url):
    assert repo.remote_url(arg) == url


@pytest.mark.parametrize("arg", ["https://github.com/pallets", "https://github.com", "path/to/repo", "./shop",
                                 "https://example.com/page", "C:\\Users\\me\\shop", "--free", "github.com/a/b c"])
def test_folders_and_other_text_are_not_links(arg):
    assert repo.remote_url(arg) is None


def test_the_clone_folder_is_one_per_project():
    a = repo.clone_folder("https://github.com/pallets/click.git")
    assert a.name == "github.com-pallets-click" and a.parent.name == "bite-projects"
    assert repo.clone_folder("git@github.com:pallets/click.git").name == "github.com-pallets-click"


def project(root):
    """A tiny project with one fix a test notices."""
    root.mkdir()
    git(root, "init", "-q")
    (root / ".bite.ini").write_text(f"[bite]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "shop.py").write_text("def total(xs):\n    return sum(xs)\n")
    (root / "test_shop.py").write_text("from shop import total\n\n\ndef test_total():\n    assert total([1, 2]) == 3\n")
    commit(root, "start")
    (root / "shop.py").write_text("def total(xs):\n    return max(0, sum(xs))\n")
    with open(root / "test_shop.py", "a") as f:
        f.write("\n\ndef test_never_below_zero():\n    assert total([-5]) == 0\n")
    commit(root, "Fix totals going below zero")
    return root


def test_clone_then_a_second_run_gets_only_whats_new(tmp_path):
    src = project(tmp_path / "web")
    got, why = repo.clone(str(src), into=tmp_path / "copy")
    assert why == "" and (got / "shop.py").is_file()
    (src / "README.md").write_text("hi\n")
    commit(src, "Add a readme")
    again, why = repo.clone(str(src), into=tmp_path / "copy")
    assert again == got and why == "" and (got / "README.md").is_file()


def test_a_link_that_cant_be_cloned_says_so(tmp_path):
    got, why = repo.clone(str(tmp_path / "nothing-here"), into=tmp_path / "copy")
    assert got is None and "couldn't download" in why and "public" in why


def test_bite_checks_a_project_from_its_link(tmp_path, monkeypatch, capsys):
    src = project(tmp_path / "web")
    asked, real_clone = [], repo.clone

    def fake_clone(url):  # the "web": clone the local project instead of github.com
        asked.append(url)
        return real_clone(str(src), into=tmp_path / "bite-projects" / "shop")

    monkeypatch.setattr(repo, "clone", fake_clone)
    monkeypatch.chdir(tmp_path)
    rc = recent.main(["--free", "https://github.com/someone/shop"])
    out = capsys.readouterr().out
    assert asked == ["https://github.com/someone/shop.git"], out
    assert rc == 0, out[-3000:]
    assert "there's no folder at" not in out, out
    assert "runs its code" in out, out
    assert "Bite score: 1/1" in out, out[-3000:]
    assert (tmp_path / "bite-projects" / "shop" / "bite_proof" / "report.html").is_file()


def test_a_link_that_fails_to_clone_stops_with_its_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(repo, "clone", lambda url: (None, f"couldn't download {url} (not found)."))
    monkeypatch.chdir(tmp_path)
    assert recent.main(["--free", "https://github.com/someone/gone"]) == 1
    assert "Bite: couldn't download https://github.com/someone/gone.git (not found)." in capsys.readouterr().out


def test_codespaces_opens_with_bite_installed():
    """The README's "Open in GitHub Codespaces" button builds .devcontainer/devcontainer.json: Bite must be installed
    there, and the commands it suggests must be ones Bite takes."""
    import json
    cfg = json.loads((KIT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8"))
    assert "-e ." in cfg["postCreateCommand"] and "pytest" in cfg["postCreateCommand"]
    assert "bite --demo" in cfg["postAttachCommand"]
    assert repo.remote_url(cfg["postAttachCommand"].split("bite --free ")[1].split("'")[0])
    assert "https://codespaces.new/connabyss/bite?quickstart=1" in (KIT / "README.md").read_text(encoding="utf-8")
