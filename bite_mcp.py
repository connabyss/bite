"""
Bite for any coding AI: `bite mcp` is a small MCP server with one tool, check_fix.

MCP is the plug most coding AIs share (Claude Code, Cursor, Copilot in VS Code, Windsurf, Codex, Gemini CLI).
Add `bite mcp` as a server in yours and the AI can ask Bite, right after it says "fixed", whether any test
notices its change. It's the same free check as `bite live`: the change is taken back out of a copy of the
project and the tests are run. No API key, nothing of yours is touched.

    bite mcp     run the server (your coding AI starts it; it talks JSON on stdin and stdout)

Setup lines for each coding AI: README.md, "Check the "fixed" live, in any coding AI".
Written by hand on purpose, so Bite still needs no packages: newline-delimited JSON-RPC over stdio.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live  # noqa: E402
import repo  # noqa: E402

PROTOCOL = "2025-06-18"  # the newest MCP version this was written against; older clients get their own back

TOOL = {
    "name": "check_fix",
    "title": "Bite: does a test notice my fix?",
    "description": (
        "Call this after you change code to fix a bug, before you tell the user it's fixed. Bite takes your "
        "change back out of a copy of the project and runs the project's tests. If they still pass, no test "
        "shows your fix does anything: add a test that fails without your change and passes with it, then call "
        "this again. Free, needs no key, never touches the user's files. Can take as long as the tests do."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "folder": {"type": "string",
                       "description": "The project folder you changed (any folder inside its git repository). "
                                      "Leave it out to use the folder Bite was started in."},
            "since": {"type": "string",
                      "description": "Check the changes since this commit or branch (for example main). "
                                     "Default: the changes since the last commit, including uncommitted ones."},
        },
    },
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
}


def check_fix(args: dict) -> tuple:
    """(text for the AI, True if it's an error the AI should know it caused)."""
    folder = args.get("folder") or os.getcwd()
    root = repo.repo_root(folder)
    if root is None:
        return (f"Bite: {folder} isn't inside a git repository. Pass the project's folder as folder.", True)
    since = args.get("since") or "HEAD"
    if repo.git(root, "rev-parse", "--verify", "-q", f"{since}^{{commit}}") is None:
        return (f"Bite: {since} isn't a commit or branch in {root}.", True)
    r = live.check(root, since)
    text = live.say(r)
    if r["status"] in ("unguarded", "tests_blind"):
        text += "\n\n" + live.send_back(r) + " Then call check_fix again."
    elif r["status"] == "cant":
        text += " This isn't a pass: tell the user Bite couldn't check it, and why."
    return (text, False)


def answer(msg: dict):
    """The reply to one JSON-RPC message, or None for a notification."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    method, mid = msg.get("method"), msg.get("id")
    if "id" not in msg:
        return None  # notifications (initialized, cancelled) need no reply
    params = msg.get("params") or {}
    if method == "initialize":
        from recent import _installed_version
        result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "bite", "version": _installed_version()},
                  "instructions": "After you fix a bug, call check_fix before you tell the user it's fixed."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        if params.get("name") != TOOL["name"]:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": f"Unknown tool: {params.get('name')}"}}
        try:
            text, err = check_fix(params.get("arguments") or {})
        except Exception as e:  # a broken check is reported to the AI, never a dead server
            text, err = f"Bite's check stopped with an error: {type(e).__name__}: {e}", True
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(inp, out) -> int:
    """Read one JSON message per line from inp (bytes), write each reply as one line to out (bytes)."""
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = answer(msg)
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            out.flush()
    return 0


def main(argv: list) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    # stdout carries the JSON only. Keep a private handle on it, then point fd 1 at stderr, so nothing Bite or
    # the tests print (even from a child process) can get mixed into a reply.
    sys.stdout.flush()
    out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return serve(sys.stdin.buffer, out)
