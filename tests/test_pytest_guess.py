"""Python projects that keep pytest's settings in pyproject.toml or setup.cfg, with tests a folder or two deeper
(tests/unit/test_api.py), get the pytest command as Bite's guess instead of "no test command found" (issue #251)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bite  # noqa: E402

PYTEST = ("python" if bite.WINDOWS else "python3") + " -m pytest -q"


def write(root, name, text=""):
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")


@pytest.mark.parametrize("name, text", [
    ("pyproject.toml", '[project]\nname = "demo"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'),
    ("setup.cfg", "[metadata]\nname = demo\n\n[tool:pytest]\ntestpaths = tests\n"),
])
def test_pytest_settings_table_means_pytest(tmp_path, name, text):
    write(tmp_path, name, text)
    write(tmp_path, "m.py", "def f():\n    return 1\n")
    assert bite.guess_test_command(tmp_path) == PYTEST


def test_issue_251_repro_tests_two_folders_down(tmp_path):
    write(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    write(tmp_path, "tests/unit/test_a.py")
    assert bite.guess_test_command(tmp_path) == PYTEST


def test_deep_tests_without_any_config(tmp_path):
    write(tmp_path, "tests/unit/api/test_api.py")
    assert bite.guess_test_command(tmp_path) == PYTEST


def test_pyproject_without_pytest_is_no_guess(tmp_path):
    write(tmp_path, "pyproject.toml", '[project]\nname = "demo"\n\n[tool.ruff]\nline-length = 100\n')
    write(tmp_path, "m.py")
    assert bite.guess_test_command(tmp_path) == ""


@pytest.mark.parametrize("raw", [
    "[]",
    '"hello"',
    '{"scripts": ["x"]}',
    '{"scripts": {"test": 5}}',
    "{ broken",
])
def test_non_standard_package_json_does_not_crash_and_falls_through(tmp_path, raw):
    write(tmp_path, "package.json", raw)
    assert bite.guess_test_command(tmp_path) == ""

    write(tmp_path, "Cargo.toml", '[package]\nname = "demo"\n')
    assert bite.guess_test_command(tmp_path) == "cargo test"


def test_npm_cargo_and_go_guesses(tmp_path):
    npm_dir = tmp_path / "npm_real"
    write(npm_dir, "package.json", '{"scripts": {"test": "jest"}}')
    assert bite.guess_test_command(npm_dir) == "npm test"

    npm_init_dir = tmp_path / "npm_init"
    write(npm_init_dir, "package.json", '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}')
    assert bite.guess_test_command(npm_init_dir) == ""

    cargo_dir = tmp_path / "cargo"
    write(cargo_dir, "Cargo.toml", '[package]\nname = "demo"\n')
    assert bite.guess_test_command(cargo_dir) == "cargo test"

    go_dir = tmp_path / "go"
    write(go_dir, "go.mod", "module example.com/demo\n")
    assert bite.guess_test_command(go_dir) == "go test ./..."
