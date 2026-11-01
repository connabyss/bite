"""Odd .bite.ini files found by the overnight stress test (2026-11-01): each test here failed before its fix."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import repo  # noqa: E402

PY = sys.executable
CMD = f"{PY} -m pytest -q"


def project(tmp_path, ini: bytes) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".bite.ini").write_bytes(ini)
    return tmp_path


def test_a_bom_from_windows_notepad_is_fine(tmp_path):
    # Notepad saves UTF-8 with an invisible mark first; Bite said ".bite.ini has no [bite] section".
    cfg = repo.load_cfg(project(tmp_path, ("﻿[bite]\ntest_command = " + CMD + "\n").encode("utf-8")))
    assert cfg.test_cmd == CMD


@pytest.mark.parametrize("ini, says", [
    (f"[bite]\ntest_command = {CMD}\ntest_timeout_seconds = abc\n", "a setting that needs a number has 'abc'"),
    (f"[bite]\ntest_command = {CMD}\ntest_command = {CMD}\n", "test_command is set twice (line 3)"),
    (f"[bite]\ntest_command = {CMD}\ntest_timeout_seconds = 0\n", "test_timeout_seconds needs a number of seconds above 0"),
    (f"[bite]\ntest_command = {CMD}\ncontain_command = docker run --rm img sh -c pytest\n", "contain_command needs {cmd}"),
])
def test_a_setting_bite_cant_use_is_named_plainly(tmp_path, ini, says):
    # These stopped Bite with a Python error, or (timeout 0, contain_command without {cmd}) ran no test at all.
    with pytest.raises(repo.ConfigError) as e:
        repo.load_cfg(project(tmp_path, ini.encode()))
    assert says in str(e.value) and "Traceback" not in str(e.value)
