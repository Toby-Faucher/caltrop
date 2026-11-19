import importlib.machinery
import importlib.util
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
        self.write("src/C.svelte", "<p>x</p>\n{#if import.meta.env.MODE === 'test'}<Fake />{/if}\n")
        self.write("src/d.test.tsx", "it.skip('x', () => { render(<App />); });\n")
        self.write("src/e.test.jsx", "it.skip('x', () => { render(<App />); });\n")
        r = self.check()
        self.assertIn("tests/test_a.py:4: no-fixed-sleep:", r.stdout)
        self.assertIn("src/A.svelte:2: no-test-swap:", r.stdout)
        self.assertIn("src/B.svelte:2: no-test-swap:", r.stdout)
        self.assertIn("src/c.test.ts:1: no-ignored-test:", r.stdout)
        self.assertIn("src/C.svelte:2: no-test-swap:", r.stdout)
        self.assertIn("src/d.test.tsx:1: no-ignored-test:", r.stdout)
        self.assertIn("src/e.test.jsx:1: no-ignored-test:", r.stdout)
        self.assertEqual(run("baseline", str(self.repo)).returncode, 0)
        toml = (self.repo / "caltrop.toml").read_text()
        self.assertNotIn("-py", toml)
        self.assertNotIn("-ts", toml)
        self.assertNotIn("-svelte", toml)
        self.assertEqual(self.check().returncode, 0)

    def test_tsx_copies_in_sync(self):
        r = subprocess.run([sys.executable, str(Path(SCRIPT).parent / "scripts/gen-tsx.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

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

    def assert_hits(self, rule, text, hit, miss):
        # Every path gets the same snippet; exactly the `hit` paths should report `rule`.
        for p in hit + miss:
            self.write(p, text)
        out = self.check().stdout
        self.assertEqual({line.split(":")[0] for line in out.splitlines() if f": {rule}:" in line}, set(hit), out)

    def test_rust_test_code_files(self):
        self.assert_hits("no-fixed-sleep", SLEEP,
                         ["tests/a.rs", "crate/tests/b.rs", "src/tests.rs", "src/view_tests.rs"],
                         ["src/lib.rs", "src/tests_util.rs", "src/latests.rs"])
        self.assert_hits("no-test-swap", "#[cfg(not(test))]\nfn f() {}\n",
                         ["src/main.rs"], ["tests/c.rs", "src/x/tests.rs", "src/x/view_tests.rs"])

    def test_python_test_code_files(self):
        self.assert_hits("no-fixed-sleep", "import time\ntime.sleep(1)\n",
                         ["test_a.py", "pkg/a_test.py", "conftest.py", "tests/h.py", "test/h.py", "pkg/tests/sub/h.py"],
                         ["pkg/mod.py", "pkg/testing.py", "pkg/contest.py", "pkg/attest.py"])
        self.assert_hits("no-test-swap", 'import sys\nif "pytest" in sys.modules:\n    x()\n',
                         ["app/mod.py"],
                         ["app/test_b.py", "app/b_test.py", "app/conftest.py", "app/tests/h.py", "app/test/h.py"])

    def test_ts_test_code_files(self):
        self.assert_hits("no-fixed-sleep", "await sleep(100);\n",
                         ["src/a.test.ts", "src/a.spec.ts", "src/b.test.js", "src/c.spec.mjs",
                          "src/__tests__/a.ts", "tests/a.ts", "test/a.js", "e2e/a.ts"],
                         ["src/a.ts", "src/b.js", "src/testing.ts", "src/latest.ts"])

    def test_ts_test_swap_skips_test_code_and_tool_config(self):
        self.assert_hits("no-test-swap", "if (process.env.VITEST) x();\n",
                         ["src/a.ts", "src/b.js", "src/c.mjs"],
                         ["src/a.test.ts", "src/a.spec.ts", "src/b.test.js", "src/__tests__/a.ts", "tests/a.ts",
                          "test/a.js", "e2e/a.ts", "vite.config.ts", "playwright.config.js", "vitest.setup.ts",
                          "vitest.workspace.ts", "src/__mocks__/a.ts"])

    def test_svelte_script_langs(self):
        ts = '<script lang="ts">\nif (process.env.VITEST) x();\nawait sleep(100);\n</script>\n'
        js = ts.replace(' lang="ts"', "")
        self.assert_hits("no-test-swap", ts, ["src/A.svelte"], ["tests/A.svelte", "src/__mocks__/A.svelte"])
        self.assert_hits("no-test-swap", js, ["src/A.svelte", "src/B.svelte"],
                         ["tests/B.svelte", "src/__mocks__/B.svelte"])
        # Plain <script> is JavaScript, and only no-test-swap has a JavaScript copy, so tests/B.svelte is quiet.
        self.assert_hits("no-fixed-sleep", ts, ["tests/A.svelte"], [])

    def test_coverage_pragma_py_everywhere(self):
        # Production and test code alike; vendored code skipped.
        self.assert_hits("no-coverage-pragma", "def main():  # pragma: no cover\n    run()\n",
                         ["app/mod.py", "tests/test_a.py"], ["vendor/x.py", "node_modules/p/x.py"])

    def test_coverage_pragma_ts_everywhere(self):
        # Every TS/JS flavour and both Svelte script langs; vendored code skipped.
        for f in ["src/a.ts", "src/b.js", "src/c.tsx", "src/a.test.ts", "node_modules/p/a.js"]:
            self.write(f, "/* istanbul ignore next */\nexport const a = 1;\n")
        self.write("src/A.svelte", '<script lang="ts">\n/* v8 ignore next */\nconst a = 1;\n</script>\n')
        self.write("src/B.svelte", "<script>\n// c8 ignore next\nlet a = 1;\n</script>\n")
        out = self.check().stdout
        self.assertEqual({line.split(":")[0] for line in out.splitlines() if ": no-coverage-pragma:" in line},
                         {"src/a.ts", "src/b.js", "src/c.tsx", "src/a.test.ts", "src/A.svelte", "src/B.svelte"}, out)

    def test_malformed_ast_grep_output(self):
        for out in ["not json", "{}"]:
            fake = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, fake)
            (fake / "ast-grep").write_text(f"#!/bin/sh\necho '{out}'\n")
            (fake / "ast-grep").chmod(0o755)
            r = self.check(env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"})
            self.assertEqual(r.returncode, 2, out)
            self.assertNotIn("Traceback", r.stderr)

    def test_github_format_hit(self):
        self.write("tests/a%,b:c.rs", SLEEP)
        r = self.check()
        self.assertIn("tests/a%,b:c.rs:2: no-fixed-sleep: ", r.stdout)
        r = run("check", "--format", "github", str(self.repo))
        self.assertEqual(r.returncode, 1)
        first, last = r.stdout.splitlines()
        self.assertRegex(first, r"^::error file=tests/a%25%2Cb%3Ac\.rs,line=2,col=5::no-fixed-sleep: \S")
        self.assertEqual(last, "::error file=caltrop.toml::run caltrop baseline to adopt caltrop in this repo")

    def test_github_format_allowance(self):
        self.write("tests/a.rs", SLEEP)
        self.write("caltrop.toml", '[allow.no-fixed-sleep]\n"tests/a.rs" = 2\n')
        r = self.check()
        self.assertEqual(r.stdout, "lower the allowance for no-fixed-sleep in tests/a.rs to 1\n"
                                   "edit caltrop.toml as shown\n")
        r = run("check", str(self.repo), "--format", "github")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.splitlines(), [
            "::error file=caltrop.toml::lower the allowance for no-fixed-sleep in tests/a.rs to 1",
            "::error file=caltrop.toml::edit caltrop.toml as shown"])
        self.assertEqual(run("check", "--format", "text", str(self.repo)).stdout, self.check().stdout)

    def test_github_escape(self):
        loader = importlib.machinery.SourceFileLoader("caltrop", SCRIPT)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("caltrop", loader))
        loader.exec_module(mod)
        self.assertEqual(mod.gh_escape("100%\r\na: b, c"), "100%25%0D%0Aa: b, c")
        self.assertEqual(mod.gh_escape("100%\r\na: b, c", True), "100%25%0D%0Aa%3A b%2C c")

    def test_base_id_drops_variant(self):
        loader = importlib.machinery.SourceFileLoader("caltrop", SCRIPT)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("caltrop", loader))
        loader.exec_module(mod)
        for rule_id in ("no-weak-result-assert-ts", "no-weak-result-assert.catch-tsx",
                        "no-weak-result-assert.raises-body-py"):
            self.assertEqual(mod.base_id(rule_id), "no-weak-result-assert", rule_id)
        self.assertEqual(mod.base_id("no-fixed-sleep-tests-dir"), "no-fixed-sleep")

    def test_weak_assert_variants_share_id(self):
        self.write("tests/test_a.py", "def test_a():\n    with pytest.raises(ValueError):\n        x = f()\n        g(x)\n")
        self.write("src/a.test.ts", "it('x', () => { try { f(); } catch (e) { expect(e.code).toBe('x'); } });\n")
        r = self.check()
        self.assertIn("tests/test_a.py:2: no-weak-result-assert: Put only the call", r.stdout)
        self.assertIn("src/a.test.ts:1: no-weak-result-assert: The catch only runs", r.stdout)
        self.assertEqual(run("baseline", str(self.repo)).returncode, 0)
        toml = (self.repo / "caltrop.toml").read_text()
        self.assertIn("[allow.no-weak-result-assert]", toml)
        self.assertNotIn("assert.", toml)
        self.assertEqual(self.check().returncode, 0)

    def test_bad_format(self):
        for args in (["--format", "json"], ["--format"], ["--format", "github", "x", "y"]):
            r = run("check", *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("usage:", r.stderr)
        self.assertEqual(run("baseline", "--format", "github").returncode, 2)


if __name__ == "__main__":
    unittest.main()
