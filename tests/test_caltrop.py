import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "caltrop")
SLEEP = "fn t() {\n    std::thread::sleep(d);\n}\n"


def run(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def check(self, **kw):
        return run("check", str(self.repo), **kw)


class CaltropTest(Fixture):
    def test_clean_repo_passes(self):
        self.write("src/lib.rs", "fn f() {}\n")
        self.assertEqual(self.check().returncode, 0)

    def test_hit_without_allowlist_fails(self):
        self.write("tests/a.rs", SLEEP)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/a.rs:2: no-fixed-sleep:", r.stdout)
        self.assertIn("run caltrop baseline to adopt caltrop in this repo", r.stdout)
        self.write("caltrop.toml", "")
        self.assertNotIn("adopt caltrop in this repo", self.check().stdout)

    def test_baseline_then_check_passes(self):
        self.write("tests/a b.rs", SLEEP + SLEEP.replace("t()", "u()"))
        self.write(".config/nextest.toml", "[profile.default]\nretries = 2\n")
        r = run("baseline", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        toml = (self.repo / "caltrop.toml").read_text()
        self.assertIn("[allow.no-fixed-sleep]", toml)
        self.assertIn('"tests/a b.rs" = 2', toml)
        self.assertIn("[allow.no-test-retries]", toml)
        self.assertEqual(self.check().returncode, 0)

    def test_over_allowance_fails(self):
        self.write("tests/a.rs", SLEEP + SLEEP.replace("t()", "u()"))
        self.write("caltrop.toml", '[allow.no-fixed-sleep]\n"tests/a.rs" = 1\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/a.rs:2: no-fixed-sleep:", r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "fix these hits; do not raise counts in caltrop.toml")
        self.assertNotIn("baseline", r.stdout)

    def test_under_allowance_fails(self):
        self.write("tests/a.rs", SLEEP)
        self.write("caltrop.toml", '[allow.no-fixed-sleep]\n"tests/a.rs" = 2\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("lower the allowance for no-fixed-sleep in tests/a.rs to 1", r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "edit caltrop.toml as shown")
        self.assertNotIn("baseline", r.stdout)

    def test_stale_file_fails(self):
        self.write("tests/a.rs", "fn f() {}\n")
        self.write("caltrop.toml", '[allow.no-fixed-sleep]\n"tests/gone.rs" = 1\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/gone.rs", r.stdout)

    def test_unknown_rule_in_allowlist_fails(self):
        self.write("tests/a.rs", "fn f() {}\n")
        self.write("caltrop.toml", '[allow.no-such-rule]\n"tests/a.rs" = 1\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no-such-rule", r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "edit caltrop.toml as shown")

    def test_both_trailers(self):
        self.write("tests/a.rs", SLEEP + SLEEP.replace("t()", "u()"))
        self.write("caltrop.toml", '[allow.no-fixed-sleep]\n"tests/a.rs" = 1\n"tests/gone.rs" = 1\n')
        self.assertEqual(self.check().stdout.splitlines()[-2:],
                         ["fix these hits; do not raise counts in caltrop.toml", "edit caltrop.toml as shown"])

    def test_tests_file_naming(self):
        self.write("src/foo_tests.rs", SLEEP)
        self.write("src/tests.rs", SLEEP)
        r = self.check()
        self.assertIn("src/foo_tests.rs:2: no-fixed-sleep:", r.stdout)
        self.assertIn("src/tests.rs:2: no-fixed-sleep:", r.stdout)

    def test_new_rules_report_and_baseline(self):
        self.write("tests/a.rs", (
            "#[test]\n#[ignore]\nfn t() {\n"
            "    assert!(r.is_err());\n"
            "    if !path.exists() { return; }\n"
            "}\n"
            "impl Runner for FakeRunner {}\n"
        ))
        r = self.check()
        for line in ("tests/a.rs:2: no-ignored-test:", "tests/a.rs:4: no-weak-result-assert:",
                     "tests/a.rs:5: no-silent-skip:", "tests/a.rs:7: no-fake-impls:"):
            self.assertIn(line, r.stdout)
        self.assertNotIn("no-silent-skip-tests-dir", r.stdout)
        self.assertEqual(run("baseline", str(self.repo)).returncode, 0)
        self.assertEqual(self.check().returncode, 0)

    def test_vendor_dir_skipped(self):
        self.write("desktop/vendor/gpui/tests/a.rs", SLEEP)
        self.write("vendor/x/src/lib.rs", "#[cfg(not(test))] fn f() {}\n")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_two_sleeps_one_line(self):
        self.write("tests/a.rs", "fn t() {\n    sleep(a); sleep(b);\n}\n")
        self.assertEqual(self.check().stdout.count("no-fixed-sleep:"), 2)

    def test_nextest_retry_lines_follow_tables(self):
        self.write(".config/nextest.toml",
                   '[profile.default]\nretries = 1\n\n[profile.ci]\nretries = 2\n\n'
                   '[[profile.default.overrides]]\nfilter = "x"\nretries = 0\n')
        r = self.check()
        self.assertEqual(r.stdout.count("no-test-retries:"), 2)
        self.assertIn(".config/nextest.toml:2:", r.stdout)
        self.assertIn(".config/nextest.toml:5:", r.stdout)

    def test_version_warning(self):
        fake = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, fake)
        (fake / "ast-grep").write_text("#!/bin/sh\n[ \"$1\" = --version ] && echo 'ast-grep 0.1.0'\nexit 0\n")
        (fake / "ast-grep").chmod(0o755)
        r = self.check(env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning: expected ast-grep 0.44.1, found ast-grep 0.1.0", r.stderr)

    def test_tests_dir_and_mod_dedupe(self):
        self.write("tests/a.rs", "#[cfg(test)]\nmod m {\n    fn t() {\n        std::thread::sleep(d);\n    }\n}\n")
        r = self.check()
        self.assertEqual(r.stdout.count("no-fixed-sleep:"), 1, r.stdout)
        self.assertNotIn("-tests-dir", r.stdout)

    def test_gitignored_dir_skipped(self):
        self.write(".gitignore", "target/\n")
        self.write("target/tests/x.rs", SLEEP)
        self.assertEqual(self.check().returncode, 0)

    def test_nextest_retries(self):
        self.write(".config/nextest.toml",
                   '[profile.default]\nretries = 2\n\n[[profile.default.overrides]]\n'
                   'filter = "test(x)"\nretries = { backoff = "fixed", count = 1 }\n')
        r = self.check()
        self.assertEqual(r.stdout.count(".config/nextest.toml:"), 2, r.stdout)
        self.assertEqual(r.stdout.count("no-test-retries:"), 2)
        self.assertIn(".config/nextest.toml:2:", r.stdout)
        self.assertIn(".config/nextest.toml:6:", r.stdout)

    def test_pytest_reruns_in_config(self):
        self.write("pyproject.toml", '[tool.pytest.ini_options]\naddopts = "-q --reruns 2"\n')
        self.write("pytest.ini", "[pytest]\nreruns = 1\n")
        self.write("setup.cfg", "[tool:pytest]\naddopts = --reruns=0 --reruns-delay 5\n")
        self.write("backend/pyproject.toml",
                   '[tool.pytest.ini_options]\naddopts = [\n  "-q",\n  "--reruns",\n  "3",\n]\n')
        self.write("tox.ini", "[pytest]\naddopts =\n    -q\n    --reruns\n    2\n")
        r = self.check()
        self.assertIn("pyproject.toml:2: no-test-retries:", r.stdout)
        self.assertIn("pytest.ini:2: no-test-retries:", r.stdout)
        self.assertIn("backend/pyproject.toml:4: no-test-retries:", r.stdout)
        self.assertIn("tox.ini:4: no-test-retries:", r.stdout)
        self.assertNotIn("setup.cfg", r.stdout)

    def test_pytest_reruns_not_in_comments_or_other_tables(self):
        self.write("pyproject.toml", '[tool.pytest.ini_options]\n# addopts = "--reruns 3"\n'
                   'addopts = "-q"\n\n[tool.other]\nreruns = 4\n')
        self.write("node_modules/x/pytest.ini", "[pytest]\nreruns = 1\n")
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_python_and_svelte_share_rule_ids(self):
        self.write("tests/test_a.py", "import time\n\ndef test_x():\n    time.sleep(1)\n")
        self.write("src/A.svelte", '<script>\nif (import.meta.env.MODE === "test") x();\n</script>\n')
        self.write("src/B.svelte", '<script lang="ts">\nif (process.env.VITEST) x();\n</script>\n')
        self.write("src/c.test.ts", "it.skip('x', () => {});\n")
        r = self.check()
        self.assertIn("tests/test_a.py:4: no-fixed-sleep:", r.stdout)
        self.assertIn("src/A.svelte:2: no-test-swap:", r.stdout)
        self.assertIn("src/B.svelte:2: no-test-swap:", r.stdout)
        self.assertIn("src/c.test.ts:1: no-ignored-test:", r.stdout)
        self.assertEqual(run("baseline", str(self.repo)).returncode, 0)
        toml = (self.repo / "caltrop.toml").read_text()
        self.assertNotIn("-py", toml)
        self.assertNotIn("-ts", toml)
        self.assertEqual(self.check().returncode, 0)

    def test_dependency_dirs_skipped(self):
        self.write("node_modules/x/tests/a.rs", SLEEP)
        self.write("venv/lib/python3.12/site-packages/x/tests/a.rs", SLEEP)
        self.assertEqual(self.check().returncode, 0)

    def test_version(self):
        r = run("--version")
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stdout, r"^caltrop \d+\.\d+\.\d+\n$")

    def test_nextest_zero_retries(self):
        self.write(".config/nextest.toml", "[profile.default]\nretries = 0\n")
        self.assertEqual(self.check().returncode, 0)

    def test_other_cwd(self):
        self.write("tests/a.rs", SLEEP)
        inside = run("check", cwd=self.repo)
        outside = run("check", str(self.repo), cwd="/")
        self.assertEqual(inside.returncode, 1)
        self.assertEqual(inside.stdout, outside.stdout)

    def test_missing_ast_grep(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty)
        r = self.check(env={**os.environ, "PATH": empty})
        self.assertEqual(r.returncode, 2)
        self.assertIn("cargo install ast-grep", r.stderr)

    def test_bad_toml(self):
        self.write("caltrop.toml", "[allow\nbroken")
        r = self.check()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_wrong_shape_toml(self):
        for body in ['allow = 3\n', '[allow.no-fixed-sleep]\n"x" = "2"\n',
                     '[allow]\nno-fixed-sleep = 1\n', '[allow.no-fixed-sleep]\n"x" = -1\n']:
            self.write("caltrop.toml", body)
            r = self.check()
            self.assertEqual(r.returncode, 2, body)
            self.assertNotIn("Traceback", r.stderr)

    def test_malformed_ast_grep_output(self):
        for out in ["not json", "{}"]:
            fake = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, fake)
            (fake / "ast-grep").write_text(f"#!/bin/sh\necho '{out}'\n")
            (fake / "ast-grep").chmod(0o755)
            r = self.check(env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"})
            self.assertEqual(r.returncode, 2, out)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
