"""Shared helpers for recent.py: git, finding the repo, and reading the settings file (.bite.ini)."""

import configparser
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bite  # noqa: E402

CODE_SUFFIXES = {".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".go", ".rs", ".rb",
                 ".java", ".kt", ".kts", ".scala", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".cs", ".fs",
                 ".php", ".swift", ".m", ".mm", ".gd", ".lua", ".ex", ".exs", ".erl", ".clj", ".dart", ".vue",
                 ".svelte", ".r", ".jl", ".zig", ".nim", ".ml", ".hs", ".pl", ".pm"}
# What each kind of test runner can exercise. A runner only notices changes in its own language: pytest can't
# notice a TypeScript change going, so taking one out and seeing pytest pass says nothing about it.
RUNNERS = [("Python", {"pytest", "py.test", "python", "python3", "py", "tox", "nox", "unittest", "hatch"},
            {".py", ".pyw", ".pyx", ".pxd"}),
           ("JavaScript or TypeScript", {"npm", "npx", "yarn", "pnpm", "node", "bun", "deno", "jest", "vitest", "mocha",
                                         "tape", "tap", "ava", "uvu", "jasmine", "nyc", "c8"},
            {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".vue", ".svelte"}),
           ("Rust", {"cargo"}, {".rs"}),
           ("Go", {"go"}, {".go"}),
           (".NET", {"dotnet"}, {".cs", ".fs"}),
           ("Java or Kotlin", {"mvn", "mvnw", "gradle", "gradlew"}, {".java", ".kt"})]
COPY_IGNORE = [".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".nox", ".mypy_cache",
               ".pytest_cache", ".ruff_cache", ".hypothesis", ".gradle", ".kotlin"]
class ConfigError(Exception):
    pass


# ---- git -----------------------------------------------------------------------

SHA = re.compile(r"\b[0-9a-f]{40}\b")
# What git says about fixed commits never changes: the same question asked again in one run (Bite asked for the same
# file of the same commit up to 7 times) gets the first answer, without starting git again. Only questions that name
# commits by their full id and nothing that moves (HEAD, a branch, the working tree) are kept.
FIXED = {"cat-file", "show", "diff-tree", "ls-tree", "diff"}
_ASKED: dict = {}


def fixed(args) -> bool:
    if not args or args[0] not in FIXED or any("HEAD" in a or ".." in a for a in args):  # a range may end at a branch
        return False
    revs = [a for a in args[1:args.index("--") if "--" in args else len(args)]
            if not a.startswith("-") and a not in ("blob", "tree", "commit")]
    if args[0] == "diff":  # a diff of one commit against the working tree changes as the files do
        return len(revs) == 2 and all(SHA.match(r) for r in revs)
    return bool(revs) and all(SHA.match(r) for r in revs)


def git(root, *args, raw=False):
    key = (str(root), args) if fixed(args) else None
    if key in _ASKED:
        r = _ASKED[key]
    else:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True)
        if key and r.returncode == 0:  # an error (a file locked for a moment) is asked again next time
            _ASKED[key] = r
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.decode("utf-8", "replace").strip()


SHALLOW = ("This is a shallow clone (git clone --depth): it holds only the newest commits, and the oldest of them "
           "has no parent here, so Bite can't see what it changed. Get the whole history with: git fetch --unshallow")


def shallow(root: Path) -> bool:
    """The repository is a shallow clone: its oldest commit's parent wasn't downloaded."""
    return (git(root, "rev-parse", "--is-shallow-repository") or "") == "true"


# ---- a project on the web --------------------------------------------------------
# `bite --free https://github.com/pallets/click` checks a project without cloning it by hand first: Bite clones it
# into a folder of its own (kept, so a second run only downloads what's new) and checks that.

HOSTS = ("github.com", "gitlab.com", "codeberg.org", "bitbucket.org")


def remote_url(arg: str) -> str | None:
    """The address to clone when arg is a link to a project on the web, else None. Takes a project's page as copied
    from the browser (https://github.com/owner/name, also with /tree/main/... after it or without the https://), a
    clone address ending in .git, or git@host:owner/name.git."""
    arg = arg.strip().strip("\"'")
    if re.fullmatch(r"git@[\w.-]+:[\w./-]+", arg):
        return arg
    m = re.fullmatch(r"(?:https?://)?(?:www\.)?([\w.-]+)/(.+?)/?", arg)
    if not m:
        return None
    host, path = m[1].lower(), m[2]
    if host in HOSTS:
        parts = path.split("/-/")[0].split("/") if host == "gitlab.com" else path.split("/")[:2]
        parts = [p for p in parts if p]
        if len(parts) < 2 or not all(re.fullmatch(r"[\w.-]+", p) for p in parts):
            return None
        parts[-1] = parts[-1].removesuffix(".git")
        return f"https://{host}/{'/'.join(parts)}.git"
    if arg.startswith(("https://", "http://")) and path.endswith(".git"):
        return arg
    return None


def clone_folder(url: str) -> Path:
    """Where Bite keeps its clone of url: one folder per project, under the computer's temporary folder."""
    import tempfile
    name = re.sub(r"\.git$", "", re.sub(r"^(?:https?://|git@)", "", url))
    name = re.sub(r"[^\w.-]+", "-", name).strip("-.")[:80] or "project"
    return Path(tempfile.gettempdir()) / "bite-projects" / name


def clone(url: str, into: Path | None = None) -> tuple[Path | None, str]:
    """Clone url (or update an earlier clone of it) for Bite to check. Returns the folder, and "" or what went
    wrong. Only the history comes down at first (--filter=blob:none); git fetches the files of the commits Bite
    looks at as it needs them, so a big project starts quickly."""
    into = into or clone_folder(url)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # a private project fails at once instead of waiting for a password
    if (into / ".git").is_dir():
        r = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=into, capture_output=True, text=True, env=env)
        return into, "" if r.returncode == 0 else "couldn't download what's new, so Bite checks the copy it has"
    into.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", url, str(into)], capture_output=True,
                       text=True, env=env)
    if r.returncode != 0:
        why = (r.stderr.strip().splitlines() or ["git clone failed"])[-1]
        return None, f"couldn't download {url} ({why}). Check the link, and that the project is public."
    return into, ""


def repo_root(start) -> Path | None:
    """The top folder of the git repository start is in; None when it isn't in one, or isn't a folder at all."""
    if not isinstance(start, (str, os.PathLike)) or not Path(start).is_dir():
        return None
    top = git(start, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def state_dir(root: Path) -> Path:
    d = Path(git(root, "rev-parse", "--absolute-git-dir") or root / ".git") / "bite"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cfg(root: Path):
    ini = Path(os.environ["BITE_CONFIG"]) if os.environ.get("BITE_CONFIG") else root / ".bite.ini"
    # utf-8-sig: Windows Notepad starts a UTF-8 file with an invisible mark (a BOM), which would hide the [bite] line.
    if ini.is_file() and not re.search(r"(?m)^\s*\[(?:bite|kit)\]\s*$", ini.read_text(encoding="utf-8-sig", errors="replace")):
        raise ConfigError(f"{ini.name} has no [bite] section, so none of its settings are read. "
                          "Put [bite] on the first line.")
    if not ini.is_file():
        ini = state_dir(root) / "auto.ini"
        ini.write_text("[bite]\n"
                       f"project_folder = {root}\n"
                       f"test_command = {bite.guess_test_command(root)}\n"
                       f"bite_copy_ignore = {', '.join(COPY_IGNORE)}\n"
                       "planted_bugs = 4\nplanted_bugs_seconds = 120\ntest_timeout_seconds = 300\n", encoding="utf-8")
    try:
        cfg = bite.Config(ini)
    except configparser.Error as e:  # a setting written twice, a line that isn't "name = value"
        why = (f"{e.option} is set twice (line {e.lineno})" if isinstance(e, configparser.DuplicateOptionError) else
               f"[{e.section}] is there twice" if isinstance(e, configparser.DuplicateSectionError) else
               "a line isn't in the form name = value" if isinstance(e, configparser.ParsingError) else
               type(e).__name__)
        raise ConfigError(f"Bite can't read {ini.name}: {why}. Fix that line and run Bite again.") from None
    except ValueError as e:  # a number setting that isn't a number
        raise ConfigError(f"Bite can't read {ini.name}: a setting that needs a number has {str(e).split(': ', 1)[-1]}. "
                          "Fix it, or take that line out to use the default.") from None
    if cfg.test_timeout <= 0:
        raise ConfigError(f"In {ini.name}, test_timeout_seconds needs a number of seconds above 0 (it's "
                          f"{cfg.test_timeout}): with it, every test run would stop before it starts.")
    if cfg.contain and "{cmd}" not in cfg.contain:
        raise ConfigError(f"In {ini.name}, contain_command needs {{cmd}} where the test command goes. Without it the "
                          "tests never run in the box, and every change would look unnoticed.")
    cfg.project = root
    for name in COPY_IGNORE:
        if name not in cfg.copy_ignore:
            cfg.copy_ignore.append(name)
    # Copies of a JavaScript project used to be made inside its node_modules/, so Node found the packages above
    # them. But tools that skip anything under node_modules (jest, @babel/register, tap) then skipped the copy too
    # (validator.js: every commit "tests already fail"), and git apply in the copy saw the project's own git folder
    # (dotenv). Now each copy sits outside the project, with a link to its node_modules: see link_node_modules.
    return cfg


def link_node_modules(root: Path, dest: Path) -> int:
    """Give a copy (dest) of the project the project's installed packages: a link at each node_modules the project
    has (its top folder, or a workspace package's folder up to two deep) to the real one. Nothing is copied, and
    the real folders are never written through by Bite (removing the copy removes only the link). Returns how many
    links were made."""
    made = 0
    for pattern in ("node_modules", "*/node_modules", "*/*/node_modules"):
        for src in sorted(root.glob(pattern)):
            rel = src.relative_to(root)
            if not src.is_dir() or src.is_symlink() or any(p in (".git", "node_modules") for p in rel.parts[:-1]):
                continue
            target = dest / rel
            if not target.parent.is_dir() or os.path.lexists(target):
                continue
            if make_link(src.resolve(), target):
                made += 1
    return made


def make_link(src: Path, target: Path) -> bool:
    """A folder link at target pointing to src: a symlink, or on Windows without the right to make one, a
    junction (any user can make those). False when neither works."""
    try:
        os.symlink(src, target, target_is_directory=True)
        return True
    except OSError:
        pass
    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(str(src), str(target))
            return True
        except OSError:
            pass
    return False


def is_setup(rel: str, cfg) -> bool:
    import fnmatch
    name = rel.rsplit("/", 1)[-1]
    return name in cfg.test_cmd or any(fnmatch.fnmatch(rel.lower(), g.lower()) or fnmatch.fnmatch(name.lower(), g.lower())
                                       for g in cfg.test_setup)


def runs_language(cmd: str) -> tuple[str, set]:
    """The language a test command runs and its file endings, or ("", set()) when it isn't plainly one runner
    (make, a script, Unity, or a mix): then Bite can't tell, and every code change is checked."""
    words = {re.sub(r"(?i)(\.exe|\.bat|\.cmd|[\d.]+)$", "", w.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower())
             for w in re.split(r"[\s\"'&|;()]+", cmd) if w}
    hits = [(lang, sufs) for lang, names, sufs in RUNNERS if words & names]
    return hits[0] if len(hits) == 1 else ("", set())


# ---- the check -----------------------------------------------------------------

def failure_excerpt(out: str, n: int = 12) -> str:
    """The lines that say what failed (assertion, expected/actual, error), not the stack around them."""
    import re
    lines = out.splitlines()
    hits = [i for i, ln in enumerate(lines) if re.search(r"not ok|FAIL|Error|[Ee]xpected|[Aa]ctual|assert|panicked|!=", ln)]
    if not hits:
        return "\n".join(lines[-n:])
    keep = sorted({j for i in hits for j in (i, i + 1) if j < len(lines)})[:n]
    return "\n".join(lines[j] for j in keep)
