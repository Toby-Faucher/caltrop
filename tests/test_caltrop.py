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
        self.assertIn("caltrop baseline", r.stdout)

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

    def test_under_allowance_fails(self):
        self.write("tests/a.rs", SLEEP)
        self.write("caltrop.toml", '[allow.no-fixed-sleep]\n"tests/a.rs" = 2\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("lower the allowance for no-fixed-sleep in tests/a.rs to 1", r.stdout)

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


if __name__ == "__main__":
    unittest.main()
