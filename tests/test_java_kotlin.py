"""Java and Kotlin: Bite finds Maven and Gradle builds, reads what their test runs print (how many tests ran, which
failed, a compile error that isn't a finding) and runs one claim test by its class name, inside its own module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bite  # noqa: E402
import recent  # noqa: E402
import repo  # noqa: E402


def build(tmp_path, *files):
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("")
    return tmp_path


@pytest.mark.parametrize("files, unix, windows", [
    (["pom.xml"], "mvn -B test", "mvn -B test"),
    (["pom.xml", "mvnw", "mvnw.cmd"], "sh mvnw -B test", "mvnw.cmd -B test"),
    (["build.gradle.kts", "settings.gradle.kts"], "gradle test", "gradle test"),
    (["build.gradle", "gradlew", "gradlew.bat"], "sh gradlew test", "gradlew.bat test"),
    (["settings.gradle", "gradlew", "lib/build.gradle"], "sh gradlew test", "gradlew.bat test"),
    (["pom.xml", "build.gradle", "gradlew"], "sh gradlew test", "gradlew.bat test"),  # both: the wrapper's build
])
def test_guesses_maven_and_gradle(tmp_path, monkeypatch, files, unix, windows):
    build(tmp_path, *files)
    for win, want in ((False, unix), (True, windows)):
        monkeypatch.setattr(bite, "WINDOWS", win)
        assert bite.guess_test_command(tmp_path) == want


@pytest.mark.parametrize("cmd", ["mvn -B test", "sh mvnw -B test", "./mvnw test", "mvnw.cmd -B test", "gradle test",
                                 "sh gradlew test", "./gradlew :core:test", "gradlew.bat test"])
def test_maven_and_gradle_run_java_and_kotlin(cmd):
    lang, sufs = repo.runs_language(cmd)
    assert lang == "Java or Kotlin" and {".java", ".kt"} <= sufs and ".py" not in sufs


class Globs:
    test_glob = bite.DEFAULT_TEST_FILES


@pytest.mark.parametrize("rel, is_test", [
    ("src/test/java/org/x/ParserTest.java", True),
    ("core/src/test/kotlin/org/x/Parser.kt", True),  # a helper in the test folder
    ("lib/src/jvmTest/kotlin/x/ParserTests.kt", True),
    ("src/integrationTest/java/x/Db.java", True),
    ("src/main/java/org/x/Parser.java", False),
    ("src/main/kotlin/org/x/Parser.kt", False),
])
def test_java_and_kotlin_test_files(rel, is_test):
    assert bite.is_test_file(rel, Globs) is is_test


MAVEN_RUN = """[INFO] Tests run: 21, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.075 s -- in org.json.junit.CDLTest
[WARNING] Tests run: 168, Failures: 0, Errors: 0, Skipped: 1, Time elapsed: 0.878 s -- in org.json.junit.JSONObjectTest
[INFO]
[INFO] Results:
[INFO]
[WARNING] Tests run: 189, Failures: 0, Errors: 0, Skipped: 1
[INFO]
[INFO] Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
"""


def test_counts_maven_tests_from_each_modules_summary():
    assert bite.auto_count(MAVEN_RUN) == 193  # 189 + 4, not the per-class lines again


def test_names_the_failing_maven_and_gradle_tests():
    surefire3 = ("[ERROR] Tests run: 3, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.1 s <<< FAILURE! -- in calc.CalcTest\n"
                 "[ERROR] calc.CalcTest.addsTwo -- Time elapsed: 0.02 s <<< FAILURE!\n")
    surefire2 = "[ERROR] addsTwo(calc.CalcTest)  Time elapsed: 0.02 s  <<< FAILURE!\n"
    gradle = ("> Task :lib:test FAILED\n\ncalc.CalcTest > adds two numbers() FAILED\n"
              "    org.opentest4j.AssertionFailedError at CalcTest.kt:4\n")
    assert recent.caught_by(surefire3) == "`CalcTest.addsTwo`"
    assert recent.caught_by(surefire2) == "`addsTwo`"
    assert recent.caught_by(gradle) == "`CalcTest > adds two numbers()`"


def test_compile_errors_are_load_failures_not_findings():
    javac = ("[ERROR] COMPILATION ERROR :\n[ERROR] /work/src/test/java/calc/CalcTest.java:[5,40] cannot find symbol\n"
             "[INFO] BUILD FAILURE\n")
    kotlinc = "e: file:///work/lib/src/test/kotlin/calc/CalcTest.kt:4:43 Unresolved reference 'clamp'.\nBUILD FAILED in 2s\n"
    gradle_java = "> Task :compileTestJava FAILED\nCalcTest.java:5: error: cannot find symbol\nCompilation failed; see the compiler error output for details.\n"
    for out in (javac, kotlinc, gradle_java):
        assert bite.load_failure(out), out
    # A test that ran and failed is a finding, even with "Compilation" somewhere else in the output.
    failed = ("calc.CalcTest > adds two numbers() FAILED\n    org.opentest4j.AssertionFailedError at CalcTest.kt:4\n"
              "warning: Compilation failed earlier in an unrelated module\n")
    assert not bite.load_failure(failed)
    assert not bite.load_failure("[ERROR] calc.CalcTest.addsTwo -- Time elapsed: 0.02 s <<< FAILURE!\n"
                                 "[ERROR] cannot find symbol in a message the test printed\n")


class Cfg:
    claim_cmd, contain, box_test_cmd = "", "", ""


def claim(tmp_path, test_cmd, rel):
    Cfg.test_cmd, Cfg.project = test_cmd, tmp_path
    return recent.claim_command(Cfg, rel)


def test_maven_claim_runs_the_claim_class_by_name(tmp_path):
    build(tmp_path, "pom.xml")
    assert claim(tmp_path, "mvn -B test -Dtest=Slow*", "src/test/java/calc/BiteClaimTest.java") == \
        "mvn -B test -Dtest=BiteClaim* -Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false"


def test_maven_claim_runs_in_its_own_module(tmp_path):
    build(tmp_path, "pom.xml", "core/pom.xml", "core/src/test/java/x/A.java")
    assert claim(tmp_path, "sh mvnw -B test", "core/src/test/java/x/BiteClaimTest.java") == \
        "sh mvnw -B test -pl core -am -Dtest=BiteClaim* -Dsurefire.failIfNoSpecifiedTests=false -DfailIfNoTests=false"


def test_gradle_claim_runs_its_own_projects_test_task(tmp_path):
    build(tmp_path, "settings.gradle.kts", "lib/build.gradle.kts", "app/feature/build.gradle")
    assert claim(tmp_path, "sh gradlew test", "lib/src/test/kotlin/calc/BiteClaimTest.kt") == \
        'sh gradlew :lib:test --tests "*BiteClaim*"'
    assert claim(tmp_path, "gradle test --tests Slow", "app/feature/src/test/java/BiteClaimTest.java") == \
        'gradle :app:feature:test --tests "*BiteClaim*"'
    assert claim(tmp_path, "gradle test", "src/test/java/BiteClaimTest.java") == 'gradle test --tests "*BiteClaim*"'


def test_a_claim_run_that_ran_no_test_is_not_a_pass():
    assert recent.ran_nothing("mvn -B test -Dtest=BiteClaim*", "[INFO] No tests to run.\n[INFO] BUILD SUCCESS\n")
    assert not recent.ran_nothing("mvn -B test", MAVEN_RUN)
    assert recent.ran_nothing('gradle :lib:test --tests "*BiteClaim*"',
                              "> No tests found for given includes: [*BiteClaim*](--tests filter)\n")


def test_preflight_asks_for_java_when_maven_cant_find_it(tmp_path, monkeypatch):
    class P:
        contain, free_cmd, test_cmd, project = "", "", "mvn -B test", tmp_path
    monkeypatch.setattr(recent.shutil, "which", lambda name: None if name == "java" else "/usr/bin/" + name)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    assert "Install a JDK" in recent.preflight(P)
    P.test_cmd = "sh gradlew test"  # the project's own wrapper still needs Java
    (tmp_path / "gradlew").write_text("")
    assert "Install a JDK" in recent.preflight(P)
