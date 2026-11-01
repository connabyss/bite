"""bite --version tells you when a newer Bite is out, with the one line that always updates it. No network: PyPI
is faked."""
import contextlib
import io
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import recent  # noqa: E402


def version_output(latest, current="0.9.0"):
    buf = io.StringIO()
    with patch.object(recent, "latest_version", return_value=latest), \
            patch.object(recent, "_installed_version", return_value=current), contextlib.redirect_stdout(buf):
        assert recent.main(["--version"]) == 0
    return buf.getvalue()


def test_a_newer_release_gets_the_update_line():
    # pipx upgrade said 0.9.0 was the latest right after 0.10.0 came out: pip had kept its old list of versions
    out = version_output("0.10.0")
    assert out.startswith("bite 0.9.0\n") and "Bite 0.10.0 is out" in out
    assert 'pipx install --force bite-check --pip-args="--no-cache-dir"' in out


def test_no_note_when_up_to_date_offline_or_ahead():
    for latest in ("0.9.0", None, "0.8.0", "not a version"):
        assert version_output(latest) == "bite 0.9.0\n"


def test_versions_compare_as_numbers_not_text():
    assert recent._newer("0.10.0", "0.9.0") and not recent._newer("0.9.0", "0.10.0")


def test_the_readme_gives_the_same_line():
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    assert "## Updating Bite" in readme and recent.UPDATE_LINE in readme
