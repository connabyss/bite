"""A pytest run where every test passed, then an exit hook printed a Traceback. No network."""

import sys
from pathlib import Path

KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT))

import bite  # noqa: E402

# What marketcalls/openalgo's suite prints: all tests pass, pytest exits 0, then an atexit hook logs to a
# stream pytest has already closed.
LOGGING_ERROR = [
    "--- Logging error ---",
    "Traceback (most recent call last):",
    '  File "/usr/lib/python3.12/logging/__init__.py", line 1163, in emit',
    "ValueError: I/O operation on closed file.",
    "Message: 'Cleanup complete'",
]


def run_printing(tmp_path, lines, code=0):
    script = tmp_path / "fake_tests.py"
    script.write_text(f"import sys\nprint({chr(10).join(lines)!r})\nsys.exit({code})\n", encoding="utf-8")
    ini = tmp_path / "kit.ini"
    ini.write_text(f'[kit]\nproject_folder = {tmp_path}\ntest_command = "{sys.executable}" "{script}"\n',
                   encoding="utf-8")
    return bite.run_tests(bite.Config(ini), tmp_path)


def test_traceback_after_all_passed_is_not_a_failure(tmp_path):
    r = run_printing(tmp_path, ["test/test_a.py::test_one PASSED [100%]",
                                "======================= 639 passed, 8 warnings in 38.11s ======================="]
                     + LOGGING_ERROR)
    assert r["ok"], r["why"]


def test_traceback_without_a_passing_summary_still_fails(tmp_path):
    r = run_printing(tmp_path, LOGGING_ERROR)
    assert not r["ok"]


def test_traceback_with_a_failed_test_still_fails(tmp_path):
    r = run_printing(tmp_path, ["Traceback (most recent call last):", "AssertionError",
                                "================== 1 failed, 638 passed in 38.11s ==================="])
    assert not r["ok"]


def test_traceback_after_passed_with_a_bad_exit_still_fails(tmp_path):
    r = run_printing(tmp_path, ["============ 639 passed in 38.11s ============"] + LOGGING_ERROR, code=1)
    assert not r["ok"]
