"""bite ask: a question in plain words finds the matching commit(s) and gets Bite's free check as one sentence.
No key, no network: a tiny repo with one guarded fix and one fix no test notices."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import ask  # noqa: E402
import bite_mcp  # noqa: E402

PY = sys.executable
NOW = datetime(2026, 11, 1, 12, 0)
AUTH = "def login(name, password):\n    return bool(name)\n"
AUTH_FIX = "def login(name, password):\n    return bool(name) and password == 'pw'\n"
AUTH_TEST = ("from auth import login\n\n\ndef test_login():\n    assert login('a', 'pw')\n\n\n"
             "def test_empty_password_is_refused():\n    assert login('a', '') is False\n")
CART = "def discount(price, percent):\n    return price - price * percent / 100\n"
CART_FIX = "def discount(price, percent):\n    return max(0, price - price * percent / 100)\n"
CART_TEST = "from cart import discount\n\n\ndef test_discount():\n    assert discount(100, 20) == 80\n"


def commit(root, msg, when):
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg], cwd=root,
                   check=True, capture_output=True, env=env)


def make(tmp_path):
    root = tmp_path / "shop"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m pytest -q -p no:cacheprovider\n")
    (root / "auth.py").write_text(AUTH)
    (root / "cart.py").write_text(CART)
    (root / "test_auth.py").write_text(AUTH_TEST.split("\n\n\ndef test_empty")[0] + "\n")
    (root / "test_cart.py").write_text(CART_TEST)
    commit(root, "start", "2026-09-01T12:00:00")
    (root / "auth.py").write_text(AUTH_FIX)
    (root / "test_auth.py").write_text(AUTH_TEST)
    commit(root, "Fix login letting an empty password in", "2026-10-27T12:00:00")  # last week
    (root / "cart.py").write_text(CART_FIX)
    commit(root, "Fix discount going below zero", "2026-10-31T12:00:00")  # yesterday, no test
    return root


def test_a_guarded_fix_gets_yes_and_its_commit(tmp_path):
    r = ask.ask(make(tmp_path), "is last week's login bug guarded?", now=NOW, log=lambda s: None)
    assert r["status"] == "held", r["text"]
    assert r["text"].startswith("Yes. \"Fix login letting an empty password in\"")
    assert "test_empty_password_is_refused fails" in r["text"] and "Oct 27" in r["text"]
    assert len(r["checked"]) == 1  # the discount fix shares no word with the question: not checked


def test_a_fix_no_test_notices_gets_no_and_a_next_step(tmp_path):
    r = ask.ask(make(tmp_path), "did the discount fix get a test?", now=NOW, log=lambda s: None)
    assert r["status"] == "gap", r["text"]
    assert r["text"].startswith("No. \"Fix discount going below zero\"") and "every test still passes" in r["text"]
    assert "Next: add a test that fails without that change" in r["text"]


def test_the_time_in_the_question_narrows_the_commits(tmp_path):
    root = make(tmp_path)
    assert ask.ask(root, "yesterday's discount fix", now=NOW, log=lambda s: None)["status"] == "gap"
    r = ask.ask(root, "is today's login fix guarded?", now=NOW, log=lambda s: None)  # nothing was made today
    assert r["status"] == "none" and "today" in r["text"]
    r = ask.ask(root, "the login fix from yesterday", now=NOW, log=lambda s: None)  # login was last week
    assert r["status"] == "none", r["text"]


def test_words_that_match_nothing_say_so_instead_of_guessing(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "has_key", lambda: False)
    r = ask.ask(make(tmp_path), "is the checkout page guarded?", now=NOW, log=lambda s: None)
    assert r["status"] == "none" and "matches your words" in r["text"] and "API key" in r["text"]


def test_the_key_is_used_only_when_words_dont_clearly_match(tmp_path, monkeypatch):
    root = make(tmp_path)
    calls = []

    def fake_pick(cfg, question, cs, n):
        calls.append(question)
        return [c for c in cs if "login" in c["subject"]]
    monkeypatch.setattr(ask, "has_key", lambda: True)
    monkeypatch.setattr(ask, "ai_pick", fake_pick)
    assert ask.ask(root, "is the discount fix guarded?", now=NOW, log=lambda s: None)["status"] == "gap"
    assert calls == []  # the words were enough: no paid call
    r = ask.ask(root, "is the sign-in hole guarded?", now=NOW, log=lambda s: None)
    assert calls == ["is the sign-in hole guarded?"] and r["status"] == "held" and r["how"] == "ai"
    ask.ask(root, "is the sign-in hole guarded?", now=NOW, free=True, log=lambda s: None)
    assert len(calls) == 1  # --free never uses the key


def test_question_words_and_times():
    assert ask.words("Is last week's login bug guarded?") == {"login"}
    assert ask.words("crashes in save_game") == ask.words("crashed saveGame") == {"crash", "save", "game"}
    start, end, said = ask.when("in the last 10 days", NOW)
    assert (NOW - start).days == 10 and said == "in the last 10 days"
    assert ask.when("is it guarded?", NOW) == (None, None, "")


def test_bite_ask_command_exits_1_on_a_gap(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(make(tmp_path))
    assert ask.main(["is", "the", "discount", "fix", "guarded?", "--free"]) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("Next:")


def test_coding_ais_can_ask_through_bite_mcp(tmp_path):
    root = make(tmp_path)
    r = bite_mcp.answer({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                         "params": {"name": "ask_bite", "arguments": {"question": "is the login fix guarded?",
                                                                       "folder": str(root)}}})["result"]
    assert r["isError"] is False and r["content"][0]["text"].startswith("Yes.")
