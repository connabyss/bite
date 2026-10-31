"""In Rust an example in a doc comment is a test: cargo test runs it. When a commit adds one, taking the commit's
code back out must keep the example, or Bite says no test noticed a change its own example tests
(seen on tokio-rs/bytes 804ee6d0: try_unsplit made public with an example)."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bite  # noqa: E402
import recent  # noqa: E402

OLD = """pub struct Buf(pub Vec<u8>);

impl Buf {
    /// Joins two buffers.
    fn join(&mut self, other: Buf) {
        self.0.extend(other.0);
    }
}
"""

NEW = """pub struct Buf(pub Vec<u8>);

impl Buf {
    /// Joins two buffers.
    ///
    /// ```
    /// let mut a = demo::Buf(vec![1]);
    /// a.join(demo::Buf(vec![2]));
    /// assert_eq!(a.0, vec![1, 2]);
    /// ```
    pub fn join(&mut self, other: Buf) {
        self.0.extend(other.0);
    }
}
"""


def test_keep_docs_puts_back_the_old_code_under_the_new_example():
    kept = recent.keep_docs(OLD.encode(), NEW.encode()).decode()
    assert "    fn join(&mut self" in kept and "pub fn join" not in kept
    assert kept.index("/// ```") < kept.index("fn join")
    assert kept.count("/// Joins two buffers.") == 1


def test_keep_docs_skips_commits_without_an_example():
    assert recent.keep_docs(OLD.encode(), OLD.replace("fn join", "pub fn join").encode()) is None
    # An example already in the file doesn't count: only one the commit added (indexmap cd4c1a53 added a doc
    # comment with no example to a file full of them).
    old = NEW.replace("pub fn join", "fn join")
    assert recent.keep_docs(old.encode(), old.replace("/// Joins two buffers.", "/// Joins two buffers, in order.")
                            .replace("    fn join", "    pub fn join").encode()) is None


def sh(root, *a):
    subprocess.run(a, cwd=root, check=True, capture_output=True)


@pytest.mark.skipif(not shutil.which("cargo"), reason="needs cargo")
def test_a_doc_example_the_commit_wrote_counts_as_its_test():
    root = Path(tempfile.mkdtemp()) / "demo"
    (root / "src").mkdir(parents=True)
    sh(root, "git", "init", "-q")
    (root / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n')
    (root / ".gitignore").write_text("target\n")
    (root / ".bite.ini").write_text("[kit]\ntest_command = cargo test\nallowed_programs = cargo\n")
    (root / "src" / "lib.rs").write_text(OLD)
    (root / "tests").mkdir()  # another test, so the run with the code taken out still runs something
    (root / "tests" / "basic.rs").write_text("#[test]\nfn new_buf() {\n    assert_eq!(demo::Buf(vec![1]).0.len(), 1);\n}\n")
    sh(root, "git", "add", "-A")
    sh(root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
    (root / "src" / "lib.rs").write_text(NEW)
    sh(root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "Fix: make join public")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    cfg = recent.repo.load_cfg(root)
    recent.extras(root, cfg)
    c = {"sha": sha, "subject": "Fix: make join public", "body": ""}
    recent.files_of(root, c, cfg)
    assert c["code"] == ["src/lib.rs"]
    assert recent.undo_check(root, c, cfg) == "guarded"
    assert "lib.rs - Buf::join" in c["caught"]  # Windows writes src\\lib.rs
