"""
Bite live: checks a coding AI's "fixed" the moment it says it, before the person sees it.

    bite live             check the changes made since the last commit now (Claude Code's /bite runs this)
    bite live --since REF check the changes since REF (a commit or branch) instead
    bite live --hook      Claude Code's Stop hook: reads the hook's JSON on stdin, answers in JSON on stdout

The check is Bite's free one: the change is taken back out of a copy of the project and the tests are run. If
they still pass, no test shows the change does anything. It runs in a copy, so nothing of yours is touched, and
it needs no API key: when no test noticed, the coding AI already at work writes the missing test.

As a Stop hook it checks each time the AI finishes a turn that changed code (the same changes aren't checked
twice). When no test noticed, it sends the AI back once to add a test that fails without its change. If the
AI stops again and still no test notices, the person gets a warning instead, so it can never go round in circles.
"""

import contextlib
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bite  # noqa: E402
import recent  # noqa: E402
import repo  # noqa: E402


def changed(root: Path, base: str) -> list:
    """Files that differ from base in the working tree: committed since, staged, unstaged or new (not ignored)."""
    names = (repo.git(root, "diff", "--name-only", "--no-renames", base) or "").split("\n")
    names += (repo.git(root, "ls-files", "--others", "--exclude-standard") or "").split("\n")
    # A symbolic link holds a path, not code: copying it would write through the link in the copy.
    return list(dict.fromkeys(n for n in names if n and not (root / n).is_symlink()))


def fingerprint(root: Path, base: str, names: list) -> str:
    """Same changes, same answer: a hash of what each changed file holds now, so a turn that changed nothing
    new isn't checked again."""
    h = hashlib.sha256(base.encode())
    for n in sorted(names):
        p = root / n
        h.update(n.encode() + b"\0" + (p.read_bytes() if p.is_file() else b"<gone>") + b"\0")
    return h.hexdigest()[:16]


def snapshot(root: Path, cfg) -> Path:
    """A copy of the project as it is right now: HEAD, plus every uncommitted change and new file on top."""
    folder = recent.export(root, "HEAD", cfg)
    for n in changed(root, "HEAD"):
        src, dst = root / n, folder / n
        if src.is_file():
            bite.safe_write(folder, dst, src.read_bytes())
        elif dst.is_file():
            dst.unlink()
    return folder


def turn_base(root: Path, started: float) -> str:
    """The commit the turn started from. A turn that committed its own change is checked against the commit
    before its first one, so committing doesn't hide the change."""
    base = "HEAD"
    for line in (repo.git(root, "log", "-n50", "--format=%H %ct") or "").splitlines():
        sha, ct = line.split()
        if started and int(ct) >= started:
            base = f"{sha}^"
        else:
            break
    if repo.git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}") is None:
        return "HEAD"  # the turn made the repo's very first commit: nothing to compare with
    return base


def check(root: Path, base: str = "HEAD") -> dict:
    """Take the change since base out of a copy and run the tests. status is one of: nothing (no code the tests
    run changed), cant (the tests can't say: see why), guarded, unguarded, tests_blind (the tests that came with
    the change still pass without it)."""
    if repo.git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        return {"status": "cant", "why": "this repository has no commit yet, so there's nothing to compare with"}
    try:
        cfg = repo.load_cfg(root)
    except repo.ConfigError as e:
        return {"status": "cant", "why": str(e)}
    covers = recent.extras(root, cfg)
    if not cfg.test_cmd:
        return {"status": "cant", "why": "Bite found no test command; set test_command in .bite.ini"}
    names = changed(root, base)
    tests = [n for n in names if bite.is_test_file(n, cfg)]
    runs = repo.runs_language(cfg.test_cmd)[1]
    code = [n for n in names if n not in tests and Path(n).suffix.lower() in repo.CODE_SUFFIXES
            and not repo.is_setup(n, cfg) and (not runs or Path(n).suffix.lower() in runs)]
    if covers:
        import fnmatch
        code = [n for n in code if any(fnmatch.fnmatch(n, g) for g in covers)]
    r = {"code": code, "tests": tests, "key": fingerprint(root, base, names), "cmd": bite.tests_cmd(cfg)}
    if not code:
        return {**r, "status": "nothing"}
    missing = recent.preflight(cfg)
    if missing:
        return {**r, "status": "cant", "why": missing}
    folder = snapshot(root, cfg)
    fcfg = recent.at(cfg, folder)
    if cfg.free_cmd:  # the faster subset, as in the free pass
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
        r["cmd"] = cfg.free_cmd
    try:
        now = bite.run_tests(fcfg, folder)
        if not now["ok"]:
            return {**r, "status": "cant", "why": f"the tests fail with the change in ({now['why']})"}
        if recent.ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return {**r, "status": "cant", "why": "no tests ran"}
        recent.take_out(root, {"code": code, "before": base}, folder)
        out = bite.run_tests(fcfg, folder)
        if out["ok"]:
            test_code = [n for n in tests if Path(n).suffix.lower() in repo.CODE_SUFFIXES]
            return {**r, "status": "tests_blind" if test_code else "unguarded", "test_code": test_code}
        return {**r, "status": "guarded", "caught": recent.caught_by(out["out"])}
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


def files(names: list, n: int = 3) -> str:
    shown = ", ".join(names[:n])
    return shown + (f" and {len(names) - n} more" if len(names) > n else "")


def say(r: dict) -> str:
    """One plain line for the person."""
    s = r["status"]
    if s == "nothing":
        return "Bite: no code your tests run has changed, so there's nothing to check."
    if s == "cant":
        return f"Bite couldn't check this change: {r['why']}."
    if s == "guarded":
        who = f" ({r['caught']})" if r.get("caught") else ""
        return f"Bite ✅ a test noticed: with the change to {files(r['code'])} taken out, the tests fail{who}."
    if s == "tests_blind":
        return (f"Bite ⚠️ the tests that came with this change ({files(r['test_code'])}) don't notice it: with the "
                f"change to {files(r['code'])} taken out, they still pass. The \"fixed\" isn't proven yet.")
    return (f"Bite ⚠️ no test noticed the change to {files(r['code'])}: with it taken out, the tests still pass. "
            "The \"fixed\" isn't proven yet.")


def send_back(r: dict) -> str:
    """What the coding AI is told when it's sent back to add the test."""
    if r["status"] == "tests_blind":
        what = (f"including the tests you added or changed ({files(r['test_code'], 5)}). Those tests pass without your "
                "change, so they don't test it")
    else:
        what = "so no test shows your fix does anything"
    return (f"Bite checked your fix before the user sees it. It took your change to {files(r['code'], 5)} back out of a "
            f"copy of the project and ran the tests ({r['cmd']}): they all still passed, {what}. Before you say it's "
            "fixed, add a test that fails without your change and passes with it, and run it both ways to be sure. "
            "If this change isn't meant to change what the code does (a rename or a tidy-up), tell the user that "
            "instead of adding a test.")


# ---- the Stop hook --------------------------------------------------------------

def turn_start(data: dict) -> float:
    """When the person sent the message this turn answers (0 when the transcript can't say)."""
    started = 0.0
    path = data.get("transcript_path")
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines() if path else []
    except OSError:
        lines = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        content = (rec.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if rec.get("type") == "user" and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
            started = stamp(rec.get("timestamp"))  # the person wrote (tool results are logged as "user" too)
    return started


def stamp(ts) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def hook(data: dict) -> dict:
    """The Stop hook's answer: {} to stay quiet, a block that sends the AI back, or a note for the person."""
    root = repo.repo_root(data.get("cwd") or os.getcwd())
    if root is None:
        return {}
    base = turn_base(root, turn_start(data))
    state_file = repo.state_dir(root) / "live.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    names = changed(root, base)
    key = fingerprint(root, base, names)
    last = state.get("last") or {}
    r = last if last.get("key") == key else check(root, base)  # same changes as last time: same answer
    session = data.get("session_id", "")
    sent = state.get("sent_back") or {}
    out = {}
    if r["status"] in ("unguarded", "tests_blind"):
        if not data.get("stop_hook_active") and sent.get(session) != key:
            sent[session] = key  # once per session and change: the next stop gets the warning instead
            out = {"decision": "block", "reason": send_back(r)}
        elif last.get("key") != key or not last.get("warned"):
            out = {"systemMessage": say(r) + " Run /bite after adding a test to check again."}
            r["warned"] = True
    elif r["status"] == "guarded" and last.get("key") != key:
        out = {"systemMessage": say(r)}
    elif r["status"] == "cant" and last.get("key") != key:
        out = {"systemMessage": say(r)}
    state.update(last=r, sent_back=dict(list(sent.items())[-20:]))
    state_file.write_text(json.dumps(state), encoding="utf-8")
    return out


def main(argv: list) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    if "--hook" in argv:
        try:
            with contextlib.redirect_stdout(sys.stderr):  # stdout is for the hook's JSON only
                data = json.loads(sys.stdin.read() or "{}")
                out = hook(data)
        except Exception as e:  # a broken check must never get in the way of the person's session
            out = {"systemMessage": f"Bite's live check stopped with an error: {type(e).__name__}: {e}"}
        if out:
            print(json.dumps(out))
        return 0
    root = repo.repo_root(os.getcwd())
    if root is None:
        print("Bite: not inside a git repository.")
        return 1
    base = argv[argv.index("--since") + 1] if "--since" in argv and argv.index("--since") + 1 < len(argv) else "HEAD"
    if repo.git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}") is None:
        print(f"Bite: --since {base} isn't a commit or branch in this repository.")
        return 1
    print("Bite: taking the changes since " + ("the last commit" if base == "HEAD" else base)
          + " out of a copy and running the tests...", flush=True)
    r = check(root, base)
    print(say(r))
    if r["status"] in ("unguarded", "tests_blind"):
        print("To fix it: add a test that fails without the change and passes with it, then run bite live again.")
        return 1
    return 0
