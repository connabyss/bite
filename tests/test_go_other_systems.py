"""Go builds a file named x_windows.go only on Windows (likewise _darwin, _linux, ...). A commit that changed only
such files for another system can't be checked here: before this, it read as "no test noticed" (found by the
overnight stress test, 2026-11-01)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402


def test_go_files_built_only_for_another_system_are_skipped():
    other = "windows" if recent.HERE != "win" else "linux"
    assert recent.go_os_only([f"term_{other}.go"]).startswith("built for")
    assert recent.go_os_only([f"term_{other}_amd64.go", f"pipe_{other}.go"]).startswith("built for")
    assert recent.go_os_only([f"term_{other}.go", "term.go"]) == ""  # term.go is built everywhere
    here = {"win": "windows", "mac": "darwin", "linux": "linux"}[recent.HERE]
    assert recent.go_os_only([f"term_{here}.go"]) == ""
    assert recent.go_os_only(["window.go", "user_windowsx.go", "shop.py"]) == ""
    assert recent.go_os_only([]) == ""
