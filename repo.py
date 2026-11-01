"""Shared helpers for recent.py: git, finding the repo, and reading the settings file (.bite.ini)."""

import configparser
import os
import re
import subprocess
import sys
import tempfile
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

def git(root, *args, raw=False):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.decode("utf-8", "replace").strip()


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
    if (root / "node_modules").is_dir():
        # Node looks for node_modules in the folders above a file: a copy made inside node_modules/ finds the
        # project's packages without copying them (node_modules itself is left out of every copy).
        tmp = root / "node_modules" / "bite_tmp"
        tmp.mkdir(exist_ok=True)
        tempfile.tempdir = str(tmp)
    return cfg


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
