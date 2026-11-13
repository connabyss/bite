// Claude Code's Stop hook for Bite: hands the hook's JSON to `bite live --hook` and passes its answer back.
// A node file, so the hook starts the same way on Windows, macOS and Linux (no shell needed).
// If Bite isn't installed, it stays quiet and never blocks Claude: install it with `pipx install bite-check`.
const { spawnSync } = require("child_process");

const input = require("fs").readFileSync(0);
const tries = [
  ["bite", ["live", "--hook"]],
  ["python3", ["-m", "bite_check", "live", "--hook"]],
  ["python", ["-m", "bite_check", "live", "--hook"]],
];
for (const [cmd, args] of tries) {
  const r = spawnSync(cmd, args, { input, stdio: ["pipe", "inherit", "inherit"] });
  if (r.error && r.error.code === "ENOENT") continue; // not on PATH: try the next way to start Bite
  if (cmd !== "bite" && r.status !== 0) continue; // a Python without bite_check installed
  process.exit(r.status === null ? 0 : r.status);
}
process.stderr.write("Bite isn't installed, so the change wasn't checked. Install it: pipx install bite-check\n");
process.exit(0);
