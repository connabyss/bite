"""The test Bite or its worker writes runs with the project's own pytest command, minus its folders, plus that one
file. Options keep their values: `-n auto` used to lose its `auto`, so every written test failed to start (#142)."""

import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402


class Cfg:
    claim_cmd, contain, box_test_cmd = "", "", ""


def claim(tmp_path, test_cmd):
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    Cfg.test_cmd, Cfg.project = test_cmd, tmp_path
    return recent.claim_command(Cfg, "tests/test_bite_claim.py")


def test_options_keep_their_values_and_folders_are_dropped(tmp_path):
    assert claim(tmp_path, "python -m pytest -q -n auto -p no:cacheprovider") == \
        "python -m pytest -q -n auto -p no:cacheprovider tests/test_bite_claim.py"
    assert claim(tmp_path, "python -m pytest -n 4 tests src -k slow --maxfail 2") == \
        "python -m pytest -n 4 -k slow --maxfail 2 tests/test_bite_claim.py"
    assert claim(tmp_path, "pytest . -x tests/test_a.py tests/test_b.py::test_one") == \
        "pytest -x tests/test_bite_claim.py"


def test_a_written_test_runs_under_pytest_xdist(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bite_claim.py").write_text("def test_ok():\n    assert True\n")
    cmd = claim(tmp_path, f"{sys.executable} -m pytest -q -n auto -p no:cacheprovider")
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_DISABLE_PLUGIN_AUTOLOAD"}  # this one needs xdist
    p = subprocess.run(cmd.split(), cwd=tmp_path, capture_output=True, text=True, env=env)
    assert p.returncode == 0 and "1 passed" in p.stdout, p.stdout + p.stderr


def test_an_option_keeps_a_path_value(tmp_path):
    """spantruth's command had `--deselect tests/test_x.py::test_slow`: the path was dropped as a file to test, so
    --deselect took the file Bite added, and the commit's own tests never ran (a false "noticed")."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("")
    assert claim(tmp_path, "python -m pytest -q --deselect tests/test_x.py::test_slow --ignore tests/test_x.py tests") \
        == "python -m pytest -q --deselect tests/test_x.py::test_slow --ignore tests/test_x.py tests/test_bite_claim.py"


def test_the_added_file_runs_beside_a_deselect(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_other.py").write_text("def test_slow():\n    assert True\n")
    (tmp_path / "tests" / "test_bite_claim.py").write_text("def test_claim():\n    assert False\n")
    cmd = claim(tmp_path, f"{sys.executable} -m pytest -q -p no:cacheprovider --deselect tests/test_other.py::test_slow tests")
    p = subprocess.run(cmd.split(), cwd=tmp_path, capture_output=True, text=True)
    assert "1 failed" in p.stdout and "passed" not in p.stdout, p.stdout + p.stderr  # only the added test ran
