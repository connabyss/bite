"""The art-trail line in bite_check and the citation file: present, and silent in normal use."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_credits_line_exists_and_points_on():
    sys.path.insert(0, ROOT)
    import bite_check

    assert bite_check.__credits__.startswith("*10 ")
    assert "security.txt" in bite_check.__credits__


def test_credits_never_reach_normal_output():
    out = subprocess.run([sys.executable, "-m", "bite_check", "--version"], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    assert "*10" not in out.stdout + out.stderr


def test_citation_file_has_the_fields_github_needs():
    with open(os.path.join(ROOT, "CITATION.cff"), encoding="utf-8") as f:
        text = f.read()
    for field in ("cff-version: 1.2.0", "message:", "title:", "authors:", "repository-code:"):
        assert field in text
    assert all(line.startswith("#") for line in text.split("cff-version")[0].strip().splitlines())
