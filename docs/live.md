# Check the "fixed" live

[← Back to the README](https://github.com/connabyss/bite#readme)

## Check Claude's "fixed" live, in Claude Code

Bite can also check the moment Claude says it fixed something, before you read "fixed!". Each time Claude finishes
a turn that changed code, Bite takes the change back out of a copy of your project and runs your tests. If none of
them notice, Claude is sent back once to add a test that fails without its change. If it stops again and still no
test notices, you get a warning instead, so it never goes round in circles. It's the free check: no API key.

In Claude Code, type:

```
/plugin marketplace add connabyss/bite
/plugin install bite-check@bite
/plugin install fixed-or-not@bite
```

and install Bite itself if you haven't:

```
pipx install bite-check
```

`/bite` checks the changes since your last commit whenever you like. In a trial, Claude fixed a discount and then
wrote `assert total([50, 50], 10) == 90`. That passes with or without the fix (100 - 10 and 100 × 90% are both
90), and Bite said so:

```
Bite ⚠️ the tests that came with this change (test_cart.py) don't notice it: with the change to cart.py taken out,
they still pass. The "fixed" isn't proven yet.
```

Without the plugin, run `bite live` yourself after a change, or `bite live --hook` from any tool that runs a
command when the AI stops (it reads Claude Code's Stop hook JSON).

## Check the "fixed" live, in any coding AI

`bite mcp` gives your coding AI the same free check as a tool it can call, `check_fix`, through MCP, the plug most
coding AIs share. Its description tells the AI to call it after fixing a bug and before saying "fixed". If no test
notices the change, the AI is told to add one that fails without it. No API key; it works in a copy, so your files
are never touched. It needs Bite 0.8.0 or newer ([Updating Bite](install.md#updating-bite)).

Add it once, in the place your coding AI keeps its MCP servers:

| Coding AI | Where | What to add |
|---|---|---|
| Claude Code | a terminal | `claude mcp add bite -- bite mcp` |
| Cursor | `.cursor/mcp.json` in the project (or `~/.cursor/mcp.json` for all) | `{"mcpServers": {"bite": {"command": "bite", "args": ["mcp"]}}}` |
| Copilot in VS Code | `.vscode/mcp.json` in the project | `{"servers": {"bite": {"type": "stdio", "command": "bite", "args": ["mcp"]}}}` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `{"mcpServers": {"bite": {"command": "bite", "args": ["mcp"]}}}` |
| Codex CLI | a terminal | `codex mcp add bite -- bite mcp` |
| Gemini CLI | `.gemini/settings.json` in the project (or `~/.gemini/settings.json`) | `{"mcpServers": {"bite": {"command": "bite", "args": ["mcp"]}}}` |

Any other AI that takes MCP servers: the command is `bite`, the argument is `mcp`. If yours says it can't start
`bite` (apps opened from the Dock or Start menu don't always see the folder pipx put it in), use the full path
instead: `~/.local/bin/bite` on Mac and Linux, `C:\Users\<you>\.local\bin\bite.exe` on Windows (`pipx list`
shows it). The tool checks the folder Bite was started in; the AI can pass `folder` for another one, and `since`
(for example `main`) to check a whole branch, not just what changed since the last commit.

An AI that can run commands but takes no MCP servers can run `bite live` itself: it prints the same answer and
exits with 1 when no test noticed the change. Put a line like "After you fix a bug, run `bite live` before you
say it's fixed" in its rules file (AGENTS.md, .cursorrules, .github/copilot-instructions.md).
