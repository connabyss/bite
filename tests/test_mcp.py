"""bite mcp: the live check as a tool any coding AI can call (Claude Code, Cursor, Copilot, Windsurf, Codex...).
No key, no network: the tiny shop repo from test_live, and MCP's JSON written by hand the way a client sends it."""

import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bite_mcp  # noqa: E402
from test_live import FIXED, GOOD, make  # noqa: E402


def call(**arguments):
    return bite_mcp.answer({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                            "params": {"name": "check_fix", "arguments": arguments}})["result"]


def test_handshake_and_tool_list():
    init = bite_mcp.answer({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                       "clientInfo": {"name": "cursor", "version": "1"}}})
    assert init["id"] == 1 and init["result"]["protocolVersion"] == "2025-03-26"  # the client's own version back
    assert init["result"]["capabilities"] == {"tools": {}} and init["result"]["serverInfo"]["name"] == "bite"
    assert bite_mcp.answer({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = bite_mcp.answer({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in tools] == ["check_fix"] and tools[0]["inputSchema"]["type"] == "object"
    assert bite_mcp.answer({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"] == -32601


def test_a_fix_no_test_notices_tells_the_ai_to_add_one(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    r = call(folder=str(root))
    text = r["content"][0]["text"]
    assert r["isError"] is False
    assert "no test noticed the change to cart.py" in text and "fails without your change" in text
    assert "call check_fix again" in text


def test_a_fix_a_test_notices_gets_a_tick(tmp_path):
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    (root / "test_cart.py").write_text(GOOD)
    text = call(folder=str(root))["content"][0]["text"]
    assert text.startswith("Bite ✅ a test noticed")


def test_since_a_branch_checks_the_commits_too(tmp_path):
    root = make(tmp_path)
    start = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True,
                           text=True, check=True).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "-b", "fix"], cwd=root, check=True)
    (root / "cart.py").write_text(FIXED)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "fix discount"],
                   cwd=root, check=True)
    assert "nothing to check" in call(folder=str(root))["content"][0]["text"]  # nothing since the last commit
    assert "no test noticed" in call(folder=str(root), since=start)["content"][0]["text"]
    assert call(folder=str(root), since="no-such-branch")["isError"] is True


def test_not_a_repo_is_an_error_not_a_pass(tmp_path):
    r = call(folder=str(tmp_path))
    assert r["isError"] is True and "isn't inside a git repository" in r["content"][0]["text"]


def test_bite_mcp_speaks_only_json_on_stdout(tmp_path):
    """The real command, the way a coding AI starts it: every line on stdout must be a JSON reply, even while
    the project's tests print, or the AI's client drops the connection."""
    root = make(tmp_path)
    (root / "cart.py").write_text(FIXED)
    (root / "test_cart.py").write_text(GOOD)
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "check_fix", "arguments": {}}},
            "not json"]
    stdin = "\n".join(m if isinstance(m, str) else json.dumps(m) for m in msgs) + "\n"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, str(KIT / "recent.py"), "mcp"], cwd=root, input=stdin.encode(),
                       capture_output=True, env=env, timeout=300)
    replies = [json.loads(line) for line in p.stdout.decode("utf-8").splitlines()]
    assert [r["id"] for r in replies] == [1, 2, None]
    assert replies[1]["result"]["content"][0]["text"].startswith("Bite ✅")
    assert replies[2]["error"]["code"] == -32700


def test_anything_printed_during_a_check_stays_off_the_json(tmp_path):
    """A check that prints (from Python or straight to the file handle, as a child process would) must not get
    into the replies: the noise goes to stderr."""
    root = make(tmp_path)
    noisy = ("import os, sys; sys.path.insert(0, sys.argv[1]); import live, bite_mcp\n"
             "def check(root, base):\n"
             "    print('noise'); sys.stdout.flush(); os.write(1, b'raw noise\\n')\n"
             "    return {'status': 'nothing'}\n"
             "live.check = check\n"
             "sys.exit(bite_mcp.main([]))\n")
    stdin = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "check_fix", "arguments": {}}}) + "\n"
    p = subprocess.run([sys.executable, "-c", noisy, str(KIT)], cwd=root, input=stdin.encode(),
                       capture_output=True, timeout=60)
    assert [json.loads(line)["id"] for line in p.stdout.decode("utf-8").splitlines()] == [5]
    assert b"noise" in p.stderr and b"raw noise" in p.stderr
