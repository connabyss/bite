"""Rust keeps a file's unit tests in the same file (#[cfg(test)] mod tests { ... }). Taking a commit's change out
must leave the tests it added there, as it does for a separate test file. Before this, a Rust fix tested that way
always read as "no test noticed" (found by the overnight stress test, 2026-11-01)."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent  # noqa: E402

OLD = """pub fn total(p: &[f64]) -> f64 {
    p.iter().sum()
}

#[cfg(test)]
mod tests {
    #[test]
    fn empty() {
        assert_eq!(super::total(&[]), 0.0);
    }
}
"""
NEW = OLD.replace("    p.iter().sum()\n", "    (p.iter().sum::<f64>() * 100.0).round() / 100.0\n").replace(
    "    #[test]\n    fn empty", "    #[test]\n    fn rounds() {\n        assert_eq!(super::total(&[0.1, 0.2]), 0.3);\n"
    "    }\n\n    #[test]\n    fn empty")


def test_the_test_module_is_found():
    lines = NEW.splitlines(keepends=True)
    (start, end), = recent.rust_test_spans(lines)
    assert lines[start].strip() == "#[cfg(test)]" and lines[end].strip() == "}" and end == len(lines) - 1
    assert recent.rust_test_spans(['let s = "#[cfg(test)]";\n']) == []
    braces = '#[cfg(test)]\nmod tests {\n    fn f() { let s = "}"; }\n}\nfn after() {}\n'.splitlines(keepends=True)
    assert recent.rust_test_spans(braces) == [(0, 3)]


def test_taking_the_change_out_keeps_its_tests():
    kept = recent.keep_rust_tests(OLD.encode(), NEW.encode()).decode()
    assert "p.iter().sum()\n" in kept and "round()" not in kept  # the code is the old code
    assert "fn rounds()" in kept and "fn empty()" in kept  # the commit's tests are still there
    assert recent.keep_rust_tests(OLD.encode(), OLD.encode()) == OLD.encode()


def test_a_change_to_the_tests_only_is_not_a_piece_of_code():
    assert recent.rust_code_same(OLD.encode(), OLD.replace("0.0);", "0.0, \"empty\");").encode())
    assert not recent.rust_code_same(OLD.encode(), NEW.encode())


def sh(root, *a):
    subprocess.run(a, cwd=root, check=True, capture_output=True)


def project(tmp: Path) -> Path:
    root = tmp / "demo"
    (root / "src").mkdir(parents=True)
    sh(root, "git", "init", "-q")
    (root / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n')
    (root / ".gitignore").write_text("target\n")
    (root / ".bite.ini").write_text("[bite]\ntest_command = cargo test\n")
    (root / "src" / "lib.rs").write_text(OLD)
    sh(root, "git", "add", "-A")
    sh(root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
    return root


def commit_new(root: Path, text: str, msg: str) -> dict:
    (root / "src" / "lib.rs").write_text(text)
    sh(root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", msg)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    cfg = recent.repo.load_cfg(root)
    c = {"sha": sha, "subject": msg, "body": ""}
    recent.files_of(root, c, cfg)
    return c, cfg


def test_a_commit_that_only_adds_unit_tests_has_no_code(tmp_path):
    root = project(tmp_path)
    c, _ = commit_new(root, OLD.replace("    #[test]\n    fn empty", "    #[test]\n    fn one() {\n"
                                        "        assert_eq!(super::total(&[1.0]), 1.0);\n    }\n\n    #[test]\n    fn empty"),
                      "Add a test for total")
    assert c["code"] == [] and c["test_code"] == ["src/lib.rs"]


def test_a_fix_with_its_unit_test_has_code_and_tests(tmp_path):
    root = project(tmp_path)
    c, _ = commit_new(root, NEW, "Fix total rounding")
    assert c["code"] == ["src/lib.rs"] and c["test_code"] == ["src/lib.rs"]
    assert all("rounds" not in p[1] for p in recent.parts(root, c))  # the test isn't a piece of the change


@pytest.mark.skipif(not shutil.which("cargo"), reason="needs cargo")
def test_a_fix_its_own_unit_test_notices_is_noticed(tmp_path):
    root = project(tmp_path)
    c, cfg = commit_new(root, NEW, "Fix total rounding")
    recent.extras(root, cfg)
    assert recent.undo_check(root, c, cfg) == "guarded"
    assert "rounds" in c["caught"]
