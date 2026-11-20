"""Bite's docs, messages and code use US spelling. This fails on a UK spelling, so one can't creep back in."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UK = re.compile(r"\b(colours?|coloured|behaviours?|favourites?|maths|labelled|modelled|whilst|recognis\w*|optimis\w*|"
                r"organis\w*|centre|licence|ticked|unticked)\b", re.I)
# Files that use the UK spelling on purpose (this one, and a test that compares the two). Translations are skipped too.
SKIP = {"tests/test_us_spelling.py", "tests/test_tricks.py"}
SKIP_DIRS = {".git", "bite_proof", "node_modules", "build", "dist", ".venv", "venv", "__pycache__", ".pytest_cache", "i18n"}


def test_no_uk_spellings():
    found = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if (path.suffix not in {".py", ".md", ".yml", ".toml"} or not path.is_file() or rel.as_posix() in SKIP
                or any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel.parts)):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in UK.finditer(line):
                found.append(f"{rel.as_posix()}:{n}: {m.group(0)}")
    assert not found, "UK spellings (use US):\n" + "\n".join(found)
