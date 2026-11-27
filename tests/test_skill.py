"""The agent skill in skills/ must stay valid and match what bite live really says."""
import re
from pathlib import Path

import live

SKILL = Path(__file__).resolve().parent.parent / "skills" / "bite-verify-fix" / "SKILL.md"


def front(text):
    head = text.split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def test_frontmatter_follows_the_agent_skills_rules():
    meta = front(SKILL.read_text(encoding="utf-8"))
    assert meta["name"] == SKILL.parent.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"]) and len(meta["name"]) <= 64
    assert 0 < len(meta["description"]) <= 1024
    assert ": " not in meta["description"]  # a colon breaks YAML for some installers
    assert meta["license"] == "MIT"


def test_the_skill_names_every_answer_bite_live_gives():
    text = SKILL.read_text(encoding="utf-8")
    answers = {
        "a test noticed": {"status": "guarded", "code": ["a.py"]},
        "no test noticed": {"status": "unguarded", "code": ["a.py"]},
        "the tests that came with this change": {"status": "tests_blind", "code": ["a.py"], "test_code": ["t.py"]},
        "couldn't check": {"status": "cant", "why": "x"},
        "nothing to check": {"status": "nothing"},
    }
    for words, result in answers.items():
        assert words in live.say(result), words
        assert words in text, words


PLUGIN = SKILL.parent.parent.parent / "plugin"


def test_the_plugin_ships_the_same_skill():
    # the directory takes the plugin folder alone and refuses symlinks, so the plugin holds a copy of the skill
    copy = PLUGIN / "skills" / SKILL.parent.name / "SKILL.md"
    assert copy.read_bytes() == SKILL.read_bytes(), "copy skills/bite-verify-fix/SKILL.md into plugin/skills/"


def test_the_plugin_folder_passes_the_directory_basics():
    import json
    words = re.sub(r"```.*?```", "", (PLUGIN / "README.md").read_text(encoding="utf-8"), flags=re.S).split()
    assert len(words) >= 40  # the directory blocks a plugin README under 40 words
    meta = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert meta["license"] and meta["version"] and meta["description"]
    live = PLUGIN.parent / "plugin-live"
    assert "hooks" in json.loads((live / "hooks" / "hooks.json").read_text(encoding="utf-8"))
