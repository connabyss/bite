"""
Bite: did your coding agent's recent "done" commits really do what they said?

    bite                      check the last 40 commits (step 2 needs an API key)
    bite --version            print the installed version
    bite --free               step 1 only: no key, no cost
    bite --demo               try it on a tiny made-up project first (free, about 30 seconds)
    bite --last 80 --suspects 3 --budget 1.00
    bite --serious            only fix claims about data, money, logins, security, crashes or leaks
    bite --any                check commits even when none of them claims a fix
    bite --free-checks 10     how many commits step 1 checks (default 6)
    bite --again              test claims again even if an earlier run already tested them
    bite --all                same as plain bite (kept so older commands still work)
    bite --roast              the same results, worded a little more gently
    bite --since main         only commits that main doesn't have (the pull request check uses this)
    bite --write-tests        after the free check, write the missing test for each change no test noticed
                              (API key, capped by --budget; --suspects sets how many, default 3)
    bite live                 check the changes since the last commit now (bite live --help: the live check for
                              coding AIs, and the Claude Code plugin's Stop hook)
    (from a clone without installing: python recent.py, python recent.py --free, ...)

Step 1 (free): for each commit that changed code, the change is taken back out and the tests are run. If they
still pass, no test shows the change does anything ("unguarded"). If the commit added or changed tests and
those still pass without its code change, they test nothing it did ("TEST GUARDS NOTHING"). Commits that
claim a fix come first.
Step 2 (API key, spending capped by --budget): for the top suspects, a fresh worker turns the commit's own claim into one
small test (with the odd inputs the claim covers) on a copy of the project at that commit. Bite then runs the
test itself, twice, at that commit and on today's code, and a second fresh check must agree that the test asks
only for what the commit claimed and fails for a real reason. Only then is it shown as a false "done".

Results are written to bite_proof/ in the repo: report.html (one page to open in a browser), and each
failing test plus the command that runs it.
--write-tests (API key, capped by --budget): for each change no test noticed, a fresh worker writes the test that's
missing, on a copy at that commit. Bite runs it itself and keeps it only if it passes twice with the change in,
fails with the change taken out, and a second fresh check calls it fair. It's shown ready to paste in (and in the pull request comment). Instead of step 2.
Settings: .bite.ini in the repo (optional; first line [kit], then test_command = ...). claim_command runs one
test file ({file}); without it Bite adds the file to test_command (for dotnet test it adds a --filter instead).
test_covers = the paths the test command can reach (globs, comma-separated, e.g. Assets/Sim/*, tests/*): commits
that touch none of them are listed as outside the tests' reach, not checked. Code in a language the test command
doesn't run (TypeScript under pytest) is listed as code the tests can't run, not checked. free_test_command = a
faster subset of the tests for step 1 (step 2 still uses test_command).

Step 2 runs on Anthropic's Agent SDK, so it needs an Anthropic API key and never uses a Claude login or plan:
Anthropic's rules for tools built on the Agent SDK (https://code.claude.com/docs/en/agent-sdk/overview) say they
must use API keys. The commits it checks can come from any coding AI or person.
"""

import ast
import asyncio
import io
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bite  # noqa: E402
import repo  # noqa: E402

CLAIM = re.compile(r"\b(fix(e[sd])?|handle[sd]?|prevent[sd]?|correct(s|ed)?|resolve[sd]?|guard|avoid[sd]?|"
                   r"support[sd]?|make[sd]? .* work|no longer|now (works|handles|returns|accepts|respects))\b", re.I)
NOT_CODE = re.compile(r"\b(docs?|readme|typo|changelog|bump|release|version|lint|format(ting)?|ci|workflow)\b", re.I)
# Claims about these come first: a miss there loses data or money, locks people out, or crashes.
MATTERS = re.compile(r"\b(sav(e|es|ed|ing)|writ(e|es|ing)|delet\w*|remov\w*|overwrit\w*|data|loss|lost|corrupt\w*|"
                     r"migrat\w*|money|price|pric\w*|payment|billing|invoice|amount|balance|auth\w*|login|password|"
                     r"token|permission\w*|secur\w*|crash\w*|hang\w*|leak\w*|race|deadlock)\b", re.I)
SPENT = [0.0]
# A change built for another OS can't be checked here: its code path never runs, so every test passes without it.
PLATFORM_WORDS = {"win": r"windows|win32|powershell|ntfs|max_path|userprofile|\.ps1\b|cmd\.exe",
                  "mac": r"macos|mac os|darwin|apfs|osx", "linux": r"linux"}
HERE = "win" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux"
# Tidy-up commits: nothing in them is meant to change behaviour, so "nothing fails without it" isn't news.
TIDY = re.compile(r"^(chore|style|ci|refactor|build|docs?|tests?)(\([^)]*\))?!?:|^(refactor\w*|renam\w*|clean(s|ed)? ?up|docs?|"
                  r"document\w*)\b|\b(lint|mypy|pyright|tidy|tidies|sort(ed)? imports|"
                  r"reformat\w*|formatting|whitespace|typos?)\b", re.I)
# Releases: "Release 1.0.154", "Bump version to 12.2.0", "v2.3.1". They change the version number, not behaviour.
RELEASE = re.compile(r"^(?:(?:release|releasing|prepare release|bump(?:ed|s)?(?: the)? version(?: to)?|version)\s+)?v?\d+(?:\.\d+)+\s*$", re.I)
# A change for another Python version can't be checked on this one ("py3.8 fix", "for Python 3.14"); "3.12+" covers later ones.
PY_VERSION = re.compile(r"\b(?:py(?:thon)?\s?|for |drop(?:s|ped|ping)? |on )3\.(\d{1,2})\b(\+| and (?:later|newer|up))?")
# Speed-ups: tests check results, not speed, so the slower old code passing them is expected.
SPEED = re.compile(r"^perf(\([^)]*\))?!?:|\b(faster|speed(s|ing)?[ -]?up|lazy|lazily|optimi[sz]\w*|performance)\b", re.I)
# dotnet test exits 0 when its --filter matches no test: that's a test that never ran, not a claim that holds.
RAN_NOTHING = re.compile(r"No test matches the given testcase filter|No test is available in")
DOTNET_FILTER = '--filter "FullyQualifiedName~BiteClaim"'
ROAST = [False]  # --roast: the same results, worded a little more gently
# Earned when every change Bite checked had a test that noticed it; a repo can show it in its README.
BADGE = "[![Bite-proof ✅](https://img.shields.io/badge/Bite--proof-%E2%9C%85-black)](https://github.com/connabyss/bite)"


def ran_nothing(cmd: str, out: str) -> bool:
    """A run that passed without running any test (dotnet test on a project that isn't a test project, a filter
    that matched nothing) shows nothing about the code."""
    if RAN_NOTHING.search(out):
        return True
    return bool(re.search(r"\bdotnet(\.exe)?\s+test\b", cmd)) and not re.search(r"Total(?: tests)?:\s*[1-9]", out)


LFS_HEAD = b"version https://git-lfs.github.com/spec/v1"
LFS_WARNED = set()


# ---- which commits ---------------------------------------------------------------

def commits(root: Path, last: int, since: str = "") -> list:
    # With since, only commits since doesn't have: a pull request that merged its base back in would otherwise
    # list the base's newer commits first, crowding out its own.
    span = [f"{since}..HEAD"] if since else []
    raw = repo.git(root, "log", f"-n{last}", "--no-merges", "--format=%H%x1f%an%x1f%ae%x1f%s%x1f%b%x1e", *span) or ""
    out = []
    for rec in raw.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        parts += [""] * (5 - len(parts))  # git's output is stripped, so the last body can lose its separator
        if not parts[0]:
            continue
        sha, _name, _mail, subject, body = parts
        out.append({"sha": sha, "subject": subject.strip(), "body": body.strip()})
    return out


def skip_reason(subject: str, said: str) -> str:
    """Why this commit can't say anything here, or "" when it can."""
    text = said.lower()
    built_for = {os_ for os_, words in PLATFORM_WORDS.items() if re.search(rf"\b({words})", text)}
    if "case-insensitive file" in text:
        built_for |= {"win", "mac"}
    if built_for and HERE not in built_for:
        names = {"win": "Windows", "mac": "macOS", "linux": "Linux"}
        return f"built for {'/'.join(sorted(names[o] for o in built_for))}, can't be checked on {names[HERE]}"
    for_py = [(int(m.group(1)), bool(m.group(2))) for m in PY_VERSION.finditer(text)]
    here = sys.version_info[1]
    if for_py and not any(v == here or (later and here > v) for v, later in for_py):
        versions = "/".join(f"3.{v}" + ("+" if later else "") for v, later in dict.fromkeys(for_py))
        return f"built for Python {versions}, can't be checked on Python 3.{here}"
    if RELEASE.search(subject):
        return "a release, so it only changes the version number"
    if TIDY.search(subject):
        return "a tidy-up, so there's nothing new to check"
    if SPEED.search(subject) and not re.search(r"\bfix", subject, re.I):
        return "a speed-up, and tests check results, not speed"
    return ""


def tests_touch(root: Path, c: dict) -> bool:
    """The commit's own tests name the code it changed: a changed file's module or class, or a function or class
    the change defines. Tests that name none of them were written for other code."""
    names = set()
    for rel in c["code"]:
        names.add(Path(rel).stem)
        diff = repo.git(root, "diff", f"{c['sha']}^", c["sha"], "--", rel) or ""
        lines = re.findall(r"(?m)^(?:[-+](?![-+])|@@.*?@@)(.*)$", diff)  # changed lines and hunk headers
        for ln in lines:
            names |= set(re.findall(r"^\s*(?:export\s+|async\s+|pub\s+)*(?:def|class|function|func|fn|struct|interface|enum|record)\s+(\w+)", ln))
            names |= set(re.findall(r"^\s*(?:public|private|internal|protected)\b[\w<>\[\], ?]*?\s(\w+)\s*[({=;]", ln))
    names = {n for n in names if len(n) > 2 and n not in {"__init__", "index", "main", "utils", "util", "test"}}
    for t in c.get("test_code", []):
        src = repo.git(root, "show", f"{c['sha']}:{t}") or ""
        if any(re.search(rf"\b{re.escape(n)}\b", src) for n in names):
            return True
    return not names


def comment_only(root: Path, sha: str, rel: str) -> bool:
    """The change to this file is comments or whitespace only: undoing it can't make a test fail."""
    def code(rev):
        b = repo.git(root, "cat-file", "blob", f"{rev}:{rel}", raw=True)
        if b is None:
            return None
        suf = Path(rel).suffix.lower()
        lines = [bite.strip_comment(ln, suf) for ln in b.decode("utf-8", "replace").splitlines()]
        if suf == ".go":  # Go's any is interface{} under another name (Go 1.18+)
            lines = [re.sub(r"\binterface\s*\{\s*\}", "any", ln) for ln in lines]
        return [t for t in ("".join(ln.split()) for ln in lines) if t]
    old, new = code(f"{sha}^"), code(sha)
    if old is not None and old == new:
        return True
    return Path(rel).suffix.lower() == ".py" and old is not None and same_python(root, sha, rel)


# Decorators and base classes that never read type hints. Any other (dataclass, BaseModel, a web route) may, so
# hints under them count as code.
HINT_BLIND = {"staticmethod", "classmethod", "property", "setter", "getter", "deleter", "abstractmethod", "overload",
              "override", "final", "cached_property", "lru_cache", "cache", "wraps", "contextmanager", "object", "ABC"}


def last_name(node) -> str:
    node = node.func if isinstance(node, ast.Call) else node
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def drop_hints(t: ast.AST) -> None:
    """Type hints out: they don't change what runs, except where a decorator or base class reads them."""
    def walk(node, blind):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            blind = blind and all(last_name(d) in HINT_BLIND for d in node.decorator_list) and all(
                last_name(b) in HINT_BLIND for b in getattr(node, "bases", []))
        if blind and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.returns = None
            a = node.args
            for arg in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
                if arg is not None:
                    arg.annotation = None
        if isinstance(node, ast.If) and last_name(node.test) == "TYPE_CHECKING":
            node.body = [ast.Pass()]  # imports for the type checker only
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                out = []
                for v in value:
                    if blind and isinstance(v, ast.AnnAssign) and v.value is not None and isinstance(v.target, ast.Name):
                        v = ast.Assign(targets=[v.target], value=v.value)
                    if isinstance(v, ast.AST):
                        walk(v, blind)
                    out.append(v)
                setattr(node, field, out)
            elif isinstance(value, ast.AST):
                walk(value, blind)
    walk(t, True)
    # Imports from the standard library that nothing uses now were only there for the hints.
    used = {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
    for node in ast.walk(t):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            node.body = [s for s in body if not (
                isinstance(s, (ast.Import, ast.ImportFrom)) and (getattr(s, "module", None) or s.names[0].name).split(".")[0]
                in sys.stdlib_module_names | {"typing_extensions"} and not getattr(s, "level", 0)
                and not any((a.asname or a.name).split(".")[0] in used for a in s.names))] or [ast.Pass()]


def same_python(root: Path, sha: str, rel: str) -> bool:
    """The Python file does the same before and after: only docstrings, type hints or layout changed."""
    def tree(rev):
        src = repo.git(root, "cat-file", "blob", f"{rev}:{rel}", raw=True)
        try:
            t = ast.parse(src or b"")
        except (SyntaxError, ValueError):
            return None
        for node in ast.walk(t):
            body = getattr(node, "body", None)
            if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body
                    and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
        drop_hints(t)
        return ast.dump(t)
    old = tree(f"{sha}^")
    return old is not None and old == tree(sha)


def files_of(root: Path, c: dict, cfg) -> None:
    names = (repo.git(root, "diff-tree", "--no-commit-id", "-r", "--name-only", "--no-renames", c["sha"]) or "").split("\n")
    names = [n for n in names if n]
    c["tests"] = [n for n in names if bite.is_test_file(n, cfg)]
    c["code"] = [n for n in names if n not in c["tests"] and Path(n).suffix.lower() in repo.CODE_SUFFIXES
                 and not repo.is_setup(n, cfg) and not comment_only(root, c["sha"], n)]
    # Code in a language the test command doesn't run can't fail a test: taking it out says nothing about it.
    runs = repo.runs_language(cfg.test_cmd)[1]
    c["other_lang"] = [n for n in c["code"] if runs and Path(n).suffix.lower() not in runs]
    c["code"] = [n for n in c["code"] if n not in c["other_lang"]]
    stat = repo.git(root, "diff", "--shortstat", f"{c['sha']}^", c["sha"], "--", *c["code"]) if c["code"] else ""
    c["lines"] = sum(int(x) for x in re.findall(r"(\d+) (?:insertion|deletion)", stat or ""))
    claims = bool(CLAIM.search(c["subject"])) and not NOT_CODE.search(c["subject"])
    c["claims"] = claims
    # Trailers out first: "Co-Authored-By" would match auth in every co-authored commit.
    said = c["subject"] + " " + re.sub(r"(?im)^[\w-]+-by:.*$", "", c["body"])[:400]
    c["serious"] = claims and bool(MATTERS.search(said))
    c["skip"] = skip_reason(c["subject"], said)
    c["test_code"] = [n for n in c["tests"] if Path(n).suffix.lower() in repo.CODE_SUFFIXES]
    # No test is suspect, and so is a new test (it may check nothing the change did): the free pass tells which.
    c["score"] = ((3 if claims else 0) + (2 if not c["tests"] or c["test_code"] else 0) + (1 if 0 < c["lines"] <= 80 else 0)
                  + (2 if MATTERS.search(said) else 0))


def export(root: Path, sha: str, cfg) -> Path:
    """The project as it was at this commit, in a fresh folder (git archive, so nothing of yours is touched)."""
    dest = Path(tempfile.mkdtemp(prefix="bite_recent_")) / root.name
    dest.mkdir()
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=root, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=data, capture_output=True)
    lfs_fill(root, dest, data)
    for name in cfg.copy_ignore:  # nothing to do for most repos: ignored files aren't committed
        for p in dest.rglob(name):
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else None
    return dest


def lfs_fill(root: Path, dest: Path, tar: bytes) -> int:
    """git archive writes Git LFS files as small pointer files. Put the real content back, from the repo's own LFS
    store or with git-lfs; warn once about any left as pointers, since a test that reads them fails on the copy.
    Returns how many are still pointers."""
    pointers = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t:
            if m.isfile() and m.size < 1024:
                head = t.extractfile(m).read()
                if head.startswith(LFS_HEAD):
                    pointers.append((m.name, head))
    if not pointers:
        return 0
    store = Path(repo.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir") or root / ".git") / "lfs" / "objects"
    left, smudge = [], True
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for name, ptr in pointers:
        oid = re.search(rb"oid sha256:([0-9a-f]{64})", ptr)
        obj = store / oid.group(1)[:2].decode() / oid.group(1)[2:4].decode() / oid.group(1).decode() if oid else None
        if obj and obj.is_file():
            bite.safe_write(dest, dest / name, obj.read_bytes())
            continue
        real = b""
        try:  # not downloaded here yet: git-lfs can fetch it, if it's installed (after one failure, stop trying)
            r = subprocess.run(["git", "lfs", "smudge", "--", name], cwd=root, input=ptr, capture_output=True,
                               timeout=120, env=env) if smudge else None
            real = r.stdout if r and r.returncode == 0 else b""
        except (OSError, subprocess.TimeoutExpired):
            pass
        smudge = smudge and bool(real)
        if real and not real.startswith(LFS_HEAD):
            bite.safe_write(dest, dest / name, real)
        else:
            left.append(name)
    if left and str(root) not in LFS_WARNED:
        LFS_WARNED.add(str(root))
        print(f"  note: {len(left)} Git LFS file(s) are only pointer files in Bite's copies (e.g. {left[0]}): install "
              "git-lfs and run `git lfs pull` so tests that read them work there.")
    return len(left)


def at(cfg, folder: Path):
    import copy as _copy
    c = _copy.copy(cfg)
    c.project = folder.resolve()
    return c


# ---- step 1: free ----------------------------------------------------------------

def preflight(cfg) -> str:
    """Why the tests can't run here at all, in words that name the fix, or "" when nothing is plainly missing.
    Checked once before any copy is made, so a missing runner isn't reported as "exit 1" on every commit."""
    if cfg.contain:  # the tests run in the box, which brings its own programs
        return ""
    for cmd in dict.fromkeys(c for c in (cfg.free_cmd, cfg.test_cmd) if c):
        if re.search(r"&&|\|\||[|;]|\{", cmd):
            continue  # a shell line: its first word may not be a program
        try:
            words = shlex.split(cmd, posix=not bite.WINDOWS)
        except ValueError:
            continue
        first = words[0].strip('"') if words else ""
        if not first or first.lower() in {"cd", "set", "env", "call", "start"}:
            continue
        if not shutil.which(first):
            return (f"Bite can't find {first!r}, the first word of the test command ({cmd}). "
                    "Install it, or set test_command in .bite.ini to the command that runs your tests.")
        if words[1:3] == ["-m", "pytest"] and subprocess.run([first, "-c", "import pytest"],
                                                           capture_output=True).returncode != 0:
            return (f"pytest isn't installed for this Python ({shutil.which(first)}), so your tests can't run. "
                    f"Install it, then run Bite again:\n    {first} -m pip install pytest")
    return ""


def take_out(root: Path, c: dict, folder: Path) -> None:
    """Put this commit's code files in the copy back the way they were before it (its tests stay)."""
    before = c.get("before") or f"{c['sha']}^"  # the live check passes the commit the turn started from
    for rel in c["code"]:
        old = repo.git(root, "cat-file", "blob", f"{before}:{rel}", raw=True)
        t = folder / rel
        if old is None and t.suffix == ".py" and t.name != "__init__.py":
            # A file the commit created: deleting it would let Python find an installed copy (pip install -e .)
            # and import that instead, so the tests pass. A file that refuses to load stands in for it.
            bite.safe_write(folder, t, b'raise ImportError("Bite took this file out: the commit it checks made it")\n')
        elif old is None:
            t.unlink(missing_ok=True)
        else:
            bite.safe_write(folder, t, old)


def undo_check(root: Path, c: dict, cfg) -> str:
    """'unguarded' when the tests still pass with this commit's code change taken back out; 'TEST GUARDS NOTHING'
    when that includes the tests the commit itself added or changed (they're kept: only the code is undone)."""
    folder = export(root, c["sha"], cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):  # the faster subset, for this step only
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        now = bite.run_tests(fcfg, folder)
        if not now["ok"]:
            errs = [ln.strip(" E>") for ln in now["out"].splitlines() if re.search(r"\b\w+(?:Error|Exception)\b:|No module named ", ln)]
            c["why"] = (errs[-1] if errs else now["why"])[:160]
            return "tests fail at this commit"
        if ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return "no tests ran at this commit"
        take_out(root, c, folder)
        undone = bite.run_tests(fcfg, folder)
        if undone["ok"]:  # would be flagged: first rule out the usual harmless reasons
            if c.get("skip"):
                return f"not flagged: {c['skip']}"
            if c.get("test_code") and not tests_touch(root, c):
                return "not flagged: its tests are about other code"
            if closed_since(root, c, cfg):
                return "closed since: today's tests catch it"
            return "TEST GUARDS NOTHING" if c.get("test_code") else "unguarded"
        c["caught"] = caught_by(undone["out"])
        return "guarded" if not bite.load_failure(undone["out"]) else "guarded (tests use the new code)"
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


# The names of failing tests, as pytest, unittest, go test, cargo test, jest and dotnet test print them.
FAILED_TEST = re.compile(r"^(?:FAILED|ERROR) \S+::(?:\S+::)*([\w\[\]-]+)|^(?:FAIL|ERROR): (\w+) \(|--- FAIL: (\S+)|"
                         r"^test (\S+) \.\.\. FAILED|✕ (.+?)(?: \(\d+ ?ms\))?$|^\s*Failed (\S+) \[", re.M)


def caught_by(out: str) -> str:
    """The test(s) that failed, for the report: "`test_x`", "`test_x` and 2 more", or "" when none is named."""
    names = list(dict.fromkeys(next(g for g in m.groups() if g).strip() for m in FAILED_TEST.finditer(out)))
    if not names:
        return ""
    return f"`{names[0]}`" + (f" and {len(names) - 1} more" if len(names) > 1 else "")


def closed_since(root: Path, c: dict, cfg) -> bool:
    """A later commit may have closed the gap: on today's code, take this commit's change back out (if it still
    applies) and see whether today's tests now fail where they passed before."""
    head = repo.git(root, "rev-parse", "HEAD")
    if not head or head == c["sha"]:
        return False
    diff = repo.git(root, "diff", "--binary", f"{c['sha']}^", c["sha"], "--", *c["code"], raw=True)
    folder = export(root, head, cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        if not diff or subprocess.run(["git", "apply", "-R", "--check", "-"], cwd=folder, input=diff,
                                      capture_output=True).returncode != 0:
            return False  # today's code moved on: can't tell
        now = bite.run_tests(fcfg, folder)
        if not now["ok"] or ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return False
        subprocess.run(["git", "apply", "-R", "-"], cwd=folder, input=diff, capture_output=True)
        undone = bite.run_tests(fcfg, folder)
        c["caught"] = caught_by(undone["out"])
        return not undone["ok"] and not bite.load_failure(undone["out"])
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


# ---- step 2: the claim, turned into a test ----------------------------------------

WORKER_SYSTEM = """You check one claim a coding agent made in a commit message. You are on a copy of the project
exactly as it was at that commit. Your job: write ONE small test that checks what the commit message says is now
true, and run it.

Rules:
- Test only what the message (and the diff's evident intent) claims. Don't test other features or ask for more.
- Be a skeptic, not a fan: the commit's own tests already cover the happy path. Look for where the claim is
  WIDER than the change: the message says "handles X" but the diff covers one form of X; it says "every" or
  "always" but one branch, caller, file format or platform path was missed; a sibling function with the same
  bug was left alone; the fix works once but not on the second call, a reload, or a round trip. Test those.
- Include the odd inputs the claim plainly covers: empty, None, zero, unicode, duplicates, boundaries.
  Small and readable, under 40 lines.
- Use the project's own test framework and conventions. Put the test in ONE new file whose name contains
  bite_claim and that the project's test runner picks up (for pytest: test_bite_claim.py), next to the
  project's other tests. Don't edit any other file. For .NET (dotnet test): BiteClaimTests.cs with a test
  class named BiteClaimTests, inside the folder of an existing test project so that project compiles it.
- Run it: `pytest <your file>` runs only your test if pytest is the runner; for .NET,
  `dotnet test <the test project> --filter "FullyQualifiedName~BiteClaim"`; `bite-test` runs the whole suite. If it fails, read the failure and make sure the TEST is right (right import, right API, right
  expectation from the claim) before you conclude the code is wrong. A failure from your own mistake is not a finding.
- Finish with one line of JSON and nothing after it:
  {"test_file": "<path relative to the project>", "claim": "<the claim in your words>", "result": "fails" or "holds", "why": "<one sentence>"}"""

JUDGE_PROMPT = """A commit said:
---
{msg}
---
Its diff (code files):
---
{diff}
---
A checker wrote this test of that claim:
---
{test}
---
Run on the code at that commit, the test fails like this:
---
{fail}
---
Answer strictly. Is this a fair test of what the commit claimed (it doesn't ask for more than the claim or the
change's evident intent), and does it fail because the code really doesn't do what was claimed (not because the
test is wrong, uses a wrong API, or expects behaviour nobody promised)?
Then, if REAL, how much it matters: +1 each for: real users would hit it; it loses or corrupts data or money;
it would be embarrassing if a user found it.
Reply with one line of JSON only: {{"verdict": "REAL" or "NOT", "matters": 0-3, "bug": "<the false claim in one plain sentence>",
"why": "<one sentence>"}}"""


def last_json(text: str) -> dict:
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", text or ""))):
        try:
            return json.loads(m.group(0))
        except ValueError:
            continue
    return {}


async def _agent(options, prompt: str):
    from claude_agent_sdk import AssistantMessage, ClaudeSDKClient, ResultMessage, TextBlock
    said, cost = [], 0.0
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                t = [b.text for b in msg.content if isinstance(b, TextBlock) and b.text.strip()]
                if t:
                    said = t
            elif isinstance(msg, ResultMessage):
                cost = msg.total_cost_usd or 0.0
    SPENT[0] += cost
    return "\n".join(said), cost


def worker(cfg, folder: Path, c: dict, diff: str, budget: float) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions
    wcfg = at(cfg, folder)
    opts = ClaudeAgentOptions(cwd=str(folder), model=cfg.model, system_prompt=WORKER_SYSTEM, max_turns=cfg.max_turns,
                              max_budget_usd=budget, allowed_tools=[], disallowed_tools=["WebFetch", "WebSearch", "Task"],
                              can_use_tool=bite.make_permission(wcfg, log=lambda *a: None), permission_mode="default",
                              setting_sources=[], env={"ANTHROPIC_API_KEY": bite.load_key()})
    prompt = f"Commit message:\n{c['subject']}\n\n{c['body']}\n\nThe code change in it:\n{diff}"
    text, _ = asyncio.run(_agent(opts, prompt))
    return last_json(text)


def judge(cfg, c: dict, diff: str, test: str, fail: str) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions

    async def nothing(*a):
        from claude_agent_sdk import PermissionResultDeny
        return PermissionResultDeny(message="No tools: answer from what you were given.")
    opts = ClaudeAgentOptions(model=cfg.judge_model, max_turns=2, max_budget_usd=cfg.judge_budget, allowed_tools=[],
                              can_use_tool=nothing, permission_mode="default", setting_sources=[],
                              env={"ANTHROPIC_API_KEY": bite.load_key()},
                              system_prompt="You check another checker's work. Default to NOT when unsure.")
    msg = f"{c['subject']}\n\n{c['body']}"[:3000]
    text, _ = asyncio.run(_agent(opts, JUDGE_PROMPT.format(msg=msg, diff=diff[:8000], test=test[:4000], fail=fail[:3000])))
    return last_json(text)


def claim_command(cfg, rel: str) -> str:
    """Bite runs the claim test with the project's own test command (never the worker's command line)."""
    if cfg.claim_cmd:
        return cfg.claim_cmd.replace("{file}", rel)
    cmd = bite.tests_cmd(cfg)
    if re.search(r"\bdotnet(\.exe)?\s+test\b", cmd):  # dotnet test takes no file: pick the claim's class by name
        cmd = re.sub(r'\s--filter(\s+|=)("[^"]*"|\S+)', "", cmd)
        return f"{cmd} {DOTNET_FILTER}"
    if re.search(r"\bgo\s+test\b", cmd):  # go test takes packages, not a file next to ./...: run the file's package
        toks = [t for t in cmd.split() if not (t in (".", "./...") or t.startswith("./") or t.endswith("/..."))]
        return " ".join(toks) + " ./" + (posixpath.dirname(rel) or ".")
    if "pytest" in cmd:  # keep the runner and its options, drop the folders it was given: only this file runs
        toks = cmd.split()
        i = next(i for i, t in enumerate(toks) if "pytest" in t)
        keep = toks[:i + 1] + [t for t in toks[i + 1:] if t.startswith("-")]
        for opt in ("-p", "-c", "-k", "-m", "--rootdir"):  # options that take a value
            keep += [toks[j + 1] for j in range(i + 1, len(toks) - 1) if toks[j] == opt and toks[j + 1] not in keep]
        return " ".join(keep) + " " + rel
    return f"{cmd} {rel}"


def run_claim(cfg, folder: Path, test_rel: str, test_src: bytes, cmd: str) -> tuple:
    """(exit code, output) of the claim test placed into this copy, run by Bite itself."""
    t = folder / test_rel
    t.parent.mkdir(parents=True, exist_ok=True)
    bite.safe_write(folder, t, test_src)
    return bite.locked_run(at(cfg, folder), cmd, folder)


def written_test(folder: Path, w: dict):
    """The one test file the worker says it wrote, if it is inside the copy and named like Bite's tests; else None."""
    rel = (w.get("test_file") or "").strip().replace("\\", "/")
    tf = bite.inside(folder, str(folder / rel)) if rel else None
    if not tf or not tf.is_file() or "biteclaim" not in re.sub(r"[_\-\s]", "", tf.name.lower()):
        return None
    return tf


def try_claim(root: Path, c: dict, cfg, budget: float) -> dict:
    res = {"sha": c["sha"], "subject": c["subject"], "status": "holds"}
    diff = repo.git(root, "diff", f"{c['sha']}^", c["sha"], "--", *c["code"]) or ""
    folder = export(root, c["sha"], cfg)
    try:
        w = worker(cfg, folder, c, diff[:12000], budget)
        res["worker"] = w
        tf = written_test(folder, w)
        if not tf:
            res["status"] = "no test written"
            return res
        rel = tf.relative_to(folder.resolve()).as_posix()
        cmd = claim_command(cfg, rel)
        src = tf.read_bytes()
        res.update(test_file=rel, run=cmd, test=src.decode("utf-8", "replace"))
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)

    # Bite runs it itself, on clean copies: twice at the commit, then on today's code.
    outs = []
    for _ in range(2):
        f = export(root, c["sha"], cfg)
        try:
            outs.append(run_claim(cfg, f, rel, src, cmd))
        finally:
            shutil.rmtree(f.parent, ignore_errors=True)
    if any(rc in cfg.ok_codes and ran_nothing(cmd, out) for rc, out in outs):
        res["status"] = "test didn't load or timed out"
        return res
    if any(rc in cfg.ok_codes for rc, _ in outs):
        res["status"] = "holds" if all(rc in cfg.ok_codes for rc, _ in outs) else "flaky"
        return res
    if any(rc is None for rc, _ in outs) or bite.load_failure(outs[0][1]):
        res["status"] = "test didn't load or timed out"
        return res
    fail = repo.failure_excerpt(outs[0][1], 25)
    res["fail"] = fail
    v = judge(cfg, c, diff, res["test"], fail)
    res["judge"] = v
    if (v.get("verdict") or "").upper() != "REAL":
        res["status"] = "second check disagreed"
        return res
    head = repo.git(root, "rev-parse", "HEAD")
    f = export(root, head, cfg)
    try:
        rc, out = run_claim(cfg, f, rel, src, cmd)
    finally:
        shutil.rmtree(f.parent, ignore_errors=True)
    res["today"] = ("fixed since" if rc in cfg.ok_codes else "can't tell (test doesn't load on today's code)"
                    if rc is None or bite.load_failure(out) else "STILL BROKEN")
    res["status"] = "FALSE DONE"
    res["matters"] = int(v.get("matters") or 0)
    res["bug"] = v.get("bug") or w.get("why", "")
    return res


# ---- --write-tests: the missing test, for a change no test noticed -------------------

GUARD_SYSTEM = """You write the test a project is missing. You are on a copy of the project exactly as it was at
one commit. The commit changed some code, and when that change is taken back out, every test still passes: no
test notices what the change does. Write ONE small test that does.

Rules:
- The test must pass on this copy, with the change in. With the change taken out (the code files put back as they
  were before the commit), it must fail. Bite checks both itself.
- Test what the change does for a user of the code, through the code's normal way in, not its private details.
  Test only what this change does. Don't test other features or ask for more.
- Small and readable, under 30 lines, in the project's own test framework and style, so the owner can paste it in
  as it is. One short comment at the top saying what it guards.
- Put it in ONE new file whose name contains bite_claim and that the project's test runner picks up (for pytest:
  test_bite_claim.py), next to the project's other tests. Don't edit any other file. For .NET (dotnet test):
  BiteClaimTests.cs with a test class named BiteClaimTests, inside the folder of an existing test project.
- Run it: `pytest <your file>` runs only your test if pytest is the runner; for .NET,
  `dotnet test <the test project> --filter "FullyQualifiedName~BiteClaim"`; `bite-test` runs the whole suite.
  Make sure it passes here.
- Finish with one line of JSON and nothing after it:
  {"test_file": "<path relative to the project>", "guards": "<the words that finish 'It checks that ...'>"}"""


GUARD_JUDGE_PROMPT = """A commit made this change to the code:
---
{msg}
---
Its diff (code files):
---
{diff}
---
No test noticed when the change was taken out. A checker wrote this test of it:
---
{test}
---
It passes with the change in. With the change taken out, it fails like this:
---
{fail}
---
Answer strictly. Is this a fair test of what the change does (it tests only this change, through the code's
normal way in, and asks for nothing the change and its message don't evidently mean), and does it fail because
the change's behaviour is gone (not because of a wrong API, a typo, or a detail nobody relies on)?
Reply with one line of JSON only: {{"verdict": "FAIR" or "NOT", "why": "<one sentence>"}}"""


def guard_judge(cfg, c: dict, diff: str, test: str, fail: str) -> dict:
    """The second check on a test --write-tests wrote, the same bar as a claim test's: a fresh model with no tools."""
    from claude_agent_sdk import ClaudeAgentOptions

    async def nothing(*a):
        from claude_agent_sdk import PermissionResultDeny
        return PermissionResultDeny(message="No tools: answer from what you were given.")
    opts = ClaudeAgentOptions(model=cfg.judge_model, max_turns=2, max_budget_usd=cfg.judge_budget, allowed_tools=[],
                              can_use_tool=nothing, permission_mode="default", setting_sources=[],
                              env={"ANTHROPIC_API_KEY": bite.load_key()},
                              system_prompt="You check another checker's work. Default to NOT when unsure.")
    msg = f"{c['subject']}\n\n{c['body']}"[:3000]
    text, _ = asyncio.run(_agent(opts, GUARD_JUDGE_PROMPT.format(msg=msg, diff=diff[:8000], test=test[:4000], fail=fail[:3000])))
    return last_json(text)


def guard_worker(cfg, folder: Path, c: dict, diff: str, budget: float) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions
    opts = ClaudeAgentOptions(cwd=str(folder), model=cfg.model, system_prompt=GUARD_SYSTEM, max_turns=cfg.max_turns,
                              max_budget_usd=budget, allowed_tools=[], disallowed_tools=["WebFetch", "WebSearch", "Task"],
                              can_use_tool=bite.make_permission(at(cfg, folder), log=lambda *a: None), permission_mode="default",
                              setting_sources=[], env={"ANTHROPIC_API_KEY": bite.load_key()})
    prompt = f"Commit message:\n{c['subject']}\n\n{c['body']}\n\nThe code change in it:\n{diff}"
    text, _ = asyncio.run(_agent(opts, prompt))
    return last_json(text)


def try_guard(root: Path, c: dict, cfg, budget: float) -> dict:
    """A worker writes the missing test; Bite keeps it only if it passes twice with the change in, fails with the
    change taken out (a real failure, not a test that can't load), and a second fresh check calls it fair."""
    res = {"sha": c["sha"], "status": "no test written"}
    diff = repo.git(root, "diff", f"{c['sha']}^", c["sha"], "--", *c["code"]) or ""
    folder = export(root, c["sha"], cfg)
    try:
        w = guard_worker(cfg, folder, c, diff[:12000], budget)
        tf = written_test(folder, w)
        if not tf:
            return res
        rel = tf.relative_to(folder.resolve()).as_posix()
        src = tf.read_bytes()
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)
    cmd = claim_command(cfg, rel)
    res.update(test_file=rel, run=cmd, test=src.decode("utf-8", "replace"), guards=w.get("guards", ""))
    for _ in range(2):
        f = export(root, c["sha"], cfg)
        try:
            rc, out = run_claim(cfg, f, rel, src, cmd)
        finally:
            shutil.rmtree(f.parent, ignore_errors=True)
        if rc not in cfg.ok_codes or ran_nothing(cmd, out):
            res["status"] = "its test failed with the change in"
            return res
    f = export(root, c["sha"], cfg)
    try:
        take_out(root, c, f)
        rc, out = run_claim(cfg, f, rel, src, cmd)
    finally:
        shutil.rmtree(f.parent, ignore_errors=True)
    if rc in cfg.ok_codes:
        res["status"] = "its test passed without the change too"
    elif rc is None or bite.load_failure(out):
        res["status"] = "its test couldn't load without the change"
    else:
        fail = repo.failure_excerpt(out, 15)
        v = guard_judge(cfg, c, diff, res["test"], fail)
        res["judge"] = v
        if (v.get("verdict") or "").upper() == "FAIR":
            res.update(status="WRITTEN", fail=fail)
        else:
            res["status"] = "a second check didn't call its test fair" + (f" ({v['why'].rstrip('.')})" if v.get("why") else "")
    return res


# ---- report ----------------------------------------------------------------------

def proof_dir(root: Path) -> Path:
    """bite_proof/ in the repo, kept out of git: it's Bite's output, not the project's."""
    d = root / "bite_proof"
    d.mkdir(exist_ok=True)
    ign = d / ".gitignore"
    if not ign.exists():
        ign.write_text("# Bite's output: not part of the project. Delete this file to commit the proof.\n*\n", encoding="utf-8")
    return d


def save_log(root: Path, tried: list, cs: list) -> None:
    """Written after every check, so a run stopped partway keeps what it found."""
    (proof_dir(root) / "recent_log.json").write_text(json.dumps({"tried": tried, "free": [
        {k: c.get(k) for k in ("sha", "subject", "undo", "score")} for c in cs]}, indent=1), encoding="utf-8")


SETUP_LINK = "https://github.com/connabyss/bite/blob/main/AGENTS.md#setup-once-your-person-says-yes-they-only-paste-a-key-and-only-for-the-paid-step"


def say(c: dict, newest: str = "") -> tuple[str, str, str]:
    """One free-check result in plain words, the same in the terminal, the report, the job page and the pull request
    comment: (kind, short label, one or two sentences). Each answers one question: if this change disappeared, would
    any test notice? kind is held, gap, odd, fail, none or skip. newest is the pull request's newest commit: tests
    failing on an older commit are skipped, since they often get fixed later."""
    u, caught = c.get("undo", ""), c.get("caught", "")
    one = caught and " more" not in caught
    if u.startswith("closed since"):
        return "held", "✅ a later test notices", f"✅ A test added in a later commit notices it now{f' ({caught})' if caught else ''}."
    if u == "guarded (tests use the new code)":
        return "held", "✅ tests crash without it", "✅ Without this change your tests crash, so they'd notice if it went."
    if u.startswith("guarded"):
        return ("held", f"✅ noticed by {caught.replace('`', '') or 'your tests'}",
                f"✅ {(('The test ' if one else 'The tests ') + caught) if caught else 'Your tests'} noticed it was gone. "
                f"If this change breaks later, "
                f"{'that test' if one else 'they'} will warn you.")
    if u.startswith("unguarded"):
        return ("gap", "⚠️ NO TEST NOTICED", "⚠️ " + ("If this fix wandered off, nothing would notice. A test would. " if ROAST[0] else
                "No test noticed it was gone. If it breaks later, nothing warns you. ")
                + "**Next:** add a test that fails without it.")
    if u == "TEST GUARDS NOTHING":
        mine = ", ".join(f"`{t}`" for t in c.get("test_code", []))
        return ("odd", "⚠️ ITS TESTS DIDN'T NOTICE", f"⚠️ {'These' if ROAST[0] else 'This commit added'} tests"
                f"{f' ({mine})' if mine else ''}" + (" are looking the other way. " if ROAST[0] else
                ", but they didn't notice it was gone either, so they check something else. ")
                + "**Next:** make one fail without the change.")
    if u == "tests fail at this commit":
        if newest and c["sha"] != newest:
            return ("skip", "➖ tests failed here, skipped", "➖ Your tests failed at this commit, so Bite skipped it "
                    "(a later commit may have fixed them).")
        return ("fail", "❌ tests already fail", "❌ Your tests already fail here, so Bite can't ask its question. "
                f"**Next:** fix them first. If they pass on your own computer, [tell Bite how to run them]({SETUP_LINK}).")
    if u == "no tests ran at this commit":
        return ("none", "⚠️ no tests found", "⚠️ Bite couldn't find any tests to run. **Next:** add one, or "
                f"[point Bite at your tests]({SETUP_LINK}).")
    if u.startswith("not flagged: "):
        return "skip", "➖ skipped: " + u[len("not flagged: "):], "➖ Skipped: " + u[len("not flagged: "):] + "."
    return "skip", "➖ couldn't check: " + u, "➖ Couldn't check: " + u + "."


def bite_proof(kinds: list, tried: list = ()) -> bool:
    """Every change Bite checked had a test that noticed it (skipped ones aside), and no claim tested was false."""
    return "held" in kinds and set(kinds) <= {"held", "skip"} and not any(r.get("status") == "FALSE DONE" for r in tried)


def flat(text: str) -> str:
    """say()'s sentence without its Markdown, for the terminal and the report page."""
    return re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text).replace("**", "").replace("`", "")


def short(title: str, n: int = 70) -> str:
    """A commit title cut to fit a terminal line: at a space, with "…", never mid-word."""
    if len(title) <= n:
        return title
    cut = title[:n - 1].rsplit(" ", 1)[0] if " " in title[:n - 1] else title[:n - 1]
    return cut.rstrip(" ,.:;-") + "…"


def commit_link(root: Path) -> str:
    """https://github.com/owner/name/commit/ for a GitHub origin, else "" (the report then shows plain shas)."""
    url = repo.git(root, "remote", "get-url", "origin") or ""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return f"https://github.com/{m.group(1)}/commit/" if m else ""


def write_html(root: Path, cs: list, tried: list, seconds: float) -> Path:
    """One page that says what was checked and how each commit did, to open in a browser or screenshot."""
    import html
    from datetime import datetime
    e = html.escape
    link = commit_link(root)
    checked = [c for c in cs if c.get("undo")]
    kinds = [say(c)[0] for c in checked]
    false_done = [r for r in tried if r.get("status") == "FALSE DONE"]
    sha = lambda x: (f'<a href="{e(link + x)}">{x[:8]}</a>' if link else x[:8])  # noqa: E731
    rows = "".join(f'<tr class="{k}"><td><code>{sha(c["sha"])}</code></td><td>{e(c["subject"])}</td>'
                   f'<td><span class="dot"></span>{e(flat(w)[2:].strip())}' + (f'<div class="why">{e(c["why"])}</div>' if c.get("why") else "")
                   + "</td></tr>" for c in checked for k, _, w in [say(c)])
    claims = "".join(f'<tr class="{"odd" if r["status"] == "FALSE DONE" else "held" if r["status"] == "holds" else "skip"}">'
                     f'<td><code>{sha(r["sha"])}</code></td><td>{e(r["subject"])}</td><td><span class="dot"></span>'
                     + (f'False "done": {e(r.get("bug", ""))} Today\'s code: {e(r.get("today", ""))}.'
                        if r["status"] == "FALSE DONE" else "The claim held" if r["status"] == "holds" else e(r["status"]))
                     + "</td></tr>" for r in tried)
    tiles = [(len(checked), "commits checked", ""), (kinds.count("held"), "a test noticed", "held"),
             (kinds.count("gap") + kinds.count("odd") + kinds.count("none"), "no test noticed", "gap"),
             (kinds.count("skip") + kinds.count("fail"), "couldn't check", "skip")]
    if tried:
        tiles.append((len(false_done), f"false \"done\" of {len(tried)} claims tested", "odd"))
    page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bite report: {e(root.name)}</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#6b6a65;--line:#e4e1d8;--held:#2e7d4f;--gap:#b7791f;--odd:#c0392b;--skip:#8a8a85}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ecebe6;--mute:#9a9992;--line:#2c2b29;--held:#5fbf86;--gap:#e0a84a;--odd:#ef6b5b;--skip:#7d7c77}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:920px;margin:0 auto;padding:32px 16px}} h1{{margin:0;font-size:28px}} h2{{font-size:18px;margin:32px 0 8px}}
.sub{{color:var(--mute)}} a{{color:inherit}} code{{font:13px ui-monospace,Consolas,monospace}}
.tiles{{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}} .tile{{flex:1 1 140px;border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.tile b{{display:block;font-size:30px;line-height:1.1}} .tile.held b{{color:var(--held)}} .tile.gap b{{color:var(--gap)}}
.tile.odd b{{color:var(--odd)}} .tile.skip b{{color:var(--skip)}}
table{{width:100%;border-collapse:collapse}} td{{padding:8px 6px;border-top:1px solid var(--line);vertical-align:top}}
td:first-child{{white-space:nowrap}} .dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;background:var(--skip)}}
.held .dot{{background:var(--held)}} .gap .dot,.none .dot{{background:var(--gap)}} .odd .dot,.fail .dot{{background:var(--odd)}}
.why{{color:var(--mute);font-size:13px}} .proof{{border:1px solid var(--held);border-radius:10px;padding:12px 14px}}
.proof b{{color:var(--held)}} footer{{margin-top:32px;color:var(--mute);font-size:13px}}
</style>
<main>
<h1><img src="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-avatar.png" width="32" height="32" alt="Bite" style="vertical-align: middle; margin-right: 8px;"> Bite report: {e(root.name)}</h1>
<div class="sub">{datetime.now():%Y-%m-%d %H:%M} &middot; did the recent "fixed" commits hold? &middot; {seconds:.0f}s, ${SPENT[0]:.2f}</div>
{f'<p class="proof"><b>Bite-proof. Nice work.</b> Every change Bite checked had a test that noticed it. Badge for your README:<br><code>{e(BADGE)}</code></p>' if bite_proof(kinds, tried) else ""}
<div class="tiles">{"".join(f'<div class="tile {k}"><b>{n}</b>{e(t)}</div>' for n, t, k in tiles)}</div>
{f'<h2>Claims tested</h2><table>{claims}</table>' if tried else ""}
<h2>If this change disappeared, would any test notice?</h2>
{f'<table>{rows}</table>' if rows else '<p class="sub">No commits were checked.</p>'}
<footer>"Held" means a test fails when the change is taken out. It doesn't prove the commit has no other bugs.
Details and rerun commands are in the other files in this folder. Made by <a href="https://github.com/connabyss/bite">Bite</a>.</footer>
</main>
"""
    out = proof_dir(root) / "report.html"
    out.write_text(page, encoding="utf-8")
    return out


# The cat logo at the start of every comment's heading, so Bite's comments look like Bite's. Hosted on main, not in
# the comment, because GitHub won't show images written into a comment.
CAT = ('<img src="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-avatar.png" '
       'width="24" height="24" alt="Bite" align="top">')


# The code fence's language for a written test, so GitHub colours it.
FENCE_LANG = {".py": "python", ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "ts", ".tsx": "tsx", ".jsx": "jsx",
              ".rs": "rust", ".go": "go", ".cs": "csharp"}


def write_comment(root: Path, cs: list, none: str = "", error: str = "", newest: str = "") -> Path:
    """The free check in plain words for a pull request comment (the GitHub Action posts it): a verdict, what to
    do next, then one line per commit. none says why nothing was checked, error why Bite couldn't start, and newest
    is the pull request's newest commit: only its failing tests decide the verdict."""
    import html
    link = commit_link(root)
    checked = [c for c in cs if c.get("undo")]
    said = [say(c, newest) for c in checked]
    kinds = [k for k, _, _ in said]
    bad = [c for c, k in zip(checked, kinds) if k in ("gap", "odd")]
    wrote = [c for c in bad if (c.get("guard") or {}).get("status") == "WRITTEN"]
    sha = lambda c: f"[`{c['sha'][:8]}`]({link}{c['sha']})" if link else f"`{c['sha'][:8]}`"  # noqa: E731
    why = lambda c: f" Why: {html.escape(c['why'], quote=False).replace('`', chr(39))}." if c.get("why") else ""  # noqa: E731
    # The verdict first; the commit's own title after it, quoted and small, so it doesn't read as Bite talking.
    line = lambda c, k, w: (f"- {w}" + (why(c) if k == "fail" or "tests failed here" in w else "")  # noqa: E731
                            + f"<br><sub>Commit {sha(c)}: “{html.escape(c['subject'], quote=False)}”</sub>")
    lines = ["<!-- bite-check -->"]
    if error:
        lines += ["### ❌ Bite couldn't start", "", html.escape(error, quote=False), "",
                  "**Next:** fix that and push again. Bite checks again on every push."]
    elif "fail" in kinds:
        lines += ["### ❌ Bite: your tests already fail", "",
                  "Bite can't ask its question while your tests fail on the newest commit.", "",
                  "**Next:** fix them first. Bite checks again on your next push. If they pass on your own computer, "
                  f"Bite may be running them the wrong way: [tell Bite how to run them]({SETUP_LINK})."]
    elif bad:
        one = len(bad) == 1
        lines += [f"### ⚠️ Bite: no test noticed {len(bad)} change{'' if one else 's'}", "",
                  f"Bite took {'the ⚠️ change' if one else 'each ⚠️ change'} below out and every test still passed. If "
                  f"{'it' if one else 'they'} broke later, nothing would warn you. That's fine for a tidy-up, a rename or docs.", "",
                  ("**Next:** if the change should do something, add a test that fails without it." if not wrote else
                   "**Next:** paste in the test Bite wrote below (🧪): it passes with the change and fails without it."
                   if len(wrote) == len(bad) else
                   f"**Next:** paste in the test{'s' if len(wrote) > 1 else ''} Bite wrote below (🧪) for {len(wrote)} of "
                   "them. For the rest, if the change should do something, add a test that fails without it.")]
    elif "none" in kinds and "held" not in kinds:
        lines += ["### ⚠️ Bite: no tests found", "", "Bite couldn't find any tests to run, so nothing would notice if this code broke.", "",
                  f"**Next:** add a test, or [point Bite at your tests]({SETUP_LINK})."]
    elif "held" in kinds:
        lines += ["### ✅ Bite-proof. Nice work." if bite_proof(kinds) else "### ✅ Bite: a test noticed every change", "",
                  "Bite took each change out, one at a time, and a test noticed every time. If one breaks later, that "
                  "test will warn you."]
        if bite_proof(kinds):
            lines += ["", f"Badge for your README: `{BADGE}`"]
    elif checked:
        lines += ["### ➖ Bite: nothing here to check", "", "Bite skipped every commit here. Each one says why."]
    else:
        lines += ["### ➖ Bite: nothing here to check", "",
                  none or "No commit in this pull request changed code: only docs, settings or tests."]
    if checked:
        lines += [""] + [line(c, k, re.sub(r"\*\*Next:\*\* .*$", "**Next:** paste in the test Bite wrote (🧪 below).", w)
                              if c in wrote else w) for c, (k, _, w) in zip(checked, said)]
    for c in wrote:  # --write-tests: the missing test, folded, ready to paste in
        g = c["guard"]
        fence = "~~~~"  # never closed early by a ``` inside the test
        lines += ["", f"<details><summary>🧪 The missing test for {sha(c)}: passes with the change, fails without it</summary>", "",
                  f"Save it as `{g['test_file']}` and run `{g['run']}`."
                  + (f" It checks that {html.escape(g['guards'].rstrip('.'), quote=False)[:200]}." if g.get("guards") else ""), "",
                  fence + FENCE_LANG.get(Path(g["test_file"]).suffix.lower(), ""), g["test"].rstrip(), fence, "", "</details>"]
    run = os.environ.get("GITHUB_RUN_ID", "")
    if wrote and run.isdigit():  # the Action uploads bite_proof/missing_tests/ as a download on the run's page
        url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{run}"
        lines += ["", f"📥 Or download {'it' if len(wrote) == 1 else 'them all'}, already in the right folder"
                  f"{'' if len(wrote) == 1 else 's'}: **bite-missing-tests** under Artifacts on [this run's page]({url})."]
    total, last = os.environ.get("BITE_PR_COMMITS", ""), os.environ.get("BITE_CHECKED_COMMITS", "")
    if total.isdigit() and last.isdigit() and int(total) > int(last) and not error:
        lines += ["", f"Bite looked at the newest {last} of this pull request's {total} commits."]
    # Every comment ends the same way: the fold, the same few words on how Bite checks, and the link.
    lines += ["", "<details><summary>How Bite checks</summary>", "",
              "Bite asks one question about each change: if it disappeared, would any test notice? It takes the change "
              "out, runs your tests, and puts it back. "
              + ("The steps to rerun each check yourself are on the job's summary page. " if bad else "")
              + "[What is Bite?](https://github.com/connabyss/bite)", "", "</details>"]
    lines[1] = lines[1].replace("### ", f"### {CAT} ", 1)
    p = proof_dir(root) / "COMMENT.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def undo_steps(root: Path, sha: str, files: list) -> list:
    """The commands that take a commit's code change back out: restore the files it edited, delete the ones it
    created. `git checkout <sha>^ -- <file>` fails for a file the commit added, so it can't carry those."""
    restored, created = [], []
    for rel in files:
        target = restored if repo.git(root, "cat-file", "blob", f"{sha}^:{rel}", raw=True) is not None else created
        target.append(rel)
    steps = []
    if created:
        steps.append("rm -f " + " ".join(created))
    if restored:
        steps.append(f"git checkout {sha}^ -- {' '.join(restored)}")
    return steps


def write_free(root: Path, cfg, flagged: list) -> Path:
    """The free pass's findings, each with a rerun recipe and a note to hand to the user's own coding AI."""
    lines = ["# Bite: changes no test noticed", "",
             "Bite took each change below out, kept the tests, and ran them. Every test still passed, so nothing would "
             "warn you if the change broke. This check is free; no AI was used.", ""]
    for i, c in enumerate(flagged, 1):
        sha = c["sha"]
        steps = undo_steps(root, sha, c["code"])
        lines += [f"## {i}. {sha[:8]} {c['subject']}", "", f"- What Bite saw: {say(c)[2][3:]}",
                  f"- Code it changed: {', '.join(c['code'])}", "", "Check it yourself (a throwaway copy; your checkout "
                  "isn't touched):", "", "```", f"git worktree add ../bite_check {sha}", "cd ../bite_check",
                  *steps, f"{cfg.test_cmd}", "# every test passes: no test noticed the change was gone",
                  f"cd {root.as_posix()}", "git worktree remove --force ../bite_check", "```", "", "Hand this to your coding AI:", "", "```",
                  f"Commit {sha[:8]} (\"{c['subject']}\") changed {', '.join(c['code'])}. With that change undone, "
                  f"the tests still pass ({'its own tests: ' + ', '.join(c['test_code']) if c.get('test_code') else 'no test covers it'}). "
                  "Write one small test of what this commit changed, next to the existing tests. Show that it fails "
                  f"with the change undone ({'; '.join(steps)} in a throwaway worktree) and passes "
                  "with it. Don't change the code.", "```", ""]
        g = c.get("guard") or {}
        if g.get("status") == "WRITTEN":
            name = f"{sha[:8]}_{Path(g['test_file']).name}"
            (proof_dir(root) / name).write_text(g["test"], encoding="utf-8")
            lines += ["Bite wrote the missing test (`--write-tests`). It passed twice with the change in, and with the "
                      "change taken out it failed like this:", "", "```", g["fail"].strip(), "```", "",
                      f"- The test: [{name}]({name}). Save it as `{g['test_file']}`, then run `{g['run']}`.", ""]
        elif g:
            lines += [f"Bite tried to write the missing test (`--write-tests`) but didn't keep it: {g['status']}.", ""]
    p = proof_dir(root) / "FREE_REPORT.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def save_missing_tests(root: Path, cs: list) -> list:
    """Each test --write-tests kept, at its own path inside bite_proof/missing_tests/, so the whole folder can be
    dropped into the project as it is (the Action offers it as a download and can open a pull request with it).
    Two tests at one path (each written on its own copy) get the commit's short sha in the second one's name."""
    d = proof_dir(root) / "missing_tests"
    shutil.rmtree(d, ignore_errors=True)  # last run's tests aren't this run's
    saved = []
    for c in cs:
        g = c.get("guard") or {}
        if g.get("status") != "WRITTEN":
            continue
        rel = g["test_file"]
        if rel in saved:
            rel = re.sub(r"(?i)(bite_?claim)", lambda m: f"{m.group(1)}_{c['sha'][:8]}", rel, count=1)
            if rel in saved:
                continue  # no bite_claim in its name to tell them apart: the comment still shows it
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(g["test"], encoding="utf-8")
        saved.append(rel)
    if not saved:
        shutil.rmtree(d, ignore_errors=True)
    return saved


def write_proof(root: Path, found: list) -> Path:
    d = proof_dir(root)
    lines = ["# Bite: false \"done\" commits", ""]
    for i, r in enumerate(found, 1):
        name = f"{r['sha'][:8]}_{Path(r['test_file']).name}"
        (d / name).write_text(r["test"], encoding="utf-8")
        lines += [f"## {i}. {r['sha'][:8]} {r['subject']}", "", f"- What's wrong: {r['bug']}",
                  f"- Today's code: {r['today']}", f"- Matters: {r['matters']}/3", f"- Test: [{name}]({name})",
                  f"- Run it: copy it to `{r['test_file']}`, then `{r['run']}`", "", "```", r["fail"].strip(), "```", ""]
    (d / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return d

# ---- the demo ------------------------------------------------------------------

# bite --demo: a made-up shop with two commits that say they fixed something. One added a test for its fix, the
# other didn't, so the free pass shows one change a test notices and one it doesn't.
DEMO_STEPS = [
    ("Start a tiny shop", {
        "shop.py": "def discount(price, percent):\n    return price - price * percent / 100\n\n\n"
                   "def total(prices):\n    return sum(prices)\n",
        "test_shop.py": "import unittest\n\nfrom shop import discount, total\n\n\nclass ShopTest(unittest.TestCase):\n"
                        "    def test_discount(self):\n        self.assertEqual(discount(100, 20), 80)\n\n"
                        "    def test_total(self):\n        self.assertEqual(total([1.5, 2.5]), 4.0)\n"}),
    ("Fix discounts over 100% making the price negative", {
        "shop.py": "def discount(price, percent):\n    return max(0, price - price * percent / 100)\n\n\n"
                   "def total(prices):\n    return sum(prices)\n",
        "test_shop.py": "import unittest\n\nfrom shop import discount, total\n\n\nclass ShopTest(unittest.TestCase):\n"
                        "    def test_discount(self):\n        self.assertEqual(discount(100, 20), 80)\n\n"
                        "    def test_discount_never_below_zero(self):\n        self.assertEqual(discount(50, 150), 0)\n\n"
                        "    def test_total(self):\n        self.assertEqual(total([1.5, 2.5]), 4.0)\n"}),
    ("Fix totals showing long decimals like 0.30000000000000004", {
        "shop.py": "def discount(price, percent):\n    return max(0, price - price * percent / 100)\n\n\n"
                   "def total(prices):\n    return round(sum(prices), 2)\n"}),
]


def make_demo(dest: Path) -> Path:
    """The demo project, built in dest as a git repo with one commit per DEMO_STEPS entry."""
    dest.mkdir(parents=True, exist_ok=True)
    git = ["git", "-c", "user.name=Bite demo", "-c", "user.email=demo@example.invalid", "-c", "commit.gpgsign=false"]
    # Fixed dates, so every run makes the same commits (and the same short shas as the README shows).
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T12:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T12:00:00Z"}
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True, capture_output=True)
    for subject, files in DEMO_STEPS:
        for name, text in files.items():
            (dest / name).write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([*git, "add", "-A"], cwd=dest, check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "-m", subject], cwd=dest, check=True, capture_output=True, env=env)
    # The tests run with the Python Bite runs on, so the demo needs nothing else installed. Left out of the
    # commits: its path differs on every machine.
    (dest / ".bite.ini").write_text(f'[kit]\ntest_command = "{sys.executable}" -m unittest\n', encoding="utf-8")
    (dest / ".git" / "info" / "exclude").write_text(".bite.ini\n", encoding="utf-8")
    return dest


def demo(argv: list) -> int:
    dest = make_demo(Path(tempfile.mkdtemp(prefix="bite_demo_")) / "tiny-shop")
    print(f"Bite demo: a made-up project in {dest}\n"
          "Two of its commits say they fixed something. One added a test for its fix, the other didn't.\n"
          "Bite takes each fix back out and runs the tests, to see whether any test notices it's gone.\n", flush=True)
    here = os.getcwd()
    os.chdir(dest)
    try:
        rc = main(["--free", *(a for a in argv if a not in ("--demo", "--free"))])
    finally:
        os.chdir(here)
    print("\nThat was the demo; nothing of yours was touched. To check your own project: go into it and run bite --free")
    return rc


# Every option main() accepts; each one must be in the help text above (the self-test checks).
FLAGS = {"--free", "--all", "--any", "--serious", "--again", "--roast", "--demo", "--write-tests"}
VALUED = {"--last": int, "--free-checks": int, "--suspects": int, "--budget": float, "--since": str}


def extras(root: Path, cfg) -> list:
    """The .bite.ini settings only recent.py reads (claim_command, free_test_command) go onto cfg; returns
    test_covers as a list of globs."""
    cfg.claim_cmd = cfg.free_cmd = ""
    ini = Path(os.environ["BITE_CONFIG"]) if os.environ.get("BITE_CONFIG") else root / ".bite.ini"
    if not ini.is_file():
        return []
    import configparser
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ini, encoding="utf-8")
    kit = cp["kit"] if "kit" in cp else {}
    cfg.claim_cmd = kit.get("claim_command", "").strip()
    cfg.free_cmd = kit.get("free_test_command", "").strip()
    return [g.strip().replace("\\", "/") for g in kit.get("test_covers", "").split(",") if g.strip()]


def _installed_version():
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("bite-check")
    except PackageNotFoundError:  # running from a clone, not installed
        text = (bite.KIT_DIR / "pyproject.toml").read_text(encoding="utf-8")
        found = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return found.group(1) if found else "unknown"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["live"]:  # the live check for coding AIs (live.py): bite live, bite live --hook
        import live
        return live.main(argv[1:])
    if "--version" in argv:
        print(f"bite {_installed_version()}")
        return 0
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    i = 0
    while i < len(argv):  # a typo must not fall through to the paid step
        if argv[i] in VALUED and i + 1 < len(argv):
            kind = VALUED[argv[i]]
            try:
                kind(argv[i + 1])
            except ValueError:
                need = "a whole number" if kind is int else "a number"
                print(f"Bite: {argv[i]} needs {need}, got {argv[i + 1]!r}.")
                return 2
            i += 2
        elif argv[i] in FLAGS:
            i += 1
        else:
            print(f"Bite: unknown option {argv[i]!r}. Run bite --help for the options.")
            return 2
    opt = lambda k, d: type(d)(argv[argv.index(k) + 1]) if k in argv else d  # noqa: E731
    ROAST[0] = "--roast" in argv
    if not shutil.which("git"):
        print("Bite: git isn't installed (or isn't on PATH). Install it from https://git-scm.com, "
              "then open a new terminal window.")
        return 1
    if "--demo" in argv:
        return demo(argv)
    root = repo.repo_root(os.getcwd())
    if root is None:
        print("Bite: not inside a git repository.")
        return 1
    try:
        cfg = repo.load_cfg(root)
    except repo.ConfigError as e:
        print(f"Bite: {e}")
        write_comment(root, [], error=str(e))
        return 1
    covers = extras(root, cfg)
    if not cfg.test_cmd:
        print("Bite: no test command found; set test_command in .bite.ini")
        write_comment(root, [], error="Bite found no test command. Set test_command in .bite.ini.")
        return 1
    if not cfg.programs:  # the worker may run the test runner and the project's language, nothing new
        first = cfg.test_cmd.split()[0]
        cfg.programs = sorted({first, "python", "python3", "pytest", "node", "npx", "go", "cargo", "dotnet"} - {"npx"})
    missing = preflight(cfg)
    if missing:
        print(f"Bite: {missing}")
        write_comment(root, [], error=missing)
        return 1
    since = opt("--since", "")
    if since and repo.git(root, "rev-parse", "--verify", "-q", f"{since}^{{commit}}") is None:
        print(f"Bite: --since {since} isn't a commit or branch in this repository.")
        write_comment(root, [], error=f"Bite couldn't find {since} (--since) in this repository.")
        return 1
    t0 = time.time()
    cs = commits(root, opt("--last", 40), since)  # --all is still accepted: every commit is the default now
    for c in cs:
        files_of(root, c, cfg)
    other = [c for c in cs if c["other_lang"] and not c["code"]]
    cs = [c for c in cs if c["code"]]
    newest = cs[0]["sha"] if cs else ""  # git log lists the newest first
    print(f"Bite: {len(cs)} commits changed code in the last {opt('--last', 40)}.", flush=True)
    lang = repo.runs_language(cfg.test_cmd)[0]
    if other:
        print(f"  {len(other)} changed only code your tests can't run (they run {lang}), not checked: "
              + ", ".join(c["sha"][:8] for c in other), flush=True)
    if not cs:
        print("Nothing to check. Try a larger --last.")
        write_comment(root, [], none=f"The code changed here isn't {lang}, and your tests only run {lang}, so they "
                                     "can't notice it." if other else "")
        return 0
    n_out = 0
    if covers:  # a change the test command can't reach can't fail a test: that says nothing about the change
        import fnmatch
        out = [c for c in cs if not any(fnmatch.fnmatch(f, g) for f in c["code"] for g in covers)]
        cs = [c for c in cs if c not in out]
        n_out = len(out)
        if out:
            print(f"  {len(out)} outside the tests' reach (test_covers), not checked: "
                  + ", ".join(c["sha"][:8] for c in out), flush=True)
        if not cs:
            print("Nothing the tests can reach. Check test_covers in .bite.ini.")
            write_comment(root, [], none="The code changed here is outside test_covers in .bite.ini, so the tests can't reach it.")
            return 0
    write_tests = "--write-tests" in argv
    free_only = "--free" in argv or write_tests  # --write-tests writes guard tests instead of testing claims
    if not any(c["claims"] for c in cs) and "--any" not in argv:
        cs = [c for c in cs if c["test_code"]]
        print(f"No fix claims found in the last {opt('--last', 40)} commits, so there's nothing to hold them to"
              + (f". Checking the {len(cs)} that added tests: do those tests check the change?" if cs else
                 ". (--any checks them anyway.)"), flush=True)
        if not cs:
            write_comment(root, [], none="No commit in this pull request says it fixes something, so there's no claim to check.")
            return 0
        free_only = True  # no claim to turn into a test
    if "--serious" in argv:  # only fix claims about data, money, logins, security, crashes or leaks
        cs = [c for c in cs if c.get("serious")]
        print(f"  {len(cs)} of them claim a fix about data, money, logins, security, crashes or leaks.")
        if not cs:
            print("Nothing serious to check. Run without --serious to test the other claims.")
            write_comment(root, [], none="No commit claims a fix about data, money, logins, security, crashes or leaks.")
            return 0
    cs.sort(key=lambda c: -c["score"])
    logf = root / "bite_proof" / "recent_log.json"
    try:  # read before the free pass saves over it
        kept = json.loads(logf.read_text(encoding="utf-8")).get("tried", [])
    except (OSError, ValueError):
        kept = []
    free = cs[:opt("--free-checks", 6)]
    print(f"  free check of {len(free)}: each runs the tests twice (with and without the change)", flush=True)
    for c in free:
        c["undo"] = undo_check(root, c, cfg)
        if c["undo"].startswith("unguarded"):
            c["score"] += 2
        elif c["undo"] == "TEST GUARDS NOTHING":
            c["score"] += 3
        print(f"  {c['sha'][:8]} {say(c)[1]:<28} {short(c['subject'])}", flush=True)
        if c.get("why"):  # say what broke, so it's clear whether it's the project or the copy
            print(f"           why: {c['why']}", flush=True)
        save_log(root, kept, cs)
    cs.sort(key=lambda c: -c["score"])
    found, tried = [], []
    before = [] if "--again" in argv else kept  # claims tested on an earlier run aren't paid for again
    done = {r["sha"] for r in before}
    found = [r for r in before if r.get("status") == "FALSE DONE"]
    cs = [c for c in cs if c["sha"] not in done]
    if before:
        print(f"  {len(done)} claims were tested on an earlier run ({len(found)} false); testing the next ones")
    if not free_only:
        budget = opt("--budget", 1.0)
        n = opt("--suspects", 3)
        for c in cs[:n]:
            left = budget - SPENT[0]
            if left < 0.15:
                print("  budget used up")
                break
            print(f"  testing the claim of {c['sha'][:8]} ...", flush=True)
            r = try_claim(root, c, cfg, min(left - 0.05, budget / n + 0.10))
            tried.append(r)
            print(f"    {r['status']}" + (f": {r.get('today')}" if r["status"] == "FALSE DONE" else ""), flush=True)
            save_log(root, before + tried, cs)
            if r["status"] == "FALSE DONE":
                found.append(r)
    found.sort(key=lambda r: (r["today"] != "STILL BROKEN", -r["matters"]))
    print()
    if found:
        top = found[0]
        print(f"FALSE \"DONE\": commit {top['sha'][:8]} said \"{top['subject']}\".")
        print(f"  {top['bug']}")
        print(f"  Today's code: {top['today']}.")
        print("  The test that shows it:\n" + "\n".join("    " + ln for ln in top["fail"].strip().splitlines()[:10]))
        d = write_proof(root, found)
        tried = before + tried
        print(f"\n{len(found)} false \"done\" in {len(tried)} claims tested. Proof and run commands: {d / 'REPORT.md'}")
    elif tried or before:
        tried = before + tried
        print(f"All {len(tried)} claims tested held up: " + "; ".join(f"{r['sha'][:8]} {r['status']}" for r in tried))
    flagged = [c for c in cs if c.get("undo") == "TEST GUARDS NOTHING" or c.get("undo", "").startswith("unguarded")]
    if write_tests and flagged:
        budget, n = opt("--budget", 1.0), opt("--suspects", 3)
        for c in flagged[:n]:
            left = budget - SPENT[0]
            if left < 0.15:
                print("  budget used up")
                break
            print(f"  writing the missing test for {c['sha'][:8]} ...", flush=True)
            c["guard"] = try_guard(root, c, cfg, min(left - 0.05, budget / n + 0.10))
            print(f"    {'wrote one: passes with the change, fails without it' if c['guard']['status'] == 'WRITTEN' else c['guard']['status']}",
                  flush=True)
    for c in flagged:
        print(f"{say(c)[1]}: {c['sha'][:8]} \"{short(c['subject'])}\": {flat(say(c)[2])[2:].strip()}")
    checked = [c for c in cs if c.get("undo")]
    held = [c for c in checked if c["undo"].startswith(("guarded", "closed since"))]
    print(f"\nChecked {len(checked)} commit(s): a test noticed {len(held)}, no test noticed {len(flagged)}, "
          f"{len(checked) - len(held) - len(flagged)} couldn't be checked or skipped"
          + (f"; {n_out} outside the tests' reach" if n_out else "")
          + (f"; {len(other)} in code your tests can't run" if other else "") + ".")
    if bite_proof([say(c)[0] for c in checked], tried):
        print(f"\nBite-proof. Nice work. Every change Bite checked had a test that noticed it.\n"
              f"Badge for your README: {BADGE}")
    if flagged:
        print(f"Each change no test noticed, with a check you can rerun and a note for your coding AI: {write_free(root, cfg, flagged)}")
    print(f"\n{time.time() - t0:.0f}s, ${SPENT[0]:.2f}")
    save_log(root, tried, cs)
    save_missing_tests(root, flagged)
    write_comment(root, cs, newest=newest)
    print(f"One-page report (open it in your browser): {write_html(root, cs, tried, time.time() - t0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
