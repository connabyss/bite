"""
Bite's engine for recent.py: reading the settings, running a project's tests (optionally in a Docker box),
copying a project safely, and the command filter that keeps the claim-checking worker inside its copy.
You shouldn't need to edit this file.
"""




import configparser


import fnmatch




import os


import re


import shlex


import subprocess


import sys


import time


from pathlib import Path


KIT_DIR = Path(__file__).resolve().parent


for _s in (sys.stdout, sys.stderr):  # a Windows console or log file can't print every character a worker writes
    try:
        _s.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


CONFIG_FILE = Path(os.environ["BITE_CONFIG"]).resolve() if os.environ.get("BITE_CONFIG") else KIT_DIR / "bite_config.ini"


KEY_FILE = KIT_DIR / "key.txt"


def _list(value: str) -> list:
    return [v.strip() for v in re.split(r"[,\n]", value or "") if v.strip()]


DEFAULT_FAIL = r"\bFAIL|SCRIPT ERROR|SHADER ERROR|Parse Error|parse error|ignoring script|Traceback"
# A line that reports a test that passed: its name can say "parse error" or "FAIL" (mocha's "✔ should persist
# store when parse error"), and that is not a failure. Mocha writes its marks as UTF-8; read with Windows' usual
# code page they arrive as "âœ”", "âœ“" or "âˆš".
PASSED_LINE = re.compile(r"^\s*(?:[✔✓√]|âœ”|âœ“|âˆš|ok\b|PASS(?:ED)?\b|--- PASS\b)")


def settings_section(cp) -> dict:
    """The settings in a .bite.ini: its [bite] section, or [kit], the name it had before 0.9 (still read)."""
    return next((cp[name] for name in ("bite", "kit") if name in cp), {})


class Config:
    def __init__(self, path: Path = CONFIG_FILE):
        if not path.exists():
            raise SystemExit(f"No {path.name} found. Settings are optional: run bite in your repo "
                             "to guess the test command, or create .bite.ini there with a [bite] section.")
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path, encoding="utf-8")
        g = settings_section(cp)
        self.project = Path(os.path.expandvars(os.path.expanduser(g.get("project_folder", "")))).resolve()
        mb = g.get("mailbox_folder", "") or str(KIT_DIR / "mailbox")
        self.mailbox = Path(os.path.expandvars(os.path.expanduser(mb))).resolve()
        self.about = g.get("about_project", "").strip()
        self.model = g.get("model", "sonnet").strip() or "sonnet"
        self.budget = float(g.get("budget_per_run_usd", "3.00"))
        self.job_budget = float(g.get("budget_per_job_usd", "1.00"))
        self.max_turns = int(g.get("max_turns_per_job", "30"))
        self.poll = float(g.get("poll_seconds", "5"))
        self.programs = _list(g.get("allowed_programs", ""))
        self.secrets = [s.lower() for s in _list(g.get("secret_files", "key.txt, .env"))]
        self.protected = [p.lower() for p in _list(g.get("protected_files", ""))]
        self.extra_rules = g.get("extra_rules", "").strip()
        self.org_id = g.get("expected_org_id", "").strip()
        self.test_cmd = g.get("test_command", "").strip()
        self.fail_pattern = g.get("test_fail_pattern", "").strip() or DEFAULT_FAIL
        self.count_pattern = g.get("test_count_pattern", "").strip()
        self.test_glob = _list(g.get("test_files", "")) or DEFAULT_TEST_FILES
        self.test_timeout = int(g.get("test_timeout_seconds", "600"))
        self.copy_ignore = _list(g.get("bite_copy_ignore", "")) or ["__pycache__", "node_modules"]
        self.bite_prepare = g.get("bite_prepare_command", "").strip()
        lk = g.get("heavy_lock_folder", "").strip()
        self.lock_dir = Path(os.path.expandvars(os.path.expanduser(lk))).resolve() if lk else None
        self.lane = g.get("proof_lane", "cpu").strip() or "cpu"
        self.look_cmd = g.get("look_command", "").strip()
        self.look_lane = g.get("look_lane", "gpu").strip() or "gpu"
        self.judge_model = g.get("judge_model", "sonnet").strip() or "sonnet"
        self.judge_budget = float(g.get("judge_budget_usd", "0.25"))
        self.proofs = dict(cp["proofs"]) if "proofs" in cp else {}
        self.sandbox = g.get("sandbox", "copy").strip().lower() != "off"
        self.sandbox_ignore = _list(g.get("sandbox_ignore", "")) or ["__pycache__", "node_modules"]
        self.apply_when = g.get("apply_when", "pass").strip().lower() or "pass"
        self.review_only = _list(g.get("review_only_files", "")) or REVIEW_ONLY_DEFAULT
        self.contain = g.get("contain_command", "").strip()
        self.box_image = g.get("box_image", "python:3.12").strip() or "python:3.12"
        self.box_setup = g.get("box_setup_command", "").strip()
        self.box_test_cmd = g.get("box_test_command", "").strip()
        self.retries = int(g.get("retries_per_job", "2") or 0)
        self.mutants = int(g.get("planted_bugs", "4") or 0)
        self.mutant_seconds = int(g.get("planted_bugs_seconds", "300") or 300)
        self.repeats = int(g.get("repeat_runs", "0") or 0)
        self.ok_codes = {int(x) for x in _list(g.get("ok_exit_codes", "0")) if x.strip().lstrip("-").isdigit()} or {0}
        self.day_budget = float(g.get("budget_per_day_usd", "0") or 0)
        self.sync_before = g.get("sync_before", "").strip()
        self.sync_after = g.get("sync_after", "").strip()
        self.sync_seconds = float(g.get("sync_seconds", "60") or 60)
        self.facts_file = g.get("facts_file", "").strip()
        n = cp["night"] if "night" in cp else {}
        self.intent_file = n.get("intent_file", "").strip()
        self.crowd_cmd = n.get("crowd_command", "").strip()
        self.personas = _list(n.get("personas", "")) or ["speedrunner", "first_timer", "masher", "quitter"]
        self.crowd_seeds = int(n.get("crowd_seeds", "20") or 20)
        self.boredom_seconds = float(n.get("boredom_seconds", "45") or 45)
        self.immune_folder = (n.get("immune_folder", "").strip() or guess_immune(self.project)).strip("/")
        self.night_fixes = int(n.get("max_fixes", "5") or 5)
        self.night_budget = float(n.get("budget_per_night_usd", "0") or 0) or self.budget
        self.night_without_box = n.get("night_without_box", "no").strip().lower() in ("yes", "true", "1", "on")
        self.run_without_box = g.get("run_without_box", "no").strip().lower() in ("yes", "true", "1", "on")
        # persona: event it lives for, e.g. humor_hunter: funny  (the hook logs a "funny" event per joke shown)
        self.seeks = {k.strip(): v.strip() for k, v in (x.split(":", 1) for x in _list(n.get("persona_seeks", "")) if ":" in x)}
        self.seek_seconds = float(n.get("seek_seconds", "120") or 120)
        pn = cp["panel"] if "panel" in cp else {}
        self.panel = _list(pn.get("members", ""))
        self.panel_files = _list(pn.get("material_files", ""))
        self.panel_cmd = pn.get("material_command", "").strip()
        self.panel_stills = pn.get("stills_folder", "").strip()
        self.panel_taste = pn.get("taste_file", "").strip()
        self.panel_briefs = {k[6:].strip(): v.strip() for k, v in pn.items() if k.startswith("brief ")}
        self.scratch = _list(g.get("scratch_files", "")) or [
            "__pycache__/*", "*.pyc", ".pytest_cache/*", "node_modules/*", ".godot/*", "*.import", "*.log",
            "*.tmp", ".cache/*", "build/*", "dist/*", "target/*", "bin/*", "obj/*", ".hypothesis/*", ".mypy_cache/*",
            ".ruff_cache/*", ".tox/*", ".nox/*", ".coverage", ".coverage.*", "htmlcov/*", ".nyc_output/*", "coverage/*", "coverage.xml", "coverage.json", "lcov.info", "*.lcov", "junit*.xml", "test-results/*"]
        self.test_setup = _list(g.get("test_setup_files", "")) or [
            "conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "package.json",
            "run_tests*", "*test_runner*", "*testrunner*", "tests/helpers/*", "test/helpers/*"]

    @property
    def inbox(self):
        return self.mailbox / "to_agent"

    @property
    def outbox(self):
        return self.mailbox / "from_agent"


SAFE_COMMANDS = {
    "cd", "ls", "dir", "cat", "head", "tail", "grep", "egrep", "rg", "wc", "echo", "printf", "pwd",
    "date", "sleep", "which", "where", "test", "sort", "uniq", "diff", "file", "stat", "tr", "cut",
    "basename", "dirname", "true", "tasklist", "find", "du", "realpath", "readlink", "type",
    "for", "do", "done", "then", "fi", "if", "else",
}


REVIEW_ONLY_DEFAULT = [  # files that can run code or steer agents: a person looks first (any depth)
    ".claude/*", "CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".mcp.json", ".cursor/*", ".github/*",
    ".gitlab-ci.yml", ".circleci/*", ".vscode/*", ".idea/*", ".husky/*", ".githooks/*",
    ".pre-commit-config.yaml", ".gitattributes", ".gitmodules", ".envrc", ".npmrc", ".yarnrc*",
    ".pypirc", "Makefile", "*.mk", "Dockerfile", "docker-compose*", "sitecustomize.py",
    "usercustomize.py", "*.pth", "*.bat", "*.cmd", "*.ps1", "*.sh", "*.desktop", "*.lnk"]


SAFE_GIT = {"status", "log", "diff", "show", "ls-files", "rev-parse", "blame", "shortlog", "describe", "grep", "branch"}


DANGER = re.compile(
    r"(\brm\b|\brmdir\b|\bdel\b|\brd\b|\bmv\b|(?<![-=%])\bformat\b|\bshutdown\b|\btaskkill\b|\bsudo\b"
    r"|\bcurl\b|\bwget\b|\bpip3?\b|\bnpm\b|\bnpx\b|\bwinget\b|\bchoco\b"
    r"|\bgit\s+(push|reset|clean|rebase|checkout|restore|remote|config|commit|add|stash|merge|pull)"
    r"|--force|--hard|Remove-Item|rmtree|os\.remove|os\.unlink|shutil\.|\bsubprocess\b"
    r"|\bfind\b[^|;&]*(-delete|-exec|-ok|-fprint|-fls)"
    r"|--output|--to-file|--ext-diff|--pre\b|--set\b|\bsort\b[^|;&]*\s-\w*o"
    r"|\bdate\b[^|;&]*\s-s\b|(?-i:\bgit\s+(-\S+\s+)*-[cp]\b)|--compress-program|--open-files-in-pager|--paginate|(?-i:\s-O\S*)|/proc\b|/dev/(tcp|udp)\b)",
    re.IGNORECASE,
)


def split_commands(s: str) -> list:
    """Split on && || ; | and newlines, but not inside quotes."""
    parts, cur, q, i = [], "", "", 0
    while i < len(s):
        c = s[i]
        if q:
            cur += c
            if c == q:
                q = ""
        elif c in "'\"":
            q = c
            cur += c
        elif c in "&|" and s[i:i + 2] in ("&&", "||"):
            parts.append(cur)
            cur = ""
            i += 1
        elif c in ";|&\n":
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    parts.append(cur)
    return parts


ENV_PEEK = re.compile(r"environ|\{[^}\s]*(,|\.\.)[^}\s]*\}", re.I)  # /proc/self/environ, {k,x}ey.txt


def unquoted(cmd: str) -> str:
    """The command with the inside of each quoted word blanked, except words that are options
    ("--output=x" stays visible, so quoting a flag hides nothing)."""
    def keep(m):
        inner = m.group(0)[1:-1]
        return m.group(0) if inner.lstrip().startswith("-") or "/proc" in inner else '""'
    return re.sub(r"'[^']*'|\"[^\"]*\"", keep, cmd)


def var_refs_ok(cmd: str) -> bool:
    """$NAME is refused (it could print the API key or reach another folder), except the
    variable of a `for NAME in ...` loop in the same command. Inside '...' nothing expands."""
    loop_vars = set(re.findall(r"\bfor\s+([A-Za-z_]\w*)\s+in\b", cmd))
    q, i = "", 0
    while i < len(cmd):
        c = cmd[i]
        if q == "'":
            q = "" if c == "'" else q
        elif c == "'" and not q:
            q = "'"
        elif c == '"':
            q = "" if q == '"' else '"'
        elif c == "\\":
            i += 1
        elif c == "$" and not q and i + 1 < len(cmd) and cmd[i + 1] in "'\"":
            return False  # $'\x6bey.txt' spells key.txt
        elif c == "$" and i + 1 < len(cmd) and re.match(r"[A-Za-z0-9_{(!@#*?$-]", cmd[i + 1]):
            m = re.match(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))", cmd[i:])
            if not m or (m.group(1) or m.group(2)) not in loop_vars:
                return False
        i += 1
    return True


def path_ok(tok: str, here: Path, cfg: Config) -> bool:
    """A word that names a path must stay inside the project (the job's copy of it)."""
    if tok.startswith("-"):
        if "=" not in tok:
            return True
        tok = tok.split("=", 1)[1]
    elif "=" in tok and not path_ok(tok.split("=", 1)[1], here, cfg):
        return False  # -o cache_dir=/anywhere: the value after = can be a path too
    if not tok:
        return True
    if tok.startswith("~"):
        return False
    base = re.split(r"[*?\[]", tok, maxsplit=1)[0] or "."
    globbed = base != tok
    if globbed and any(c == ".." or (c.startswith(".") and fnmatch.fnmatchcase("..", c)) for c in re.split(r"[/\\]", tok)):
        return False  # */../../x or .*/x (.* matches ..): the part before the pattern is inside, the pattern climbs out
    if re.match(r"^[A-Za-z]:[\\/]?", base) or base.startswith(("/", "\\")):
        if not re.match(r"^[A-Za-z]:", base) or WINDOWS:
            target = Path(base)
            if inside(cfg.project, str(target)) is not None:
                return True
            if globbed:
                return False  # /pro[c]/... or /e*/passwd: a pattern aimed outside the project
            first = Path(target.anchor) / target.parts[1] if len(target.parts) > 1 else Path(target.anchor)
            return not first.exists()  # "/api/" is a search word; "/etc/x" and "C:\Users" are places
        return False
    if not re.search(r"[/\\]", base) and base not in ("..", "."):
        return True  # a plain name in the current folder (or a search word)
    return inside(cfg.project, str(here / base)) is not None


def segment_ok(seg: str, cfg: Config, here: list) -> bool:
    try:
        toks = shlex.split(seg.strip(), posix=True)
    except ValueError:
        return False
    if toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        return False  # GIT_PAGER=, GIT_EXTERNAL_DIFF=, LD_PRELOAD=... turn any tool into "run this"
    while toks and toks[0] in ("do", "then", "else"):  # before timeout: "do timeout 580 ..."
        toks.pop(0)
    if toks and toks[0] == "timeout":
        toks = toks[1:]
        if toks and re.match(r"^\d+[smh]?$", toks[0]):
            toks = toks[1:]
    if not toks:
        return True
    for i, t in enumerate(toks):
        low = t.lower()
        if any(sec in low for sec in cfg.secrets) or is_secret(Path(low.replace("\\", "/")).name, cfg):
            return False  # catches 'key'.txt and key''.txt once the quotes are gone
        glob = Path(low.replace("\\", "/")).name
        if re.search(r"[*?\[]", glob):
            lead = re.split(r"[*?\[]", glob, maxsplit=1)[0]
            if any(fnmatch.fnmatch(sec, glob) and (lead or not cfg.sandbox) for sec in cfg.secrets):
                return False  # k*.txt aims at key.txt (and with no copy, even *.txt could reach it)
        if i and not path_ok(t, here[0], cfg):
            return False  # the program itself is checked below; its arguments must stay inside
    head = toks[0].replace("\\", "/")
    name = head.rsplit("/", 1)[-1]
    if name == "cd":
        if len(toks) != 2:
            return False  # bare cd goes home, cd - goes back out
        new = inside(cfg.project, str(here[0] / toks[1]))
        if new is None:
            return False
        here[0] = new
        return True
    if name == "uniq" and len([t for t in toks[1:] if not t.startswith("-")]) > 1:
        return False  # uniq IN OUT writes OUT
    if name in SAFE_COMMANDS:
        return True
    if name in ("git", "git.exe"):
        args = toks[1:]
        while len(args) > 1 and args[0] == "-C":  # git -C sub status: sub was path-checked above
            args = args[2:]
        rest = [t for t in args if not t.startswith("-") and "=" not in t]
        if rest and rest[0] == "branch":
            return all(t in ("branch", "-a", "-r", "-v", "-vv", "--list", "--show-current", "--all") for t in args)
        return bool(rest) and rest[0] in SAFE_GIT
    if name.lower() in ("python", "python3", "py", "bash", "sh", "cmd", "powershell", "pwsh"):
        return False  # no scripts: they could do anything
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in cfg.programs)


def command_ok(cmd: str, cfg: Config) -> bool:
    if any(t in cmd for t in ("<<", ">", "`", "$(")):
        return False  # no heredocs, redirects or command substitution
    low = cmd.lower()
    if any(s in low for s in cfg.secrets):
        return False
    bare = unquoted(cmd)  # "rm" or "format(" inside quotes is a search word, not a command
    if DANGER.search(bare) or ENV_PEEK.search(bare) or not var_refs_ok(cmd):
        return False
    here = [cfg.project]
    return all(segment_ok(seg, cfg, here) for seg in split_commands(cmd))


def uses_program(cmd: str) -> bool:
    """True if the command runs an allowed program, not just a read-only built-in or git."""
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg.strip(), posix=True)
        except ValueError:
            return True
        while toks and (toks[0] in ("do", "then", "else", "timeout") or re.match(r"^\d+[smh]?$", toks[0])):
            toks.pop(0)
        if toks and toks[0].replace("\\", "/").rsplit("/", 1)[-1] not in SAFE_COMMANDS | {"git", "git.exe"}:
            return True
    return False


def guess_immune(project: Path) -> str:
    """Where the night's immune tests go when the config doesn't say: inside the folder the project's
    own test run collects (a project with testpaths = test never sees tests/immune)."""
    for name, pat in (("pytest.ini", r"(?ms)^\[pytest\].*?^testpaths\s*=\s*([^\s#;]+)"),
                      ("pyproject.toml", r"(?ms)^\[tool\.pytest\.ini_options\].*?^testpaths\s*=\s*\[?\s*[\"']?([^\"'\s,\]]+)"),
                      ("tox.ini", r"(?ms)^\[pytest\].*?^testpaths\s*=\s*([^\s#;]+)"),
                      ("setup.cfg", r"(?ms)^\[tool:pytest\].*?^testpaths\s*=\s*([^\s#;]+)")):
        try:
            m = re.search(pat, (project / name).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if m and (project / m.group(1)).is_dir():
            return m.group(1).strip("./").rstrip("/") + "/immune"
    if not (project / "tests").is_dir() and (project / "test").is_dir():
        return "test/immune"
    return "tests/immune"


def program_wrapper(cfg: Config, cmd: str) -> str:
    """The worker's program runs under the kit: no API key in its environment, killed with
    everything it started if it overruns, and one per lane when a heavy-run lock is set."""
    secs = max(30, min(cfg.test_timeout, 590))  # the Bash tool moves runs past 600 s to the background
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(KIT_DIR / 'bite.py'))} --run {secs} -- {shlex.quote(cmd)}"


def contain(cfg: Config, cmd: str, folder: Path, posix: bool | None = None) -> str:
    """With contain_command set, a command that runs project code goes into that box
    (for example a container with no network and only the job's copy mounted).
    posix: the command is handed to a bash-like shell (the worker's), not cmd.exe."""
    if not cfg.contain:
        return cmd
    if posix is None:
        posix = not WINDOWS
    quoted = shlex.quote(cmd) if posix else '"' + cmd.replace('"', '\\"') + '"'
    box = cfg.contain
    if box.lstrip().startswith("docker run ") and "--name" not in box and "--rm" in box:  # without --rm, a reused name would clash
        # Named, so a timeout can remove it: killing the docker client leaves the box running,
        # and a stuck box's test process then blocks every later proof ("one at a time").
        _BOX_N[0] += 1
        box = box.replace("docker run ", f"docker run --name bite-{os.getpid()}-{_BOX_N[0]} ", 1)
    return box.replace("{project}", str(folder)).replace("{cmd}", quoted)


_BOX_N = [0]


def inside(folder: Path, file_path: str) -> Path | None:
    try:
        target = Path(folder, file_path).resolve()
        target.relative_to(folder.resolve())
        return target
    except (ValueError, OSError):
        return None


def kit_owned(target: Path) -> bool:
    try:
        target.relative_to(KIT_DIR)
        return True
    except ValueError:
        return False


def edit_ok(file_path: str, cfg: Config) -> bool:
    target = inside(cfg.project, file_path)
    if target is None or kit_owned(target):
        return False
    name = target.name.lower()
    if ".git" in target.parts or is_secret(name, cfg) or name in cfg.protected:
        return False
    if not cfg.sandbox and review_only(target.relative_to(cfg.project.resolve()).as_posix(), cfg):
        return False  # no copy to hold it for review, so it is not written at all
    return name not in ("bite.py", "bite_config.ini", "key.txt")


def review_only(rel: str, cfg: Config) -> bool:
    parts = rel.replace("\\", "/").lower().split("/")
    for pat in (p.lower() for p in cfg.review_only):
        if pat.endswith("/*") and pat[:-2] in parts[:-1]:
            return True  # .claude/* also catches sub/.claude/settings.json
        if fnmatch.fnmatch("/".join(parts), pat) or fnmatch.fnmatch(parts[-1], pat):
            return True
    return False


def is_secret(name: str, cfg: Config) -> bool:
    """Secret names match in any case, and .env also covers .env.local and friends."""
    n = name.lower()
    return any(n == s or n.startswith(s + ".") or fnmatch.fnmatch(n, s) for s in cfg.secrets)


def read_ok(tool_input: dict, cfg: Config) -> bool:
    p = tool_input.get("file_path") or tool_input.get("path") or str(cfg.project)
    names = [p, tool_input.get("glob") or ""]  # a search WORD may mention .env; a path or glob may not
    if any(is_secret(Path(n.replace("\\", "/").lower()).name, cfg) or any(s in n.lower() for s in cfg.secrets)
           for n in names if n):
        return False
    if ".git" in Path(p).parts:
        return False  # git internals (and any hidden tests kept there) stay unseen
    return inside(cfg.project, p) is not None  # the job text is in the prompt; the mailbox stays shut


JOB_EDITS = {}  # path -> the file's bytes before the agent first touched it (None = it was new)


RUN_BASE = {}  # (project, relative path) -> the file as it was the first time a worker touched it this run


def remember_original(cfg: Config, file_path: str):
    target = inside(cfg.project, file_path)
    if target is not None and str(target) not in JOB_EDITS:
        JOB_EDITS[str(target)] = target.read_bytes() if target.is_file() else None
        RUN_BASE.setdefault((str(getattr(cfg, "origin", cfg.project)), target.relative_to(cfg.project).as_posix()),
                            JOB_EDITS[str(target)])


def refusal_hint(tool: str, cmd: str, cfg: Config) -> str:
    """Say what to use instead, so a refusal costs one turn, not five."""
    if tool != "Bash":
        return f"{tool} isn't available to workers. Use Read/Glob/Grep to look and Edit/Write inside the project."
    if any(t in cmd for t in (">", "<<")):
        return "No redirects or heredocs: write files with the Edit or Write tool."
    if "$" in cmd:
        return "No variables ($NAME): write the value out, or use a for loop's own variable."
    if re.search(r"(^|\s)(~|/|\.\.|[A-Za-z]:\\)", cmd):
        return "Paths must stay inside the project folder (your working directory)."
    if re.match(r"\s*(python3?|py|bash|sh|cmd|powershell|pwsh|node)\b", cmd):
        return ("No scripts. To check behaviour, write a test file and let the kit run the tests"
                + (f", or run an allowed program ({', '.join(cfg.programs)})." if cfg.programs else "."))
    if re.search(r"\bgit\b", cmd):
        return "Only read-only git (status, log, diff, show, blame, grep, ls-files). The planners commit."
    if re.search(r"\b(rm|del|mv|cp)\b", cmd):
        return "No deleting or moving files. Edit or Write a file instead; leave deletions to the person."
    return ("Only read-only commands (ls, cat, grep, find, head, wc, diff, sort...), read-only git"
            + (f" and {', '.join(cfg.programs)}" if cfg.programs else "") + " work.")


def make_permission(cfg: Config, log=print):
    async def permission(tool_name, tool_input, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        if tool_name in ("Read", "Glob", "Grep"):
            if read_ok(tool_input, cfg):
                return PermissionResultAllow(updated_input=tool_input)
            log(f"  [REFUSED] {tool_name} outside the project or a secret file")
            return PermissionResultDeny(message="Only files inside the project may be read, and never secret files.")
        if tool_name in ("Edit", "Write", "NotebookEdit") and edit_ok(
                tool_input.get("file_path") or tool_input.get("notebook_path") or "", cfg):
            log(f"  [edit] {tool_input.get('file_path', '')}")
            remember_original(cfg, tool_input.get("file_path") or tool_input.get("notebook_path") or "")
            return PermissionResultAllow(updated_input=tool_input)
        if tool_name in ("TodoWrite",):
            return PermissionResultAllow(updated_input=tool_input)
        if tool_name == "Bash" and tool_input.get("run_in_background"):
            log("  [REFUSED] background command")
            return PermissionResultDeny(message="Background commands are refused. Run it in the foreground and wait.")
        if tool_name == "Bash" and cfg.test_cmd and tool_input.get("command", "").strip() == "bite-test":
            log("  [run] bite-test (the kit's own test command)")
            command = tests_cmd(cfg).replace("{project}", str(cfg.project)).replace("{seed}", SEED[0])
            if cfg.contain:  # run by the kit's --run, so quoted for this OS's shell (cmd.exe on Windows)
                command = contain(cfg, command, cfg.project)
            return PermissionResultAllow(updated_input={**tool_input, "command": program_wrapper(cfg, command)})
        if tool_name == "Bash" and command_ok(tool_input.get("command", ""), cfg):
            first = (tool_input.get("command", "").strip().splitlines() or [""])[0]
            log(f"  [run] {first[:110]}")
            command = tool_input["command"]
            wrapped = uses_program(tool_input["command"])
            if cfg.contain:  # with a box, every worker command runs in it
                # a wrapped command ends up in this OS's shell (cmd.exe on Windows), the rest in the
                # worker's bash, where Git Bash on Windows would turn -w /work into a Windows path
                command = contain(cfg, command, cfg.project, posix=None if wrapped else True)
                if WINDOWS and not wrapped:
                    command = "MSYS_NO_PATHCONV=1 " + command
            if wrapped:
                command = program_wrapper(cfg, command)
            if command != tool_input["command"]:
                tool_input = {**tool_input, "command": command}
            return PermissionResultAllow(updated_input=tool_input)
        target = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("url") or ""
        log(f"  [REFUSED] {tool_name}: {str(target)[:110]}")
        return PermissionResultDeny(message="Refused. " + refusal_hint(tool_name, str(target), cfg) +
                                    " Don't work around it; if it's truly needed, say in your report what the "
                                    "person would need to run.")
    return permission


DEFAULT_TEST_FILES = ["test_*", "*_test.*", "test.*", "tests.*", "*.test.*", "*.spec.*", "*_spec.*",
                      "tests/*", "test/*", "__tests__/*", "spec/*",
                      "*tests.cs", "*test.cs", "*tests.fs", "*test.fs", "*.tests/*", "*.test/*",  # C#/F# (.NET) names
                      "*test.java", "*tests.java", "*test.kt", "*tests.kt",  # Java and Kotlin names
                      "*test/java/*", "*test/kotlin/*"]  # Gradle's other test folders: src/integrationTest/java, src/jvmTest/kotlin


def is_test_file(rel: str, cfg: Config) -> bool:
    """A pattern without a slash names a file (test_*); one with a slash names a folder (tests/*), which
    must be a whole folder name, so src/testkit/core.py and src/testfixtures/x.py stay code and get the proof."""
    rel = rel.replace("\\", "/").lower()
    name = rel.rsplit("/", 1)[-1]
    for g in (g.lower().replace("\\", "/") for g in cfg.test_glob):
        if "/" not in g:
            if fnmatch.fnmatchcase(name, g):
                return True
        elif any(fnmatch.fnmatchcase(tail, g) for tail in
                 ["/".join(rel.split("/")[i:]) for i in range(rel.count("/") + 1)]):
            return True
    return False


WINDOWS = os.name == "nt"


def run_cmd(cmd: str, cwd: Path, timeout: int):
    """Run one command; on timeout kill it AND its children by PID (a killed shell would
    otherwise leave the game engine running). Returns (exit code or None on timeout, output)."""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ANTHROPIC_", "CLAUDE_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # stale bytecode once faked a pass
    env["BITE_SEED"] = SEED[0]
    env.update(EXTRA_ENV)
    src = Path(cwd) / "src"
    if (src.is_dir() and not (src / "__init__.py").exists()
            and any((d / "__init__.py").exists() for d in src.iterdir() if d.is_dir())):
        # A src/ layout installed with pip install -e . would load the checkout's code, not this copy's.
        env["PYTHONPATH"] = os.pathsep.join(x for x in (str(src), env.get("PYTHONPATH", "")) if x)
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                         text=True, errors="replace", creationflags=flags, start_new_session=not WINDOWS)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            import signal
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
        for name in re.findall(r"--name (bite-\d+-\d+)", cmd):  # the box outlives its killed client
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                pass  # the timeout is still reported; a box left behind shows in docker ps
        out, _ = p.communicate()
        return None, out or ""


class HeavyLock:
    def __init__(self, folder, lane: str, max_hold: int, who: str = "bite"):
        self.path = Path(folder) / f"{lane}.lock" if folder else None
        self.lane, self.max_hold, self.who = lane, max_hold, who

    def _holder(self):
        try:
            pid, start, _who = self.path.read_text(encoding="utf-8").split(" ", 2)
            return int(pid), float(start), _who.strip()
        except (OSError, ValueError):
            return None

    def acquire(self, wait: int) -> str:
        """'' when held; otherwise why not. Takes over a lock whose holder died or overran."""
        if not self.path:
            return ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        end = time.time() + wait
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {time.time():.0f} {self.who}".encode())
                os.close(fd)
                return ""
            except FileExistsError:
                h = self._holder()
                if h is None or not pid_alive(h[0]) or time.time() - h[1] > self.max_hold + 60:
                    self.path.unlink(missing_ok=True)  # dead or overran its own limit: take over
                    continue
                if time.time() >= end:
                    return f"{self.lane} lane busy ({h[2]}, pid {h[0]}) for over {wait}s"
                time.sleep(3)

    def release(self):
        if self.path:
            h = self._holder()
            if h and h[0] == os.getpid():
                self.path.unlink(missing_ok=True)


def locked_run(cfg: Config, cmd: str, cwd: Path, lane: str = ""):
    """run_cmd under the lane lock (if configured), with the watchdog timeout."""
    lock = HeavyLock(cfg.lock_dir, lane or cfg.lane, cfg.test_timeout)
    why = lock.acquire(cfg.test_timeout)
    if why:
        return None, f"not run: {why}"
    try:
        return run_cmd(contain(cfg, cmd, cwd), cwd, cfg.test_timeout)
    finally:
        lock.release()


EXTRA_ENV = {}  # e.g. BITE_PERSONA and BITE_OUT for a crowd run


SEED = ["0"]  # BITE_SEED for the next test run: 0 = the normal run, 1..N = the repeat runs


AUTO_COUNTS = [  # common runners' summary lines, so the test count works without test_count_pattern
    (r"(?:^=+ .*|^)\b\d+ (?:passed|failed|errors?)\b.* in [\d.]+s\b", r"\b(\d+) (?:passed|failed|errors?|xfailed|xpassed)\b"),  # pytest
    (r"^Ran (\d+) tests? in ", r"^Ran (\d+) tests? in "),  # unittest
    (r"^Tests:.* (\d+) total", r"^Tests:.* (\d+) total"),  # jest / vitest
    (r"^\s*(\d+) (?:passing|failing|pending)\b", r"^\s*(\d+) (?:passing|failing|pending)\b"),  # mocha
    (r"^\s*(?:#|ℹ) tests (\d+)\s*$", r"^\s*(?:#|ℹ) tests (\d+)"),  # node --test, tap, tape
    (r"^\s*Tests\s+.*\((\d+)\)\s*$", r"\((\d+)\)\s*$"),  # vitest
    (r"^\s*(\d+) tests? (?:passed|failed)\b", r"^\s*(\d+) tests? (?:passed|failed)\b"),  # ava
    (r"^\s*Total:\s+(\d+)\s*$", r"(\d+)"),  # uvu
    (r"^test result: \w+\. (\d+) passed", r"(\d+) (?:passed|failed)(?=;)"),  # cargo
    # Maven (surefire): the summary line of each module, not the per-class lines that end in "Time elapsed ..."
    (r"^(?:\[\w+\] )?Tests run: \d+, Failures: \d+, Errors: \d+, Skipped: \d+\s*$", r"Tests run: (\d+)"),
]


def auto_count(out: str):
    for find, add in AUTO_COUNTS:
        lines = [ln for ln in out.splitlines() if re.search(find, ln, re.M)]
        if lines:
            return sum(int(x) for ln in lines for x in re.findall(add, ln))
    return None


def tests_cmd(cfg: Config) -> str:
    """Inside the box the project is at /work and only the copy is mounted, so a test command that
    names files outside the project (a Windows runner script, say) needs its own box version."""
    return cfg.box_test_cmd if cfg.contain and cfg.box_test_cmd else cfg.test_cmd


# pytest's own exit codes, in words: "exit 3" alone tells nobody that pytest never got to the tests.
PYTEST_EXITS = {2: "pytest stopped before running your tests (a test file failed to load)",
                3: "pytest crashed while loading your tests (a test file may run code or call sys.exit when it loads)",
                4: "pytest was given options it doesn't know",
                5: "pytest found no tests"}


def exit_why(cmd: str, rc: int) -> str:
    return f"{PYTEST_EXITS[rc]} (exit {rc})" if "pytest" in cmd and rc in PYTEST_EXITS else f"exit {rc}"


def run_tests(cfg: Config, folder: Path) -> dict:
    cmd = tests_cmd(cfg).replace("{project}", str(folder)).replace("{seed}", SEED[0])
    rc, out = locked_run(cfg, cmd, folder)
    if rc is None:
        why = out if out.startswith("not run:") else f"timed out after {cfg.test_timeout}s (test_command must exit on its own)"
        return {"ok": False, "why": why,
                "fails": [], "count": None, "out": out}
    fails = [ln.strip() for ln in out.splitlines() if re.search(cfg.fail_pattern, ln) and not PASSED_LINE.match(ln)]
    count = None
    if cfg.count_pattern:
        m = re.findall(cfg.count_pattern, out)
        count = sum(int(x) for x in m) if m else 0
    else:
        count = auto_count(out)
    ok = rc in cfg.ok_codes and not fails and (count is None or count > 0)
    why = (exit_why(cmd, rc) if rc else "") or (fails[0][:160] if fails else "") or ("no tests ran" if count == 0 else "")
    return {"ok": ok, "why": why, "fails": fails, "count": count, "out": out}


def safe_write(root: Path, target: Path, data: bytes):
    """Write a file inside root, never through a symlink (the file or any folder above it)."""
    rel = target.relative_to(root)
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise OSError(f"refused to write through a link: {rel.as_posix()}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


LOAD_ERRORS = re.compile(r"ImportError|ModuleNotFoundError|SyntaxError|IndentationError|error(?:s)? during collection|"
                         r"Cannot find module|Parse Error|Failed to load script|could not compile|unresolved import|"
                         r"error CS\d{4}|error FS\d{4}|"
                         r"COMPILATION ERROR|Compilation failed|cannot find symbol|Unresolved reference|"
                         r"^e: \S+\.kts?:", re.M)  # javac and kotlinc through Maven and Gradle


CHECK_FAILS = re.compile(r"(?m)^\s*FAIL\b|AssertionError|\bassert\b|Expected|expected|FAILED .*::|✕|\bFAIL\b.*(?:!=|==|got|want)|panicked at|"
                         r"<<< FAILURE!|^\S+ > .+ FAILED$|AssertionFailedError|ComparisonFailure")  # JUnit (Maven, Gradle)


def load_failure(out: str) -> bool:
    """True when a failing run failed only because code couldn't load, with no failing check in it."""
    return bool(LOAD_ERRORS.search(out)) and not CHECK_FAILS.search(out)


HASH_COMMENTS = {".py", ".pyw", ".rb", ".sh", ".gd", ".r", ".pl", ".toml", ".yaml", ".yml", ".ini", ".cfg"}


def strip_comment(line: str, suffix: str) -> str:
    """Cut a trailing comment the way the file's language writes one: in Python // is floor division,
    and in any language a # or // inside a string (a URL) isn't a comment."""
    out, quote, i = [], "", 0
    hash_ = suffix in HASH_COMMENTS
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                out.append(line[i:i + 2]); i += 2; continue
            if c == quote:
                quote = ""
        elif c in "'\"`":
            quote = c
        elif (hash_ and c == "#") or (not hash_ and line.startswith("//", i)):
            break
        out.append(c)
        i += 1
    return "".join(out)


def pid_alive(pid: int) -> bool:
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if KEY_FILE.exists():
        return clean_key(KEY_FILE.read_text(encoding="utf-8-sig"))
    raise SystemExit("No API key. Set ANTHROPIC_API_KEY, or put your key in key.txt next to bite.py.")


def guess_test_command(folder: Path) -> str:
    """The usual test command for what's in the folder, or "" if nothing is obvious."""
    import json as _json
    f = Path(folder)
    if (f / "package.json").is_file():
        try:
            t = (_json.loads((f / "package.json").read_text(encoding="utf-8")).get("scripts") or {}).get("test", "")
        except ValueError:
            t = ""
        if t and "no test specified" not in t:
            return "npm test"
    if (f / "Cargo.toml").is_file():
        return "cargo test"
    if (f / "go.mod").is_file():
        return "go test ./..."
    jvm = jvm_test_command(f)
    if jvm:
        return jvm
    if (f / "ProjectSettings" / "ProjectVersion.txt").is_file():
        return ""  # Unity: its tests run inside the Unity editor (-runTests), not with dotnet test
    dotnet = dotnet_target(f)
    if dotnet:
        return "dotnet test " + (f'"{dotnet}"' if " " in dotnet else dotnet)
    if any((f / n).exists() for n in ("pytest.ini", "conftest.py", "tox.ini")) or \
            any(f.glob("test*/test_*.py")) or any(f.glob("test_*.py")) or any(f.glob("*/tests/test_*.py")):
        return ("python" if WINDOWS else "python3") + " -m pytest -q"
    return ""


def jvm_test_command(folder: Path) -> str:
    """Java and Kotlin: the project's own Gradle or Maven wrapper when it has one (it pins the version the project
    builds with), else the installed gradle or mvn. "" when the folder isn't a Gradle or Maven build."""
    f = Path(folder)
    gradle = any((f / n).is_file() for n in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"))
    if gradle or (f / "gradlew").is_file():
        if (f / "gradlew").is_file() or (f / "gradlew.bat").is_file():
            return ("gradlew.bat" if WINDOWS else "sh gradlew") + " test"
        return "gradle test"
    if (f / "pom.xml").is_file():
        if (f / "mvnw").is_file() or (f / "mvnw.cmd").is_file():
            return ("mvnw.cmd" if WINDOWS else "sh mvnw") + " -B test"
        return "mvn -B test"
    return ""


def dotnet_target(folder: Path) -> str:
    """The solution or project file dotnet test should run (it needs one named when there are several)."""
    f = Path(folder)
    for found in (sorted(f.glob("*.sln")) + sorted(f.glob("*.slnx")), sorted(f.glob("*.csproj")) + sorted(f.glob("*.fsproj"))):
        if found:
            return found[0].name
    tests = sorted(p for pat in ("*/*.csproj", "*/*/*.csproj", "*/*.fsproj", "*/*/*.fsproj") for p in f.glob(pat)
                   if "test" in p.name.lower())
    return tests[0].relative_to(f).as_posix() if len(tests) == 1 else ""


def clean_key(text: str) -> str:
    return text.replace("\ufeff", "").strip().strip("'\" ").split()[0] if text.strip() else ""


