"""One set of names for 1.0: the help says what the results say (#76), and settings live under [bite] while old
.bite.ini files with [kit] keep working."""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402
import repo  # noqa: E402


def test_help_uses_the_names_the_results_use():
    out = subprocess.run([sys.executable, str(Path(recent.__file__)), "--help"], capture_output=True, text=True,
                         encoding="utf-8").stdout
    c = {"sha": "a" * 40, "subject": "Fix x", "undo": "unguarded"}
    for undo in ("unguarded", "TEST GUARDS NOTHING"):
        name = recent.say({**c, "undo": undo})[1].removeprefix("⚠️ ")
        assert f'("{name}")' in out
    assert "TEST GUARDS NOTHING" not in out and '"unguarded"' not in out


def project(ini: str) -> Path:
    root = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".bite.ini").write_text(ini, encoding="utf-8")
    return root


@pytest.mark.parametrize("section", ["bite", "kit"])
def test_settings_are_read_under_bite_and_the_old_kit(section):
    root = project(f"[{section}]\ntest_command = echo hi\nfree_test_command = echo fast\n")
    cfg = repo.load_cfg(root)
    recent.extras(root, cfg)
    assert cfg.test_cmd == "echo hi" and cfg.free_cmd == "echo fast"


def test_a_file_without_the_section_says_to_add_bite():
    with pytest.raises(repo.ConfigError, match=r"\[bite\]"):
        repo.load_cfg(project("test_command = echo hi\n"))
