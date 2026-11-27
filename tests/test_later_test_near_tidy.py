"""A fix with no test of its own, guarded by a test a later commit added, stays "a later test notices" even when a
tidy-up afterward edits the line right next to the fix. The tidy-up changes the fix's context lines, so its diff
no longer takes back out of today's code as is; Bite used to give up there and call the fix NO TEST NOTICED.
(Found by the robot dev team side project: a janitor removing an unused import beside a fix.)"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402

RECENT = str(Path(recent.__file__))
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]

START = '''"""A till."""
import math


def total(cups, tip):
    return round(cups * 1.5 * (1 + tip / 100), 2)
'''
FIXED = '''"""A till."""
from decimal import Decimal, ROUND_HALF_UP
import math


def total(cups, tip):
    t = Decimal(str(cups * 1.5)) * (1 + Decimal(tip) / 100)
    return float(t.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
'''
TEST = "from till import total\n\n\ndef test_two():\n    assert total(2, 0) == 3.0\n"
LATER = TEST + "\n\ndef test_tip_rounds_half_cent_up():\n    assert total(3, 15) == 5.18\n"


def project(steps: list) -> Path:
    root = Path(tempfile.mkdtemp(prefix="bite_near_tidy_"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for subject, files in steps:
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", subject], cwd=root, check=True)
    return root


def result_for(root: Path, subject: str) -> dict:
    p = subprocess.run([sys.executable, RECENT, "--free", "--any", "--quick", "--json"], cwd=root, capture_output=True,
                       text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert p.stdout.strip(), p.stderr
    return next(c for c in json.loads(p.stdout)["commits"] if c["subject"] == subject)


def test_a_later_test_still_counts_after_a_tidy_up_beside_the_fix():
    root = project([("Start", {"till.py": START, "test_till.py": TEST}),
                    ("Fix tips rounding down by a cent", {"till.py": FIXED}),
                    ("Add a test for the tip rounding fix", {"test_till.py": LATER}),
                    ("Tidy up: remove unused import math", {"till.py": FIXED.replace("import math\n", "")})])
    r = result_for(root, "Fix tips rounding down by a cent")
    assert r["result"] == "noticed", r
    assert "test_tip_rounds_half_cent_up" in r["detail"]


def test_with_no_later_test_it_is_still_flagged():
    root = project([("Start", {"till.py": START, "test_till.py": TEST}),
                    ("Fix tips rounding down by a cent", {"till.py": FIXED}),
                    ("Tidy up: remove unused import math", {"till.py": FIXED.replace("import math\n", "")})])
    assert result_for(root, "Fix tips rounding down by a cent")["result"] == "no_test_noticed"


# The comeback alarm had the same blind spot: an undo that also tidied the line beside the fix went unnoticed.
SHOP_OLD = '"""A shop."""\nimport math\n\n\ndef total(prices):\n    return sum(prices)\n'
SHOP_FIX = ('"""A shop."""\nfrom decimal import Decimal\nimport math\n\n\n'
            'def total(prices):\n    return float(sum(map(Decimal, prices)))\n')


def sha_of(root: Path, subject: str) -> str:
    return subprocess.run(["git", "log", "--format=%H", f"--grep=^{subject}$"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.split()[0]


def test_an_undo_that_also_tidies_beside_the_fix_is_still_named():
    root = project([("Start", {"shop.py": SHOP_OLD}), ("Fix totals", {"shop.py": SHOP_FIX}),
                    ("Simplify and tidy", {"shop.py": SHOP_OLD.replace("import math\n", "")})])
    c = {"sha": sha_of(root, "Fix totals"), "code": ["shop.py"]}
    assert recent.came_back(root, c) == "undone since"
    assert c["undone_by"]["subject"] == "Simplify and tidy"


def test_a_tidy_beside_a_fix_that_stays_is_not_an_undo():
    root = project([("Start", {"shop.py": SHOP_OLD}), ("Fix totals", {"shop.py": SHOP_FIX}),
                    ("Tidy up", {"shop.py": SHOP_FIX.replace("import math\n", "")})])
    assert recent.came_back(root, {"sha": sha_of(root, "Fix totals"), "code": ["shop.py"]}) == ""
