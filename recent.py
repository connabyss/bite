"""
Bite: did your coding agent's recent "done" commits really do what they said?

    bite                      check the last 40 commits (step 2 needs an API key)
    bite --version            print the installed version, and the line to update when a newer one is out
    bite --free               step 1 only: no key, no cost
    bite --demo               try it on a tiny made-up project first (free, about 30 seconds)
    bite --demo comeback      see the comeback alarm: a later commit quietly undoes a fix, and Bite names it
    bite --last 80 --suspects 3 --budget 1.00
    bite --serious            only fix claims about data, money, logins, security, crashes or leaks
    bite --any                check commits even when none of them claims a fix
    bite --free-checks 10     how many commits step 1 checks (default 6)
    bite --again              test claims again even if an earlier run already tested them
    bite --all                same as plain bite (kept so older commands still work)
    bite --roast              the same results, worded a little more gently
    bite --quick              faster: skip the piece-by-piece check, the flaky-test rerun and the deleted-test check
                              (--part-runs N: test runs the piece check may use in one run, 6 by default)
    bite --since main         only commits that main doesn't have (the pull request check uses this)
    bite --json               print the results as JSON for other programs (the rest goes to stderr); they're
                              also saved in bite_proof/results.json on every run
    bite --write-tests        after the free check, write the missing test for each change no test noticed
                              (API key, capped by --budget; --suspects sets how many, default 3)
    bite live                 check the changes since the last commit now (bite live --help: the live check for
                              coding AIs, and the Claude Code plugin's Stop hook)
    bite ask "is last week's login fix guarded?"
                              ask in plain words: Bite finds the matching commit(s) and checks them (free;
                              bite ask --help)
    bite mcp                  the same check as a tool your coding AI can call (an MCP server: Claude Code,
                              Cursor, Copilot in VS Code, Windsurf, Codex, Gemini CLI)
    (from a clone without installing: python recent.py, python recent.py --free, ...)

Step 1 (free): for each commit that changed code, the change is taken back out and the tests are run. If they
still pass, no test shows the change does anything ("NO TEST NOTICED"). If the commit added or changed tests and
those still pass without its code change, they test nothing it did ("ITS TESTS DIDN'T NOTICE"). Commits that
claim a fix come first.
The comeback alarm (free, no test runs): when a checked commit's change is gone from today's code because a later
commit put the old code back, Bite says so ("UNDONE BY A LATER COMMIT") and names that commit. A later commit
that says it's a revert counts as done on purpose and is only noted.
Step 2 (API key, spending capped by --budget): for the top suspects, a fresh worker turns the commit's own claim into one
small test (with the odd inputs the claim covers) on a copy of the project at that commit. Bite then runs the
test itself, twice, at that commit and on today's code, and a second fresh check must agree that the test asks
only for what the commit claimed and fails for a real reason. Only then is it shown as a false "done".

Results are written to bite_proof/ in the repo: report.html (one page to open in a browser), and each
failing test plus the command that runs it.
--write-tests (API key, capped by --budget): for each change no test noticed, a fresh worker writes the test that's
missing, on a copy at that commit. Bite runs it itself and keeps it only if it passes twice with the change in,
fails with the change taken out, and a second fresh check calls it fair. It's shown ready to paste in (and in the pull request comment). Instead of step 2.
Settings: .bite.ini in the repo (optional; first line [bite], then test_command = ...). claim_command runs one
test file ({file}); without it Bite adds the file to test_command (for dotnet test, Maven and Gradle it picks the
test by its class name instead).
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
import difflib
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
# Words that say a commit fixes something: they outweigh tidy-up and speed-up words ("refactor: fix the crash").
FIXES = re.compile(r"\b(fix(e[sd]|ing)?|bug(s|fix(es)?)?|correct(s|ed|ing)?|crash(es|ing)?)\b", re.I)
# Code that checks which OS or Python it runs on: only behind one can a change's code path skip this machine.
PLATFORM_CODE = re.compile(r"sys\.platform|os\.name\b|platform\.(system|mac_ver|win32_ver)|\bwin(32|64|dows)\b|_WIN32|"
                           r"\bdarwin\b|\bmacos\b|\blinux\b|cfg!?\(\s*(windows|unix|target_os|target_family)|runtime\.GOOS|"
                           r"go:build|\+build|process\.platform|os\.platform\(|OperatingSystem\.Is|OSPlatform|IS_OS_|"
                           r"os\.name\b|msvcrt|winreg|windll|ntpath|WindowsPath|_winapi|win32api|fcntl|termios|"
                           r"\.(ps1|bat|cmd)\b", re.I)
VERSION_CODE = re.compile(r"version_info|hexversion|\bPY3\d*\b|\bPY2\b|PY_VERSION|python_version|sys\.version\b|"
                          r"importlib_metadata|typing_extensions|__future__")
REVERT = re.compile(r'^(?:Revert|Reapply)\s+"', re.I)
TIDY_SKIP = "a tidy-up, so there's nothing new to check"
# Speed-ups: tests check results, not speed, so the slower old code passing them is expected.
SPEED = re.compile(r"^perf(\([^)]*\))?!?:|\b(faster|speed(s|ing)?[ -]?up|lazy|lazily|optimi[sz]\w*|performance)\b", re.I)
# dotnet test exits 0 when its --filter matches no test: that's a test that never ran, not a claim that holds.
# Gradle stops when its --tests filter matches nothing; Maven's summary says how many ran.
RAN_NOTHING = re.compile(r"No test matches the given testcase filter|No test is available in|No tests found for given includes")
DOTNET_FILTER = '--filter "FullyQualifiedName~BiteClaim"'
ROAST = [False]  # --roast: the same results, worded a little more gently
# Earned when every change Bite checked had a test that noticed it; a repo can show it in its README.
BADGE = "[![Bite-proof ✅](https://img.shields.io/badge/Bite--proof-%E2%9C%85-black)](https://github.com/connabyss/bite)"


def ran_nothing(cmd: str, out: str) -> bool:
    """A run that passed without running any test (dotnet test on a project that isn't a test project, a filter
    that matched nothing) shows nothing about the code."""
    if RAN_NOTHING.search(out) or all_skipped(out):
        return True
    if re.search(r"\bdotnet(\.exe)?\s+test\b", cmd):
        return not re.search(r"Total(?: tests)?:\s*[1-9]", out)
    if MAVEN.search(cmd):  # Maven says "Tests run: N" for every module that ran tests
        return not any(int(n) > int(k) for n, k in re.findall(r"Tests run: (\d+), Failures: \d+, Errors: \d+, Skipped: (\d+)", out))
    return False


def all_skipped(out: str) -> bool:
    """Every test was skipped (pytest's "3 skipped in 0.1s", unittest's "OK (skipped=3)", jest, vitest, node --test,
    mocha, dotnet test): the run passed without any test checking anything."""
    def nums(pattern):
        return [int(x) for x in re.findall(pattern, out, re.M)]
    if re.search(r"^=*\s*\d+ (?:skipped|deselected)(?:, \d+ (?:skipped|deselected|warnings?))* in [\d.]+s\b", out, re.M):
        return True  # pytest: a summary with no passed, failed or error in it
    ran, skipped = nums(r"^Ran (\d+) tests? in "), nums(r"^OK \(skipped=(\d+)\)")
    if ran and skipped and sum(ran) == sum(skipped):
        return True  # unittest
    for total, skip in ((r"^Tests:.*?\b(\d+) total", r"^Tests:.*?\b(\d+) skipped\b"),  # jest
                        (r"^\s*Tests\s+.*\((\d+)\)\s*$", r"^\s*Tests\s+(\d+) skipped\b"),  # vitest
                        (r"^\s*(?:#|ℹ) tests (\d+)", r"^\s*(?:#|ℹ) skipped (\d+)")):  # node --test, tap
        t, k = nums(total), nums(skip)
        if t and k and sum(t) == sum(k) and sum(t) > 0:
            return True
    if nums(r"^\s*(\d+) pending\b") and not any(nums(r"^\s*(\d+) passing\b")) and not nums(r"^\s*\d+ failing\b"):
        return True  # mocha
    return bool(re.search(r"Failed:\s*0, Passed:\s*0, Skipped:\s*[1-9]", out))  # dotnet test


MAVEN = re.compile(r"(?:^|[\s/\\])(?:mvn|mvnw)(?:\.cmd|\.bat)?(?=\s|$)")
GRADLE = re.compile(r"(?:^|[\s/\\])(?:gradle|gradlew)(?:\.bat)?(?=\s|$)")


def build_folder(folder: Path, rel: str, names: tuple) -> str:
    """The folder of the Maven module or Gradle project a file belongs to: the nearest folder above it with one of
    these build files, as a path from the project ("" for the project itself)."""
    d = posixpath.dirname(rel)
    while d:
        if any((Path(folder) / d / n).is_file() for n in names):
            return d
        d = posixpath.dirname(d)
    return ""


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


def code_text(root: Path, c: dict) -> str:
    """The commit's code files as they are after it, with their names: where a platform or version check would be."""
    return "\n".join(n + "\n" + (repo.git(root, "show", f"{c['sha']}:{n}") or "") for n in c["code"])


def skip_reason(subject: str, said: str, code: str | None = None) -> str:
    """Why this commit can't say anything here, or "" when it can. code is the changed files' text (see code_text):
    naming another OS or Python version only skips a change whose code checks for one, since only then does its
    code path not run here. Saying it fixes something outweighs tidy-up and speed-up words."""
    text = said.lower()
    built_for = {os_ for os_, words in PLATFORM_WORDS.items() if re.search(rf"\b({words})", text)}
    if "case-insensitive file" in text:
        built_for |= {"win", "mac"}
    fixes = bool(FIXES.search(subject)) and not NOT_CODE.search(subject)
    if built_for and HERE not in built_for and (code is None or PLATFORM_CODE.search(code)):
        names = {"win": "Windows", "mac": "macOS", "linux": "Linux"}
        return f"built for {'/'.join(sorted(names[o] for o in built_for))}, can't be checked on {names[HERE]}"
    for_py = [(int(m.group(1)), bool(m.group(2))) for m in PY_VERSION.finditer(text)]
    here = sys.version_info[1]
    if for_py and not any(v == here or (later and here > v) for v, later in for_py) and (code is None or VERSION_CODE.search(code)):
        versions = "/".join(f"3.{v}" + ("+" if later else "") for v, later in dict.fromkeys(for_py))
        return f"built for Python {versions}, can't be checked on Python 3.{here}"
    if RELEASE.search(subject):
        return "a release, so it only changes the version number"
    if TIDY.search(subject) and not fixes:
        return TIDY_SKIP
    if SPEED.search(subject) and not fixes:
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


def bare_code(src: bytes | None, suf: str):
    """The file's code with comments and whitespace out, for telling whether two versions differ in code."""
    if src is None:
        return None
    lines = bite.code_lines(src.decode("utf-8", "replace"), suf)
    if suf == ".go":  # Go's any is interface{} under another name (Go 1.18+)
        lines = [re.sub(r"\binterface\s*\{\s*\}", "any", ln) for ln in lines]
    return [t for t in ("".join(ln.split()) for ln in lines) if t]


def same_code(old: bytes | None, new: bytes | None, suf: str, reads: bool = True) -> bool:
    """The two versions do the same: only comments or layout differ (and for Python, docstrings or type hints).
    reads=False leaves docstrings and hints out even in a file that reads them (a --help text, say)."""
    if old is None or new is None:
        return False
    if suf == ".py":
        a, b = py_tree(old, reads), py_tree(new, reads)
        if a is not None and b is not None:
            return a == b  # the syntax tree knows a "#" inside a string isn't a comment
    return bare_code(old, suf) == bare_code(new, suf)


def comment_only(root: Path, sha: str, rel: str, old_rel: str = "") -> bool:
    """The change to this file is comments or whitespace only: undoing it can't make a test fail. old_rel is the
    file's name before the commit, when the commit moved it."""
    old = repo.git(root, "cat-file", "blob", f"{sha}^:{old_rel or rel}", raw=True)
    new = repo.git(root, "cat-file", "blob", f"{sha}:{rel}", raw=True)
    return same_code(old, new, Path(rel).suffix.lower())


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


# Code that reads its own docstrings (docopt(__doc__), argparse(description=__doc__)) or type hints at run time:
# in a file that does, they're code too.
READS_DOCS = re.compile(rb"__doc__|getdoc\b")
READS_HINTS = re.compile(rb"__annotations__|get_type_hints|get_annotations|\bsignature\(")


def py_tree(src: bytes, reads: bool = True):
    """What the Python file does, as a syntax tree: docstrings, type hints and layout left out (unless the file
    reads them at run time and reads is True). None when it doesn't parse."""
    try:
        t = ast.parse(src or b"")
    except (SyntaxError, ValueError):
        return None
    if not (reads and READS_DOCS.search(src or b"")):
        for node in ast.walk(t):
            body = getattr(node, "body", None)
            if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body
                    and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    if not (reads and READS_HINTS.search(src or b"")):
        drop_hints(t)
    return ast.dump(t)


def changed_files(root: Path, sha: str) -> tuple[list, dict]:
    """The files a commit changed, and the ones it moved ({new name: old name}). A moved file is listed once, by
    its new name: taking the commit out puts the old content back under the new name, so a fix that rode along
    with a move is checked like any other (rather than the tests crashing on the missing new name)."""
    raw = repo.git(root, "diff-tree", "--no-commit-id", "-r", "-z", "--name-status", "-M", sha) or ""
    parts, names, moved, i = raw.split("\0"), [], {}, 0
    while i < len(parts) and parts[i]:
        st = parts[i]
        if st[:1] in "RC" and i + 2 < len(parts):
            old, new = parts[i + 1], parts[i + 2]
            names.append(new)
            if st[0] == "R" and Path(old).suffix.lower() == Path(new).suffix.lower():
                moved[new] = old
            elif st[0] == "R":
                names.append(old)  # moved into another language: both sides are their own change
            i += 3
        else:
            names.append(parts[i + 1] if i + 1 < len(parts) else "")
            i += 2
    return [n for n in names if n], moved


def code_paths(c: dict) -> list:
    """The commit's code files under both their names, for git diff (with -M it shows a move as one change)."""
    return list(dict.fromkeys(c["code"] + [c.get("moved", {})[n] for n in c["code"] if n in c.get("moved", {})]))


def files_of(root: Path, c: dict, cfg) -> None:
    names, moved = changed_files(root, c["sha"])
    c["tests"] = [n for n in names if bite.is_test_file(n, cfg)]
    c["code"] = [n for n in names if n not in c["tests"] and Path(n).suffix.lower() in repo.CODE_SUFFIXES
                 and not repo.is_setup(n, cfg) and not comment_only(root, c["sha"], n, moved.get(n, ""))]
    c["moved"] = {n: o for n, o in moved.items() if n in c["code"]}
    # Code in a language the test command doesn't run can't fail a test: taking it out says nothing about it.
    runs = repo.runs_language(cfg.test_cmd)[1]
    c["other_lang"] = [n for n in c["code"] if runs and Path(n).suffix.lower() not in runs]
    c["code"] = [n for n in c["code"] if n not in c["other_lang"]]
    stat = repo.git(root, "diff", "-M", "--shortstat", f"{c['sha']}^", c["sha"], "--", *code_paths(c)) if c["code"] else ""
    c["lines"] = sum(int(x) for x in re.findall(r"(\d+) (?:insertion|deletion)", stat or ""))
    # 'Revert "Fix the login crash"' quotes the commit it undoes: that title isn't this commit's claim.
    claims = bool(CLAIM.search(c["subject"])) and not NOT_CODE.search(c["subject"]) and not REVERT.match(c["subject"])
    c["claims"] = claims
    # Trailers out first: "Co-Authored-By" would match auth in every co-authored commit.
    said = c["subject"] + " " + re.sub(r"(?im)^[\w-]+-by:.*$", "", c["body"])[:400]
    c["serious"] = claims and bool(MATTERS.search(said))
    c["skip"] = skip_reason(c["subject"], said, code_text(root, c))
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
        if (Path(cfg.project) / first).is_file():
            pass  # the project's own script or wrapper (gradlew.bat, mvnw.cmd)
        elif not shutil.which(first):
            return (f"Bite can't find {first!r}, the first word of the test command ({cmd}). "
                    "Install it, or set test_command in .bite.ini to the command that runs your tests.")
        if (MAVEN.search(cmd) or GRADLE.search(cmd)) and not (shutil.which("java") or os.environ.get("JAVA_HOME")):
            return (f"Maven and Gradle need Java, and Bite can't find it (java isn't on PATH and JAVA_HOME isn't set), "
                    "so your tests can't run. Install a JDK (for example from https://adoptium.net), then run Bite again.")
        if words[1:3] == ["-m", "pytest"] and subprocess.run([first, "-c", "import pytest"],
                                                           capture_output=True).returncode != 0:
            return (f"pytest isn't installed for this Python ({shutil.which(first)}), so your tests can't run. "
                    f"Install it, then run Bite again:\n    {first} -m pip install pytest")
    return ""


def take_out(root: Path, c: dict, folder: Path) -> None:
    """Put this commit's code files in the copy back the way they were before it (its tests stay)."""
    before = c.get("before") or f"{c['sha']}^"  # the live check passes the commit the turn started from
    if c.get("part_undo"):  # only the piece no test noticed (see unnoticed_part)
        rest = {k: v for k, v in c.items() if k != "part_undo"}
        for rel, data in c["part_undo"].items():
            if data is None:
                take_out(root, {**rest, "code": [rel]}, folder)
            else:
                bite.safe_write(folder, folder / rel, data)
        return
    for rel in c["code"]:
        # A moved file gets its old content under its new name: the move stays, the change rides out.
        old = repo.git(root, "cat-file", "blob", f"{before}:{c.get('moved', {}).get(rel, rel)}", raw=True)
        t = folder / rel
        if old is None and t.suffix == ".py" and t.name != "__init__.py":
            # A file the commit created: deleting it would let Python find an installed copy (pip install -e .)
            # and import that instead, so the tests pass. A file that refuses to load stands in for it.
            bite.safe_write(folder, t, b'raise ImportError("Bite took this file out: the commit it checks made it")\n')
        elif old is None:
            t.unlink(missing_ok=True)
        else:
            bite.safe_write(folder, t, old)


def is_rust_doc(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("///") or s.startswith("//!")


def keep_docs(old: bytes, new: bytes) -> bytes | None:
    """The Rust file as it was before the commit, but with the commit's doc comments (/// and //!) kept. In Rust an
    example in a doc comment is a test (cargo test runs it), so taking it out with the code hides that it tested
    the change. None when the commit added no doc example."""
    a = old.decode("utf-8", "replace").splitlines(keepends=True)
    b = new.decode("utf-8", "replace").splitlines(keepends=True)
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    if not any(is_rust_doc(ln) and "```" in ln for op, _, _, j1, j2 in ops if op != "equal" for ln in b[j1:j2]):
        return None  # the commit added no doc example (the file's older examples were already there before)
    out = []
    for op, i1, i2, j1, j2 in ops:
        olds, news = a[i1:i2], b[j1:j2]
        if op in ("equal", "delete"):
            out += olds
            continue
        # The commit's doc lines replace the old ones; its code lines go back to the old code. A doc comment sits
        # above the code it documents, so the doc lines before the chunk's first code line go first.
        first = next((k for k, ln in enumerate(news) if not is_rust_doc(ln)), len(news))
        out += [ln for ln in news[:first] if is_rust_doc(ln)]
        code = [ln for ln in olds if not is_rust_doc(ln) and ln.strip()]
        if first and not code:
            # The commit added a whole new item. Its docs would now sit on top of whatever item comes next, and
            # cargo would name the example after that one: a stand-in with the same name keeps it apart.
            out += stand_in(news[first:], a[:i1])
        out += [ln for ln in olds if not is_rust_doc(ln)]
        out += [ln for ln in news[first:] if is_rust_doc(ln)]
    kept = "".join(out).encode()
    return None if kept == old else kept


RUST_ITEM = re.compile(r"^(\s*)(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe|extern(?:\s+\"[^\"]*\")?)\s+)*"
                       r"(?:fn|struct|enum|union|trait|type|const|static(?:\s+mut)?)\s+([A-Za-z_]\w*)")


def stand_in(code: list, above: list) -> list:
    """An item for a taken-out item's docs to sit on, named like it, so cargo names its example after it. It's a
    const holding (), which the example can't use as the real thing. None in a trait impl (it can only hold the
    trait's own items) or when the item's name can't be read."""
    first = next((ln for ln in code if ln.strip() and not ln.lstrip().startswith("#[")), "")
    m = RUST_ITEM.match(first)
    if not m:
        return []
    pad = m.group(1)
    for ln in reversed(above):  # the block the item sits in: the nearest line indented less than it
        if ln.strip() and len(ln) - len(ln.lstrip()) < len(pad):
            if re.match(r"\s*(?:unsafe\s+)?impl\b.*\bfor\b", ln) or re.match(r"\s*(?:pub\s+)?(?:unsafe\s+)?extern\b", ln):
                return []
            break
    nl = "\r\n" if first.endswith("\r\n") else "\n"
    return [f"{pad}#[allow(dead_code, non_upper_case_globals)]{nl}", f"{pad}const {m.group(2)}: () = ();{nl}"]


# cargo test's name for a doc example: "src/lib.rs - Thing::method (line 12)"
DOCTEST_FAILED = re.compile(r"^test (\S+\.rs - .+? \(line \d+\)) \.\.\. FAILED", re.M)


def doc_example_catches(root: Path, c: dict, folder: Path, fcfg) -> bool:
    """With the code taken out but the commit's Rust doc examples kept, does a doc example fail? Only a failing doc
    example counts: anything else (a doc comment left with nothing under it won't compile) says nothing."""
    before = c.get("before") or f"{c['sha']}^"
    changed = False
    for rel in c["code"]:
        if Path(rel).suffix.lower() != ".rs":
            continue
        old = repo.git(root, "cat-file", "blob", f"{before}:{c.get('moved', {}).get(rel, rel)}", raw=True)
        new = repo.git(root, "cat-file", "blob", f"{c['sha']}:{rel}", raw=True)
        kept = keep_docs(old, new) if old is not None and new is not None else None
        if kept is not None:
            bite.safe_write(folder, folder / rel, kept)
            changed = True
    if not changed:
        return False
    names = DOCTEST_FAILED.findall(bite.run_tests(fcfg, folder)["out"])
    if names:
        c["caught"] = f"`{names[0]}`" + (f" and {len(names) - 1} more" if len(names) > 1 else "")
    return bool(names)


def lines_back(diff: bytes) -> bool:
    """Every hunk of this diff removes a line distinctive enough (10+ characters) to be looked for without its
    context: a closing bracket or a blank line could match anywhere."""
    hunks, cur = [], None
    for ln in diff.decode("utf-8", "replace").splitlines():
        if ln.startswith("@@"):
            cur = []
            hunks.append(cur)
        elif ln.startswith("diff --git"):
            cur = None
        elif cur is not None and ln.startswith("-"):
            cur.append(ln[1:].strip())
    return bool(hunks) and all(any(len(x) >= 10 for x in h) for h in hunks)


def came_back(root: Path, c: dict) -> str:
    """The comeback alarm: "" unless this commit's change is gone from today's code. It is gone when the change
    would apply again, forward, to today's code, and can't be taken back out of it: a later commit put the old code
    back, and neither the fix's lines nor a name it brought in live on anywhere in those files (moved or rewritten
    isn't undone). Then "undone since", or "reverted since" when the commit that undid it says it reverts (on
    purpose), with c["undone_by"] = {"sha", "subject"} for that commit, when Bite can find it. No test runs: it only
    compares code, so it's free."""
    sha, code = c["sha"], c.get("code") or []
    head = repo.git(root, "rev-parse", "HEAD")
    if not head or head == sha or c.get("before") or not code:
        return ""
    # A revert coming undone is the reverted change coming back, and a tidy-up changes nothing a user would miss.
    if REVERT.match(c.get("subject", "")) or c.get("skip") == TIDY_SKIP:
        return ""
    if subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=root, capture_output=True).returncode:
        return ""
    for rel in code:  # a file the fix changed that's gone today was moved or deleted, which isn't an undo
        if repo.git(root, "cat-file", "-e", f"{sha}:{rel}") is not None and repo.git(root, "cat-file", "-e", f"HEAD:{rel}") is None:
            return ""
    diff = repo.git(root, "diff", "--binary", f"{sha}^", sha, "--", *code, raw=True)
    if not diff:
        return ""
    changed = [ln for ln in diff.decode("utf-8", "replace").splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    added = [ln[1:].strip() for ln in changed if ln[0] == "+" and ln[1:].strip()]
    # Moved or rewritten, not undone: the fix's code (or a name it brought in) still lives in today's files.
    show = lambda rev: "\n".join(repo.git(root, "show", f"{rev}:{rel}") or "" for rel in code)  # noqa: E731
    today, before = show("HEAD"), show(f"{sha}^")
    today_lines = {ln.strip() for ln in today.splitlines()}
    long_added = [ln for ln in added if len(ln) >= 10]
    if long_added and sum(ln in today_lines for ln in long_added) * 2 > len(long_added):
        return ""
    words = lambda text: set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text))  # noqa: E731
    if (words("\n".join(added)) - words(before)) & words(today):
        return ""
    with tempfile.TemporaryDirectory(prefix="bite_back_") as d:  # a scratch index: the user's checkout isn't touched
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(d) / "index")}
        ok = lambda *a: subprocess.run(["git", *a], cwd=root, env=env, input=diff, capture_output=True).returncode == 0  # noqa: E731
        context = lines_back(diff)

        def gone(rev: str) -> bool:
            """At rev, the fix's change would apply again and can't be taken back out."""
            if not ok("read-tree", rev):
                return False
            fwd, back = ok("apply", "--cached", "--check", "-"), ok("apply", "--cached", "--check", "-R", "-")
            if not fwd and not back and context:
                # Code added right next to the fix (often at the end of a small file) changes its context lines, so
                # neither way applies. Then the lines the fix removed decide: are they back, and its own lines gone?
                fwd, back = ok("apply", "--cached", "--check", "-C0", "-"), ok("apply", "--cached", "--check", "-C0", "-R", "-")
            return fwd and not back

        if not gone("HEAD"):
            return ""
        # Who put the old code back: the newest commit that touched these files where the fix is gone but wasn't
        # just before it (an older undo that was later fixed again doesn't count). A merge is named only when it
        # dropped the fix itself: one that brings in a branch that still had it isn't the culprit.
        later = (repo.git(root, "rev-list", "--topo-order", "--ancestry-path", "-n200", f"{sha}..HEAD", "--", *code) or "").split()
        culprit, merges = "", []
        for rev in later:
            ups = (repo.git(root, "rev-parse", f"{rev}^@") or "").split()
            if len(ups) > 1:
                merges.append((rev, ups))
            elif ups and gone(rev) and not gone(ups[0]):
                culprit = rev
                break
        else:
            culprit = next((m for m, ups in merges if gone(m) and not any(gone(u) for u in ups)), "")
        if culprit and redone(root, sha, culprit, code):
            return ""  # the culprit wrote its own code for the same thing: done another way, not undone
    if not culprit:
        return "undone since"
    c["undone_by"] = {"sha": culprit, "subject": repo.git(root, "log", "-n1", "--format=%s", culprit) or ""}
    # "Revert ...", "fix #587 by reverting ...": done on purpose, so a note rather than the alarm
    return "reverted since" if re.search(r"(?i)\brevert", c["undone_by"]["subject"]) else "undone since"


def redone(root: Path, sha: str, culprit: str, code: list) -> bool:
    """The commit that took the fix's lines out wrote new code of its own in a function the fix changed: the fix
    was done another way (often a better one), so its text is gone but not what it did. Putting old lines back
    and removing the fix's lines doesn't count as new code; comments don't either."""
    def ops(rev: str, rel: str):
        a = repo.git(root, "cat-file", "blob", f"{rev}^:{rel}", raw=True)
        b = repo.git(root, "cat-file", "blob", f"{rev}:{rel}", raw=True)
        if a is None or b is None:
            return [], [], []
        a = a.decode("utf-8", "replace").splitlines()
        b = b.decode("utf-8", "replace").splitlines()
        return a, b, [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    for rel in code:
        a, b, fix = ops(sha, rel)
        names = {owner(b, j) for _, i1, i2, j1, j2 in fix for j in range(j1, j2)}  # each changed line's function
        names = (names | {owner(a, i) for _, i1, i2, _, _ in fix for i in range(i1, i2)}) - {""}
        old = {ln.strip() for _, i1, i2, _, _ in fix for ln in a[i1:i2]}
        a2, b2, undo = ops(culprit, rel)
        for _, i1, i2, j1, j2 in undo:
            for j in range(j1, j2):
                line = b2[j].strip()
                if len(line) >= 10 and line not in old and not line.startswith(("#", "//", "/*", "*", '"""')) \
                        and owner(b2, j) in names:
                    return True
    return False


def fail_why(run: dict) -> str:
    """What broke in a failed test run, for the report and the comment: the failing test by name with its error
    when the runner gives them (see caught_by), else the last error line, else how the run ended."""
    out = run["out"]
    msg = re.search(r"^FAILED \S+ - (.+)$", out, re.M)  # pytest's summary line carries the error
    errs = [ln.strip(" E>") for ln in out.splitlines() if re.search(r"\b\w+(?:Error|Exception)\b:|No module named ", ln)]
    err = msg.group(1).strip() if msg else errs[-1] if errs else ""
    who = caught_by(out).replace("`", "")
    return ((f"{who} failed" + (f": {err}" if err else "")) if who else err or run["why"])[:160]


def tests_pass_at(root: Path, sha: str, cfg) -> tuple[bool, str]:
    """Whether the tests pass on a copy of the project at sha, and what broke when they don't."""
    folder = export(root, sha, cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        run = bite.run_tests(fcfg, folder)
        return run["ok"], "" if run["ok"] else fail_why(run)
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


def undo_check(root: Path, c: dict, cfg) -> str:
    """'unguarded' when the tests still pass with this commit's code change taken back out; 'TEST GUARDS NOTHING'
    when that includes the tests the commit itself added or changed (they're kept: only the code is undone);
    "undone since" or "reverted since" when a later commit put the old code back (see came_back)."""
    back = came_back(root, c)
    if back:  # the change is gone from today's code: whether a test noticed it then matters less than that
        return back
    folder = export(root, c["sha"], cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):  # the faster subset, for this step only
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        now = bite.run_tests(fcfg, folder)
        if not now["ok"]:
            c["why"] = fail_why(now)
            return "tests fail at this commit"
        if ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return "no tests ran at this commit"
        take_out(root, c, folder)
        undone = bite.run_tests(fcfg, folder)

        def flag():  # would be flagged: first rule out the usual harmless reasons
            if c.get("skip"):
                return f"not flagged: {c['skip']}"
            if c.get("test_code") and not tests_touch(root, c):
                return "not flagged: its tests are about other code"
            if closed_since(root, c, cfg):
                return "closed since: today's tests catch it"
            return "TEST GUARDS NOTHING" if c.get("test_code") else "unguarded"
        if undone["ok"] and doc_example_catches(root, c, folder, fcfg):
            return "guarded"  # by a doc example the commit wrote (Rust runs those as tests)
        if undone["ok"]:
            return flag()
        crashed = bite.load_failure(undone["out"])
        if not crashed and not QUICK[0]:
            # Once more: a test that fails now and then (flaky) can fail by luck. Only a test that fails every
            # time the change is out counts as noticing it.
            again = bite.run_tests(fcfg, folder)
            if again["ok"]:
                c["flaky"] = caught_by(undone["out"]) or "a test"
                return flag()
        c["caught"] = caught_by(undone["out"])
        missed = unnoticed_part(root, c, folder, fcfg)
        if missed and c.get("skip"):
            return f"not flagged: {c['skip']}"
        caught, still = c["caught"], []
        for p in missed:  # a later commit's test may notice a piece now: each is checked on today's code
            set_part(c, [p])
            if today_notices(root, c, cfg) is not True:
                still.append(p)
        c["caught"] = caught
        c.pop("part_undo", None)
        if still:
            set_part(c, still)
            c["part"] = part_text(still)
            return "unguarded: part"
        gone = [] if QUICK[0] else tests_gone_since(root, c, cfg)
        if gone:  # a test noticed it then, but test files were deleted since: does one still notice it today?
            caught = c["caught"]
            if today_notices(root, c, cfg) is False:
                c["caught"], c["gone"] = caught, gone
                return "guard gone since"
            c["caught"] = caught
        return "guarded" if not crashed else "guarded (tests use the new code)"
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


MAX_PARTS = 6  # a commit in more pieces than this isn't split: each piece costs a test run
# Piece runs left for this whole run (--part-runs; the commits Bite checks first get them), and --quick: no piece
# check, no flaky rerun, no deleted-test check, so a commit costs two test runs as it used to.
PART_RUNS = [6]
QUICK = [False]
DEF_LINE = re.compile(r"^(\s*)(?:@\w+\s+)?(?:(?:export|default|async|pub(?:\([^)]*\))?|public|private|protected|internal|static|"
                      r"final|abstract|override|open|suspend|inline|virtual|unsafe|const|extern)\s+)*"
                      r"(?:def|class|function|func|fn|struct|interface|enum|record|impl|trait|object|fun|module)\s+"
                      r"(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")
MEMBER_LINE = re.compile(r"^(\s*)(?:(?:public|private|protected|internal|static|final|abstract|override|virtual|async|"
                         r"synchronized)\s+)+[\w<>\[\], ?]*?\s(\w+)\s*\(")


def owner(lines: list, at_line: int) -> str:
    """The function or class a changed line sits in: the nearest definition above it (or on it) that's indented
    less than it. "" for code at the top of the file."""
    if not lines:
        return ""
    at_line = min(at_line, len(lines) - 1)
    first = lines[at_line]
    pad = len(first) - len(first.lstrip())
    m = DEF_LINE.match(first) or MEMBER_LINE.match(first)
    if m:
        return m.group(2)
    for ln in reversed(lines[:at_line]):
        if not ln.strip():
            continue
        m = DEF_LINE.match(ln) or MEMBER_LINE.match(ln)
        if m and len(m.group(1)) < pad:
            return m.group(2)
    return ""


def parts(root: Path, c: dict) -> list:
    """The commit's code change in pieces: one per function or class it touched in each file (a file it created or
    deleted is one piece). Each piece is (file, name, the file with only that piece taken out, or None for a file
    the commit created)."""
    before = c.get("before") or f"{c['sha']}^"
    out = []
    for rel in c["code"]:
        old = repo.git(root, "cat-file", "blob", f"{before}:{c.get('moved', {}).get(rel, rel)}", raw=True)
        new = repo.git(root, "cat-file", "blob", f"{c['sha']}:{rel}", raw=True)
        if old is None or new is None:
            out.append((rel, "", old))
            continue
        a = old.decode("utf-8", "replace").splitlines(keepends=True)
        b = new.decode("utf-8", "replace").splitlines(keepends=True)
        groups = {}
        for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op[0] == "equal":
                continue
            _, i1, i2, j1, j2 = op
            name = owner(b, j1) if j2 > j1 else owner(a, i1)
            groups.setdefault(name, []).append(op)
        for name, ops in groups.items():
            undone = without(a, b, ops)
            # A piece that's only comments, docstrings or hints isn't one, even where the file reads its
            # docstrings: an untested --help text isn't worth a flag of its own.
            if not same_code(new, undone, Path(rel).suffix.lower(), reads=False):
                out.append((rel, name, undone, (a, b, ops)))
    return out


def without(a: list, b: list, ops: list) -> bytes:
    """The new lines b with these changes (difflib opcodes from a to b) put back the way a had them."""
    keep, j = [], 0
    for _, i1, i2, j1, j2 in sorted(ops, key=lambda o: o[3]):
        keep += b[j:j1] + a[i1:i2]
        j = j2
    return "".join(keep + b[j:]).encode()


def part_text(missed: list) -> str:
    return ", ".join(f"the new file {p[0]}" if p[2] is None else f"`{p[1]}()` in {p[0]}" if p[1] else f"the top of {p[0]}"
                     for p in missed)


def set_part(c: dict, missed: list) -> None:
    """Record these pieces as the part to take out: all of a file's pieces together in that file."""
    c["part_undo"] = {}
    for rel in dict.fromkeys(p[0] for p in missed):
        mine = [p for p in missed if p[0] == rel]
        if any(p[2] is None for p in mine):
            c["part_undo"][rel] = None
        else:
            a, b, _ = mine[0][3]
            c["part_undo"][rel] = without(a, b, [op for p in mine for op in p[3][2]])


def unnoticed_part(root: Path, c: dict, folder: Path, fcfg) -> list:
    """With the whole change out a test failed. Does one fail with each piece of it out alone? A commit can bundle
    a tested change with an untested one (or add a helper that a test only calls): the tested piece shouldn't vouch
    for the rest. Returns the pieces no test noticed (as parts gives them), or [] when every piece was noticed, the
    commit is one piece, or it has too many to try. When no piece alone is noticed, the pieces only count together,
    so that says nothing either."""
    if QUICK[0]:
        return []
    ps = parts(root, c)
    if not 2 <= len(ps) <= min(MAX_PARTS, PART_RUNS[0]):
        if len(ps) > PART_RUNS[0] and 2 <= len(ps) <= MAX_PARTS:
            c["parts_skipped"] = len(ps)
        return []
    PART_RUNS[0] -= len(ps)
    news = {rel: repo.git(root, "cat-file", "blob", f"{c['sha']}:{rel}", raw=True) for rel in c["code"]}
    missed = []
    for p in ps:
        rel, undone = p[0], p[2]
        for r, b in news.items():  # the whole change back in
            if b is not None:
                bite.safe_write(folder, folder / r, b)
        if undone is None:
            take_out(root, {**c, "code": [rel]}, folder)  # a file the commit created
        else:
            bite.safe_write(folder, folder / rel, undone)
        run = bite.run_tests(fcfg, folder)
        if run["ok"] and not ran_nothing(bite.tests_cmd(fcfg), run["out"]):
            missed.append(p)
    return [] if len(missed) == len(ps) else missed


# The names of failing tests, as pytest, unittest, go test, cargo test, jest, dotnet test, Maven and Gradle print them.
FAILED_TEST = re.compile(r"^(?:FAILED|ERROR) \S+::(?:\S+::)*([\w\[\]-]+)|^(?:FAIL|ERROR): (\w+) \(|--- FAIL: (\S+)|"
                         r"^test (\S+) \.\.\. FAILED|✕ (.+?)(?: \(\d+ ?ms\))?$|^\s*Failed (\S+) \[|"
                         r"^\[ERROR\] (?:[\w$]+\.)*?([\w$]+\.[\w$]+|[\w$]+)(?:\([\w.$]*\))?\s+(?:-- )?Time elapsed:.*<<< (?:FAILURE|ERROR)!|"
                         r"^(?:[\w$]+\.)*([\w$]+ > .+?) FAILED$", re.M)


def caught_by(out: str) -> str:
    """The test(s) that failed, for the report: "`test_x`", "`test_x` and 2 more", or "" when none is named."""
    names = list(dict.fromkeys(next(g for g in m.groups() if g).strip() for m in FAILED_TEST.finditer(out)))
    if not names:
        return ""
    return f"`{names[0]}`" + (f" and {len(names) - 1} more" if len(names) > 1 else "")


def closed_since(root: Path, c: dict, cfg) -> bool:
    """A later commit may have closed the gap: on today's code, take this commit's change back out (if it still
    applies) and see whether today's tests now fail where they passed before."""
    return today_notices(root, c, cfg) is True


def tests_gone_since(root: Path, c: dict, cfg) -> list:
    """Test files that were there at this commit and are deleted in today's code."""
    names = (repo.git(root, "diff", "--name-only", "--no-renames", "--diff-filter=D", c["sha"], "HEAD") or "").split("\n")
    return [n for n in names if n and bite.is_test_file(n, cfg)]


def part_diff(root: Path, c: dict) -> bytes:
    """The piece no test noticed (see unnoticed_part) as a patch that puts it in, for git apply -R on today's code."""
    out = []
    for rel, undone in c["part_undo"].items():
        new = repo.git(root, "cat-file", "blob", f"{c['sha']}:{rel}", raw=True) or b""
        if undone is None:
            return b""  # a whole new file: the full diff says the same
        a = undone.decode("utf-8", "replace").splitlines(keepends=True)
        b = new.decode("utf-8", "replace").splitlines(keepends=True)
        out += difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}")
    return "".join(ln if ln.endswith("\n") else ln + "\n\\ No newline at end of file\n" for ln in out).encode()


def today_notices(root: Path, c: dict, cfg):
    """On today's code, with this commit's change taken back out (if it still applies), do today's tests fail where
    they passed before? True or False, or None when Bite can't tell (no later commit, the change no longer applies,
    or today's tests already fail)."""
    head = repo.git(root, "rev-parse", "HEAD")
    if not head or head == c["sha"]:
        return None
    diff = part_diff(root, c) if c.get("part_undo") else repo.git(
        root, "diff", "-M", "--binary", f"{c['sha']}^", c["sha"], "--", *code_paths(c), raw=True)
    folder = export(root, head, cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        if not diff or subprocess.run(["git", "apply", "-R", "--check", "-"], cwd=folder, input=diff,
                                      capture_output=True).returncode != 0:
            return None  # today's code moved on: can't tell
        now = bite.run_tests(fcfg, folder)
        if not now["ok"] or ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return None
        subprocess.run(["git", "apply", "-R", "-"], cwd=folder, input=diff, capture_output=True)
        undone = bite.run_tests(fcfg, folder)
        if undone["ok"]:
            return False
        c["caught"] = caught_by(undone["out"])
        return None if bite.load_failure(undone["out"]) else True
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
  class named BiteClaimTests, inside the folder of an existing test project so that project compiles it. For
  Java or Kotlin (Maven, Gradle): BiteClaimTest.java or BiteClaimTest.kt with a class named BiteClaimTest, in the
  test folder (src/test/java or src/test/kotlin) of the module whose code it tests, in that code's package.
- Run it: `pytest <your file>` runs only your test if pytest is the runner; for .NET,
  `dotnet test <the test project> --filter "FullyQualifiedName~BiteClaim"`; for Maven, `mvn test -Dtest=BiteClaim*`;
  for Gradle, `gradle test --tests "*BiteClaim*"` (or the project's ./mvnw, ./gradlew); `bite-test` runs the whole suite. If it fails, read the failure and make sure the TEST is right (right import, right API, right
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
    if MAVEN.search(cmd) or GRADLE.search(cmd):  # they take a class name, not a file: pick the claim's class by name
        return jvm_claim_command(cmd, rel, Path(cfg.project))
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


def jvm_claim_command(cmd: str, rel: str, folder: Path) -> str:
    """Maven and Gradle run one test class by name, inside the module or project the file belongs to: in a build of
    many modules, a filter that matches nothing elsewhere would stop the run."""
    if MAVEN.search(cmd):
        cmd = re.sub(r'\s-Dtest=("[^"]*"|\S+)', "", cmd)
        mod = build_folder(folder, rel, ("pom.xml",))
        cmd = re.sub(r"\s(?:-pl|--projects)(?:\s+|=)\S+", "", cmd)
        where = f" -pl {mod} -am" if mod else ""
        # -am also builds the modules it needs, which don't have the claim's class: they mustn't stop the run.
        return f"{cmd}{where} -Dtest=BiteClaim* -Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false"
    cmd = re.sub(r'\s--tests(?:\s+|=)("[^"]*"|\S+)', "", cmd)
    names = ("build.gradle", "build.gradle.kts")
    mod = build_folder(folder, rel, names)
    if mod:  # run that project's own test task: ":lib:test", not every project's "test"
        task = ":" + mod.replace("/", ":") + ":test"
        cmd = re.sub(r"(?<=\s)(?::?[\w:-]*:)?test(?=\s|$)", task, cmd, count=1)
    return f'{cmd} --tests "*BiteClaim*"'


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
    diff = repo.git(root, "diff", "-M", f"{c['sha']}^", c["sha"], "--", *code_paths(c)) or ""
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
  BiteClaimTests.cs with a test class named BiteClaimTests, inside the folder of an existing test project. For
  Java or Kotlin (Maven, Gradle): BiteClaimTest.java or BiteClaimTest.kt with a class named BiteClaimTest, in the
  test folder (src/test/java or src/test/kotlin) of the module whose code it tests, in that code's package.
- Run it: `pytest <your file>` runs only your test if pytest is the runner; for .NET,
  `dotnet test <the test project> --filter "FullyQualifiedName~BiteClaim"`; for Maven, `mvn test -Dtest=BiteClaim*`;
  for Gradle, `gradle test --tests "*BiteClaim*"` (or the project's ./mvnw, ./gradlew); `bite-test` runs the whole suite.
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
    if c.get("part"):
        prompt += f"\n\nThe project's tests already notice the rest of this change. The part no test notices: {c['part']}. Test that part."
    text, _ = asyncio.run(_agent(opts, prompt))
    return last_json(text)


def try_guard(root: Path, c: dict, cfg, budget: float) -> dict:
    """A worker writes the missing test; Bite keeps it only if it passes twice with the change in, fails with the
    change taken out (a real failure, not a test that can't load), and a second fresh check calls it fair."""
    res = {"sha": c["sha"], "status": "no test written"}
    diff = repo.git(root, "diff", "-M", f"{c['sha']}^", c["sha"], "--", *code_paths(c)) or ""
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
    any test notice? kind is held, gap, odd, back (a later commit undid it), fail, none or skip. newest is the pull request's newest commit: tests
    failing on an older commit are skipped, since they often get fixed later."""
    u, caught = c.get("undo", ""), c.get("caught", "")
    one = caught and " more" not in caught
    if u in ("undone since", "reverted since"):
        import html
        by = c.get("undone_by") or {}
        who = (f"commit `{by['sha'][:8]}` (“{html.escape(by['subject'], quote=False).replace('`', chr(39))}”)"
               if by else "a later commit")
        if u == "reverted since":
            return "skip", "➖ reverted on purpose", f"➖ {who[0].upper() + who[1:]} reverted it on purpose, so Bite didn't check it."
        return ("back", "🔁 UNDONE BY A LATER COMMIT", f"🔁 {'This fix slipped out the back door: ' if ROAST[0] else ''}"
                f"{who[0].upper() + who[1:] if not ROAST[0] else who} put the old code back, so this fix is gone from "
                "today's code. **Next:** if that wasn't on purpose, put the fix back with a test that fails without it.")
    if u.startswith("closed since"):
        return "held", "✅ a later test notices", f"✅ A test added in a later commit notices it now{f' ({caught})' if caught else ''}."
    if u == "guarded (tests use the new code)":
        return "held", "✅ tests crash without it", "✅ Without this change your tests crash, so they'd notice if it went."
    if u.startswith("guarded"):
        return ("held", f"✅ noticed by {caught.replace('`', '') or 'your tests'}",
                f"✅ {(('The test ' if one else 'The tests ') + caught) if caught else 'Your tests'} noticed it was gone. "
                f"If this change breaks later, "
                f"{'that test' if one else 'they'} will warn you.")
    if u == "guard gone since":
        files = ", ".join(f"`{t}`" for t in c.get("gone", [])[:3])
        return ("gap", "⚠️ ITS TEST IS GONE", f"⚠️ A test noticed it when it was made{f' ({caught})' if caught else ''}, "
                f"but {files or 'test files'} {'was' if len(c.get('gone', [])) == 1 else 'were'} deleted later, and with "
                "it taken out of today's code every test still passes. **Next:** put back a test that fails without it.")
    if u == "unguarded: part":
        return ("gap", "⚠️ PART NOT NOTICED", f"⚠️ Your tests noticed part of this change{f' ({caught})' if caught else ''}, "
                f"but not {c.get('part') or 'all of it'}: with only that part taken out, every test still passes. "
                "If it breaks later, nothing warns you. **Next:** add a test that fails without it.")
    flaky = (f"({c['flaky'].replace('`', '')} failed once without it, then passed: it fails now and then, so it can't "
             "be counted on.) ") if c.get("flaky") else ""
    if u.startswith("unguarded"):
        return ("gap", "⚠️ NO TEST NOTICED", "⚠️ " + flaky + ("If this fix wandered off, nothing would notice. A test would. " if ROAST[0] else
                "No test noticed it was gone. If it breaks later, nothing warns you. ")
                + "**Next:** add a test that fails without it.")
    if u == "TEST GUARDS NOTHING":
        mine = ", ".join(f"`{t}`" for t in c.get("test_code", []))
        return ("odd", "⚠️ ITS TESTS DIDN'T NOTICE", f"⚠️ {flaky}{'These' if ROAST[0] else 'This commit added'} tests"
                f"{f' ({mine})' if mine else ''}" + (" are looking the other way. " if ROAST[0] else
                ", but they didn't notice it was gone either, so they check something else. ")
                + "**Next:** make one fail without the change.")
    if u == "tests fail at this commit":
        if c.get("head") and c.get("head_ok"):
            return ("skip", "➖ tests failed here, fixed later", "➖ Your tests failed at this commit and pass on the "
                    f"newest one (`{c['head'][:8]}`), so Bite skipped it.")
        if newest and c["sha"] != newest:
            return ("skip", "➖ tests failed here, skipped", "➖ Your tests failed at this commit, so Bite skipped it "
                    "(a later commit may have fixed them).")
        return ("fail", "❌ tests already fail", "❌ Your tests fail at this commit before Bite takes anything out, so "
                "Bite can't ask its question. **Next:** fix them first. If they pass on your own computer, "
                f"[tell Bite how to run them]({SETUP_LINK}).")
    if u == "no tests ran at this commit":
        return ("none", "⚠️ no tests found", "⚠️ Bite couldn't find any tests to run. **Next:** add one, or "
                f"[point Bite at your tests]({SETUP_LINK}).")
    if u.startswith("not flagged: "):
        return "skip", "➖ skipped: " + u[len("not flagged: "):], "➖ Skipped: " + u[len("not flagged: "):] + "."
    return "skip", "➖ couldn't check: " + u, "➖ Couldn't check: " + u + "."


def bite_proof(kinds: list, tried: list = ()) -> bool:
    """Every change Bite checked had a test that noticed it (skipped ones aside), and no claim tested was false."""
    return "held" in kinds and set(kinds) <= {"held", "skip"} and not any(r.get("status") == "FALSE DONE" for r in tried)


def score(kinds: list) -> tuple[int, int]:
    """The Bite score: of the changes Bite could ask its question about, how many a test noticed. Skipped ones,
    failing tests and "no tests found" don't count either way. (noticed, out of); out of is 0 when none counted."""
    counted = [k for k in kinds if k in ("held", "gap", "odd", "back")]
    return counted.count("held"), len(counted)


def score_color(n: int, total: int) -> str:
    """shields.io colour for a score: green when every change was noticed, then yellow-green, yellow, orange, red."""
    r = n / total if total else 0
    return "brightgreen" if n == total else "yellowgreen" if r >= .75 else "yellow" if r >= .5 else "orange" if r >= .25 else "red"


def score_badge(n: int, total: int) -> str:
    """A README badge with the score, like the Bite-proof one: "Bite score | 7/9 noticed"."""
    from urllib.parse import quote
    msg = quote(f"{n}/{total} noticed", safe="").replace("-", "--")
    return (f"[![Bite score: {n} of {total} changes noticed by a test](https://img.shields.io/badge/Bite%20score-{msg}-"
            f"{score_color(n, total)})](https://github.com/connabyss/bite)")


def write_badge(root: Path, sc: dict | None) -> Path | None:
    """bite_proof/badge.json, in shields.io's endpoint format, so a badge can follow the newest run (README:
    Bite score badge). sc is results()'s "score"; with none (nothing counted), an old badge.json is removed."""
    p = proof_dir(root) / "badge.json"
    if not sc:
        p.unlink(missing_ok=True)
        return None
    n, total = sc["noticed"], sc["out_of"]
    p.write_text(json.dumps({"schemaVersion": 1, "label": "Bite score", "message": f"{n}/{total} noticed",
                             "color": score_color(n, total)}) + "\n", encoding="utf-8")
    return p


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
    if "back" in kinds:
        tiles.insert(3, (kinds.count("back"), "undone by a later commit", "odd"))
    if tried:
        tiles.append((len(false_done), f"false \"done\" of {len(tried)} claims tested", "odd"))
    n, total = score(kinds)
    ring = ""
    if total:  # the score as a ring: the green part is the share of changes a test noticed
        arc = 2 * 3.14159 * 42
        ring = (f'<div class="score {"held" if n == total else "gap"}"><svg viewBox="0 0 100 100" width="104" height="104" role="img" aria-label="Bite score '
                f'{n} of {total}"><circle cx="50" cy="50" r="42" class="track"/><circle cx="50" cy="50" r="42" class="arc" '
                f'stroke-dasharray="{arc * n / total:.1f} {arc:.1f}" transform="rotate(-90 50 50)"/>'
                f'<text x="50" y="49" class="big">{n}/{total}</text><text x="50" y="66" class="small">noticed</text></svg>'
                f'<div><b>Bite score: {n} of {total}</b><br>'
                + ("Every change Bite could check had a test that noticed it." if n == total else
                   f"{total - n} change{'' if total - n == 1 else 's'} could wander off and no test would say a word."
                   if ROAST[0] else f"No test noticed any of the {total} changes Bite could check." if n == 0 else
                   f"A test noticed {n} of the {total} changes Bite could check. The other {total - n} could break "
                   "quietly.")
                + f'<div class="why">README badge: <code>{e(score_badge(n, total))}</code></div></div></div>')
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
.held .dot{{background:var(--held)}} .gap .dot,.none .dot{{background:var(--gap)}} .odd .dot,.fail .dot,.back .dot{{background:var(--odd)}}
.why{{color:var(--mute);font-size:13px}} .proof{{border:1px solid var(--held);border-radius:10px;padding:12px 14px}}
.proof b{{color:var(--held)}} .score{{display:flex;gap:18px;align-items:center;margin:24px 0 0}}
.score .track{{fill:none;stroke:var(--line);stroke-width:10}} .score .arc{{fill:none;stroke:var(--gap);stroke-width:10;stroke-linecap:round}} .score.held .arc{{stroke:var(--held)}}
.score .big{{fill:var(--fg);font:700 22px system-ui,sans-serif;text-anchor:middle}} .score .small{{fill:var(--mute);font:12px system-ui,sans-serif;text-anchor:middle}}
.score code{{word-break:break-all}} footer{{margin-top:32px;color:var(--mute);font-size:13px}}
</style>
<main>
<h1><img src="https://raw.githubusercontent.com/connabyss/bite/main/assets/bite-avatar.png" width="32" height="32" alt="Bite" style="vertical-align: middle; margin-right: 8px;"> Bite report: {e(root.name)}</h1>
<div class="sub">{datetime.now():%Y-%m-%d %H:%M} &middot; did the recent "fixed" commits hold? &middot; {seconds:.0f}s, ${SPENT[0]:.2f}</div>
{ring}
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
              ".rs": "rust", ".go": "go", ".cs": "csharp", ".java": "java", ".kt": "kotlin"}


def write_comment(root: Path, cs: list, none: str = "", error: str = "", newest: str = "", tried: list = ()) -> Path:
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
    line = lambda c, k, w: (f"- {w}" + (why(c) if "tests failed here" in w else "")  # a fail's why is in the heading  # noqa: E731
                            + f"<br><sub>Commit {sha(c)}: “{html.escape(c['subject'], quote=False)}”</sub>")
    lines = ["<!-- bite-check -->"]
    if error:
        lines += ["### ❌ Bite couldn't start", "", html.escape(error, quote=False), "",
                  "**Next:** fix that and push again. Bite checks again on every push."]
    elif "fail" in kinds:
        f = checked[kinds.index("fail")]
        later = f.get("head") and f["head"] != f["sha"]
        lines += ["### ❌ Bite: your tests fail, so it couldn't check this pull request", "",
                  "Your tests fail before Bite takes anything out. Bite's question is \"if a change disappeared, "
                  "would a test notice?\", and it can't ask that while they already fail.", "",
                  f"- **Where:** commit {sha(f)}, "
                  + ("the newest commit that changed code. The commits after it changed no code, and the tests fail "
                     f"on the newest one too ({sha({'sha': f['head']})})." if later else
                     "the newest commit in this pull request.")]
        if f.get("why") or f.get("head_why"):
            lines += ["- **What failed:** `" + html.escape(f.get("head_why") or f["why"], quote=False).replace("`", "'") + "`"]
        lines += ["- **About your changes:** nothing yet. Bite hasn't checked them, so this isn't a verdict on them.", "",
                  "**Next:** run your tests, fix what fails, and push. Bite checks again on every push. If they pass "
                  f"on your own computer, Bite may be running them the wrong way: [tell Bite how to run them]({SETUP_LINK})."]
    elif "back" in kinds:
        back = kinds.count("back")
        lines += [f"### 🔁 Bite: {'a fix' if back == 1 else f'{back} fixes'} came undone", "",
                  f"A later commit put the old code back, so {'the 🔁 fix' if back == 1 else 'each 🔁 fix'} below is gone "
                  "from today's code. If that was on purpose, all good.", "",
                  "**Next:** if it wasn't, put the fix back with a test that fails without it, so it can't slip out again."
                  + (f" Bite also found {len(bad)} change{'' if len(bad) == 1 else 's'} no test noticed (⚠️ below)." if bad else "")]
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
                              if c in wrote else re.sub(r" \*\*Next:\*\* .*$", "", w) if k == "fail" else w)
                         for c, (k, _, w) in zip(checked, said)]  # a fail's next step is in the heading
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
    n, out_of = score(kinds)
    if out_of and not error and "fail" not in kinds and not bite_proof(kinds):
        lines += ["", f"<sub>Bite score for these commits: **{n}/{out_of}** noticed by a test.</sub>"]
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
    write_results(root, cs, none, error, newest, tried)
    return p


# --json: the names in results.json are kept from release to release (a change to them bumps "schema").
RESULT_NAMES = {"held": "noticed", "gap": "no_test_noticed", "odd": "its_tests_didnt_notice", "fail": "tests_fail",
                "none": "no_tests", "skip": "skipped", "back": "undone_later"}


def results(cs: list, none: str = "", error: str = "", newest: str = "", tried: list = ()) -> dict:
    """The run for other programs (bite --json, bite_proof/results.json): the same results as the comment, under
    names that stay the same between releases. The fields are listed in README.md (Results for other tools)."""
    checked = [c for c in cs if c.get("undo")]
    commits = []
    for c in checked:
        kind, label, text = say(c, newest)
        r = {"sha": c["sha"], "subject": c["subject"], "result": RESULT_NAMES[kind],
             "label": label.split(" ", 1)[1] if " " in label else label, "detail": flat(text)[2:].strip()}
        if c.get("why"):
            r["why"] = c["why"]
        if c.get("undone_by"):
            r["undone_by"] = c["undone_by"]
        if (c.get("guard") or {}).get("status") == "WRITTEN":
            r["missing_test"] = {k: c["guard"][k] for k in ("test_file", "run") if c["guard"].get(k)}
        commits.append(r)
    kinds = {r["result"] for r in commits}
    outcome = ("error" if error else "tests_fail" if "tests_fail" in kinds
               else "undone_later" if "undone_later" in kinds
               else "gaps" if kinds & {"no_test_noticed", "its_tests_didnt_notice"}
               else "no_tests" if "no_tests" in kinds and "noticed" not in kinds
               else "noticed" if "noticed" in kinds else "nothing_checked")
    false_done = [{"sha": r["sha"], "subject": r.get("subject", ""), "bug": r.get("bug", ""), "today": r.get("today", "")}
                  for r in tried if r.get("status") == "FALSE DONE"]
    n, total = score([say(c, newest)[0] for c in checked])
    out = {"schema": 1, "bite": _installed_version(), "outcome": outcome, "message": error or none,
           "commits": commits, "false_done": false_done}
    if total and not error:
        out["score"] = {"noticed": n, "out_of": total, "badge": score_badge(n, total)}
    return out


LAST_RESULTS = [None]  # the results.json this run wrote, for --json


def write_results(root: Path, cs: list, none: str = "", error: str = "", newest: str = "", tried: list = ()) -> Path:
    p = proof_dir(root) / "results.json"
    r = results(cs, none, error, newest, tried)
    p.write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_badge(root, r.get("score"))
    LAST_RESULTS[0] = p
    return p


def undo_steps(root: Path, sha: str, files: list, moved: dict | None = None) -> list:
    """The commands that take a commit's code change back out: restore the files it edited, delete the ones it
    created. `git checkout <sha>^ -- <file>` fails for a file the commit added, so it can't carry those. A file it
    moved gets its old content under its new name."""
    restored, created, steps = [], [], []
    for rel in files:
        if (moved or {}).get(rel):
            steps.append(f"git show {sha}^:{moved[rel]} > {rel}")
            continue
        target = restored if repo.git(root, "cat-file", "blob", f"{sha}^:{rel}", raw=True) is not None else created
        target.append(rel)
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
        steps = undo_steps(root, sha, c["code"], c.get("moved"))
        if c.get("part_undo"):  # only the piece no test noticed: its file with just that piece taken out
            steps = []
            for rel, data in c["part_undo"].items():
                if data is None:
                    steps.append(f"rm -f {rel}")
                    continue
                keep = proof_dir(root) / f"{sha[:8]}_part_{Path(rel).name}"
                keep.write_bytes(data)
                steps.append(f"cp {keep.as_posix()} {rel}")
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

# bite --demo comeback: the same shop, then a later "simplify" commit quietly puts the old total() back. The comeback
# alarm notices the rounding fix is gone and names the commit that undid it.
COMEBACK_STEPS = DEMO_STEPS + [
    ("Simplify total()", {
        "shop.py": "def discount(price, percent):\n    return max(0, price - price * percent / 100)\n\n\n"
                   "def total(prices):\n    return sum(prices)\n"}),
]


def make_demo(dest: Path, steps: list = DEMO_STEPS) -> Path:
    """The demo project, built in dest as a git repo with one commit per entry of steps (DEMO_STEPS or COMEBACK_STEPS)."""
    dest.mkdir(parents=True, exist_ok=True)
    git = ["git", "-c", "user.name=Bite demo", "-c", "user.email=demo@example.invalid", "-c", "commit.gpgsign=false"]
    # Fixed dates, so every run makes the same commits (and the same short shas as the README shows).
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T12:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T12:00:00Z"}
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True, capture_output=True)
    for subject, files in steps:
        for name, text in files.items():
            (dest / name).write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([*git, "add", "-A"], cwd=dest, check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "-m", subject], cwd=dest, check=True, capture_output=True, env=env)
    # The tests run with the Python Bite runs on, so the demo needs nothing else installed. Left out of the
    # commits: its path differs on every machine.
    (dest / ".bite.ini").write_text(f'[bite]\ntest_command = "{sys.executable}" -m unittest\n', encoding="utf-8")
    (dest / ".git" / "info" / "exclude").write_text(".bite.ini\n", encoding="utf-8")
    return dest


def demo(argv: list) -> int:
    comeback = "comeback" in argv
    dest = make_demo(Path(tempfile.mkdtemp(prefix="bite_demo_")) / "tiny-shop", COMEBACK_STEPS if comeback else DEMO_STEPS)
    if comeback:
        print(f"Bite demo, the comeback alarm: a made-up project in {dest}\n"
              "Two of its commits fixed something. Then a later commit, \"Simplify total()\", quietly put the old\n"
              "code back for one of them. Bite looks for fixes that are gone from today's code, and names who undid them.\n",
              flush=True)
    else:
        print(f"Bite demo: a made-up project in {dest}\n"
              "Two of its commits say they fixed something. One added a test for its fix, the other didn't.\n"
              "Bite takes each fix back out and runs the tests, to see whether any test notices it's gone.\n", flush=True)
    here = os.getcwd()
    os.chdir(dest)
    try:
        rc = main(["--free", *(a for a in argv if a not in ("--demo", "--free", "comeback"))])
    finally:
        os.chdir(here)
    print("\nThat was the demo; nothing of yours was touched. To check your own project: go into it and run bite --free")
    return rc


# Every option main() accepts; each one must be in the help text above (the self-test checks).
FLAGS = {"--free", "--all", "--any", "--serious", "--again", "--roast", "--demo", "--write-tests", "--json", "--quick"}
VALUED = {"--last": int, "--free-checks": int, "--suspects": int, "--budget": float, "--since": str, "--part-runs": int}


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
    kit = bite.settings_section(cp)
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


UPDATE_LINE = 'pipx install --force bite-check --pip-args="--no-cache-dir"'


def latest_version(timeout=3):
    """The newest bite-check on PyPI, or None when it can't be told (offline, slow, or an odd answer). Only
    bite --version asks, so a check never waits on the network."""
    try:
        import urllib.request
        with urllib.request.urlopen("https://pypi.org/pypi/bite-check/json", timeout=timeout) as r:
            return str(json.load(r)["info"]["version"])
    except Exception:
        return None


def _newer(latest, current):
    """True when the version latest is newer than current (plain numbers like 0.10.0; 0.10.0 is newer than 0.9.0)."""
    try:
        return tuple(map(int, latest.split("."))) > tuple(map(int, current.split(".")))
    except (AttributeError, ValueError):
        return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--json" in argv and argv[:1] not in (["live"], ["ask"], ["mcp"]) and not {"-h", "--help", "--version"} & set(argv):
        # Only the results go to stdout, so a program can read them; what Bite says along the way goes to stderr.
        import contextlib
        out, argv = sys.stdout, [a for a in argv if a != "--json"]
        LAST_RESULTS[0] = None
        with contextlib.redirect_stdout(sys.stderr):
            rc = main(argv)
        if LAST_RESULTS[0]:
            out.write(LAST_RESULTS[0].read_text(encoding="utf-8"))
        else:
            out.write(json.dumps({"schema": 1, "bite": _installed_version(), "outcome": "error",
                                  "message": "Bite stopped before it had results (see above).", "commits": [],
                                  "false_done": []}) + "\n")
        return rc
    if argv[:1] == ["live"]:  # the live check for coding AIs (live.py): bite live, bite live --hook
        import live
        return live.main(argv[1:])
    if argv[:1] == ["ask"]:  # a question in plain words: "is last week's login fix guarded?" (ask.py)
        import ask
        return ask.main(argv[1:])
    if argv[:1] == ["mcp"]:  # the same check as a tool any coding AI can call (bite_mcp.py)
        import bite_mcp
        return bite_mcp.main(argv[1:])
    if "--version" in argv:
        current = _installed_version()
        print(f"bite {current}")
        latest = latest_version()
        if _newer(latest, current):
            print(f"Bite {latest} is out. To update, paste this line:\n  {UPDATE_LINE}\n"
                  "(pip users: python -m pip install --upgrade --no-cache-dir bite-check)")
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
        elif argv[i] in FLAGS or (argv[i] == "comeback" and i and argv[i - 1] == "--demo"):
            i += 1
        else:
            print(f"Bite: unknown option {argv[i]!r}. Run bite --help for the options.")
            return 2
    opt = lambda k, d: type(d)(argv[argv.index(k) + 1]) if k in argv else d  # noqa: E731
    ROAST[0] = "--roast" in argv
    QUICK[0] = "--quick" in argv
    PART_RUNS[0] = opt("--part-runs", 6)
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
        cfg.programs = sorted({first, "python", "python3", "pytest", "node", "npx", "go", "cargo", "dotnet",
                               "mvn", "mvnw", "mvnw.cmd", "gradle", "gradlew", "gradlew.bat"} - {"npx", "sh"})
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
    top = cs[0]["sha"] if cs else ""  # the newest commit of all, even one that changed no code
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
    print(f"  free check of {len(free)}: each runs the tests with and without the change", flush=True)
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
    last = next((c for c in free if c["sha"] == newest and c["undo"] == "tests fail at this commit"), None)
    if last and top and top != newest:  # later commits changed no code, but one may have fixed the tests
        last["head"] = top
        last["head_ok"], last["head_why"] = tests_pass_at(root, top, cfg)
        print(f"  the tests {'pass' if last['head_ok'] else 'fail too'} on the newest commit, {top[:8]}, which changed no code",
              flush=True)
    unsplit = [c for c in free if c.get("parts_skipped")]
    if unsplit:
        print(f"  {len(unsplit)} noticed commit(s) weren't checked piece by piece: that check used its "
              f"{opt('--part-runs', 6)} test runs (--part-runs N allows more).", flush=True)
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
    back = [c for c in cs if c.get("undo") == "undone since"]
    for c in back + flagged:
        print(f"{say(c)[1]}: {c['sha'][:8]} \"{short(c['subject'])}\": {flat(say(c)[2])[2:].strip()}")
    checked = [c for c in cs if c.get("undo")]
    held = [c for c in checked if c["undo"].startswith(("guarded", "closed since"))]
    print(f"\nChecked {len(checked)} commit(s): a test noticed {len(held)}, no test noticed {len(flagged)}, "
          + (f"undone by a later commit {len(back)}, " if back else "")
          + f"{len(checked) - len(held) - len(flagged) - len(back)} couldn't be checked or skipped"
          + (f"; {n_out} outside the tests' reach" if n_out else "")
          + (f"; {len(other)} in code your tests can't run" if other else "") + ".")
    n, total = score([say(c)[0] for c in checked])
    if total:
        print(f"Bite score: {n}/{total} (a test noticed {n} of the {total} changes Bite could check)."
              + (f"\nScore badge for your README: {score_badge(n, total)}" if n < total else ""))
    if bite_proof([say(c)[0] for c in checked], tried):
        print(f"\nBite-proof. Nice work. Every change Bite checked had a test that noticed it.\n"
              f"Badge for your README: {BADGE}")
    if flagged:
        print(f"Each change no test noticed, with a check you can rerun and a note for your coding AI: {write_free(root, cfg, flagged)}")
    print(f"\n{time.time() - t0:.0f}s, ${SPENT[0]:.2f}")
    save_log(root, tried, cs)
    save_missing_tests(root, flagged)
    write_comment(root, cs, newest=newest, tried=tried)
    print(f"One-page report (open it in your browser): {write_html(root, cs, tried, time.time() - t0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
