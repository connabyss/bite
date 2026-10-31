"""The PR checklist check. Run by .github/workflows/pr-checklist.yml on each pull request.

It reads the pull request's description and goes red while a box from .github/pull_request_template.md is left
unticked. A box that doesn't apply passes when its line says "n/a". A description with no boxes at all goes red
too. Pull requests opened by bots (for example the ones Bite opens on itself) are skipped.
It can only see the boxes, not the work behind them. Standard library only.
"""

import json
import os
import re
import sys

BOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s*(.*)$", re.M)


def problems(body: str) -> list:
    """What's still missing in a pull request description: one line per unticked box, or one line if there are none."""
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    boxes = BOX.findall(body)
    if not boxes:
        return ["The checklist is missing. Paste it in from .github/pull_request_template.md and tick the boxes."]
    return [text.strip() for mark, text in boxes
            if mark == " " and not re.search(r"\bn/?a\b", text, re.I)]


def main() -> int:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        pr = json.load(f)["pull_request"]
    if pr["user"].get("type") == "Bot":
        print("Opened by a bot, so no checklist to check.")
        return 0
    left = problems(pr.get("body") or "")
    if not left:
        print("Every box is ticked (or says n/a). Thanks!")
        return 0
    print("Almost there. Tick these boxes in the pull request description, or write n/a on a line that doesn't apply:")
    for line in left:
        print(f"::error::{line}")
    print("Editing the description reruns this check.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
