"""Prints the opening paragraph of a version's CHANGELOG.md section: the lead of its release notes.

The release-drafter workflow passes it to the draft as its header when it publishes a release by itself, so the
notes open with words a person wrote instead of a "write this before publishing" placeholder. Prints nothing
when the section is missing or opens with a list.
"""
import re
import sys
from pathlib import Path


def lead(changelog: str, version: str) -> str:
    m = re.search(rf"^## {re.escape(version)}(?=[ \t]|$).*?\n(.*?)(?=^## |\Z)", changelog, re.S | re.M)
    if not m:
        return ""
    para = m.group(1).strip().split("\n\n")[0].strip()
    return "" if not para or para.startswith(("- ", "* ", "#")) else para


if __name__ == "__main__":
    print(lead(Path(sys.argv[1]).read_text(encoding="utf-8"), sys.argv[2]))
