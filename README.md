<div align="center">

<h1><img src="docs/assets/logo-lockup.png" alt="caltrop" width="520"></h1>

**Fail CI when a test takes a shortcut that coding agents like.**

[![CI](https://img.shields.io/github/actions/workflow/status/Toby-Faucher/caltrop/ci.yml?branch=main&label=CI)](https://github.com/Toby-Faucher/caltrop/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Toby-Faucher/caltrop)](https://github.com/Toby-Faucher/caltrop/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![ast-grep 0.44.1](https://img.shields.io/badge/ast--grep-0.44.1-E5654B)](https://github.com/ast-grep/ast-grep/releases/tag/0.44.1)

</div>

caltrop covers Rust, Python, and TypeScript/JavaScript including React (`.tsx`/`.jsx`) and Svelte components. It flags sleeping instead of waiting for an event, polling until a deadline, swapping behaviour under test, mocks, skipped or filtered tests, tests that assert nothing, and retries. Each failure says what to do instead, so the agent can fix it in the same loop. It is built on [ast-grep](https://ast-grep.github.io) rules plus a small Python script, and it is modelled on [landmines](https://github.com/interfere-inc/landmines).

## What it catches

A test an agent might write to make a failure go away:

```python
import time
from unittest import mock

import pytest

from app import worker


def test_job_finishes():
    worker.start()
    time.sleep(2)
    assert worker.done()


@pytest.mark.skip("flaky on CI")
def test_retry():
    with mock.patch("app.worker.fetch"):
        worker.retry()
```

`caltrop check` on a repo with only `tests/test_worker.py` exits 1:

```
tests/test_worker.py:2: no-mock-libs: Use the real implementation, not a mock or a patched attribute. Pass the dependency in. For HTTP, a real local server (`pytest-httpserver`, a uvicorn app on a free port) is fine. `monkeypatch.setenv`, `chdir` and `syspath_prepend` are fine.
tests/test_worker.py:11: no-fixed-sleep: Await the operation or an event it emits (`asyncio.Event`, a queue, a future). To prove something did not happen, send a sentinel after it and wait for the sentinel. For timers or timestamps, inject the clock or freeze time (`time-machine`, `freezegun`).
tests/test_worker.py:15: no-ignored-test: An ignored test never runs in CI, and an xfail passes whether or not it fails. Make it run (fixture, dependency or a CI job), or delete it.
tests/test_worker.py:16: no-assertion-free-test: This test checks nothing. Assert on the result. If 'does not raise' is the point, say so with an explicit assertion.
run caltrop baseline to adopt caltrop in this repo
```

With `--format github` the same hits become pull request annotations, one per line:

```
::error file=tests/test_worker.py,line=11,col=5::no-fixed-sleep: Await the operation or an event it emits ...
```

## Contents

- [Quick start](#quick-start)
- [Install](#install)
- [Usage](#usage)
  - [The allowlist](#the-allowlist)
- [Rules](#rules)
- [Known limits](#known-limits)
- [Pinning](#pinning)
- [Tests](#tests)
- [Credit](#credit)
- [License](#license)

## Quick start

Add the GitHub Action to a workflow:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: Toby-Faucher/caltrop@v1.3.0
    # with:
    #   dir: path/to/repo   # default: .
```

It installs ast-grep 0.44.1 with pipx and runs `caltrop check`. The action first ships in v1.1.0; v1.0.0 has no `action.yml`.

If the repo already has hits, run [`caltrop baseline`](#usage) once and commit `caltrop.toml`.

## Install

caltrop needs ast-grep 0.44.1 and Python 3.11 or newer (standard library only). Pin caltrop and ast-grep: see [Pinning](#pinning). For the GitHub Action, see [Quick start](#quick-start).

### pre-commit

```yaml
repos:
  - repo: https://github.com/Toby-Faucher/caltrop
    rev: v1.3.0
    hooks:
      - id: caltrop
```

The hook installs ast-grep 0.44.1 itself and checks the whole repo on every commit.

### pipx

```
pipx install git+https://github.com/Toby-Faucher/caltrop@v1.3.0
pipx install ast-grep-cli==0.44.1
```

### Manual

ast-grep: download the prebuilt binary from the [0.44.1 release](https://github.com/ast-grep/ast-grep/releases/tag/0.44.1), or run:

```
cargo install ast-grep --version 0.44.1 --locked
```

caltrop: clone it and symlink the script onto your PATH.

```
git clone https://github.com/Toby-Faucher/caltrop ~/Projects/caltrop
ln -s ~/Projects/caltrop/caltrop ~/.local/bin/caltrop
```

## Usage

```
caltrop check [--format text|github] [REPO_DIR]   # default: text, current directory
caltrop baseline [REPO_DIR]                        # write caltrop.toml from the current hits
```

`check` scans the repo, counts hits per rule and file, and compares them with `caltrop.toml` at the repo root. Exit codes: 0 pass, 1 violations, 2 usage or tool error (ast-grep missing, bad TOML, or ast-grep ran fewer rules than caltrop ships, for example because an ignore file above the install hides `rules/`).

In GitHub Actions, `caltrop check --format github` prints each problem as an error annotation, so hits show up next to the code in the pull request. Allowance problems are annotated on `caltrop.toml`. The default is `--format text`. Exit codes are the same.

```
::error file=tests/a.rs,line=2,col=5::no-fixed-sleep: Await the operation or an event it emits. ...
```

Run `baseline` once, to adopt caltrop in a repo that already has hits. It overwrites `caltrop.toml` with the current counts. After that, fix hits instead of re-running it.

### The allowlist

```toml
[allow.no-fixed-sleep]
"crates/server/tests/timeouts.rs" = 5
"crates/server/tests/push.rs" = 1
```

Each entry is a rule id, a file, and the number of hits allowed there. The count can only shrink:

- More hits than allowed: `check` fails and prints each hit as `file:line: rule: message`.
- Fewer hits than allowed: `check` fails with "lower the allowance for <rule> in <file> to <n>". This is the ratchet. Pay down a hit, then lower the number.
- An entry for a file that no longer exists fails the same way, with a target of 0.
- An unknown rule id in `caltrop.toml` fails.

## Rules

Rule ids are stable. They key the allowlist. Each language has its own rule files, but a rule that means the same thing in every language shares one id: a Python sleep and a Rust sleep both count under `no-fixed-sleep`. The rule files carry a language suffix (`no-fixed-sleep-py.yml`, `no-test-swap-ts.yml`) that `caltrop` strips. A case that needs its own message gets its own file with a dotted variant (`no-weak-result-assert.catch-ts.yml`), which is stripped too.

### Rust

<details><summary>9 Rust rules</summary>

| id | Matches | Message |
|---|---|---|
| `no-fixed-sleep` | A sleep call in test code, outside a loop. | Await the operation or an event it emits. To prove something did not happen, send a sentinel after it and wait for the sentinel. For timers, use `#[tokio::test(start_paused = true)]`. For distinct timestamps, inject the clock. |
| `no-deadline-poll` | A sleep call inside `loop`, `while` or `for` in test code. | Wait on a signal (`tokio::sync::Notify`, `watch`, a channel, an event stream), not on a deadline. |
| `no-test-swap` | Outside test code: a `cfg!(..)` that mentions `test`, a `#[cfg(..)]` containing `not(test)`, or a `cfg` on a test-only cargo feature (a feature name with a `-` or `_` separated word `test`, `tests`, `testing`, `mock`, `fake` or `stub`, plural too, like `test-support` or `net_mock`). | Production code must behave the same under test. Pass the dependency in instead. |
| `no-mock-crates` | `use` of `mockall`, `mockers`, `faux` or `mry`; `#[automock]` and similar attributes; `mock!`. | Use the real implementation. For HTTP, a real local server (`wiremock`, `httpmock` are fine). |
| `no-test-retries` | `retries` above 0 in any profile or override of `.config/nextest.toml`. | Make the test deterministic; a retry hides the flake. |
| `no-ignored-test` | Any `#[ignore]` attribute. | An ignored test never runs in CI. Make it run (fixture, feature or a CI job), or delete it. |
| `no-weak-result-assert` | `assert!` or `debug_assert!` whose whole condition is one `.is_ok()` or `.is_err()` (negated too). `&&`, `\|\|` or `^` make it a compound condition and it is skipped, as is `try_recv().is_ok()`/`is_err()`. | Assert the value or which error. Use `assert_eq!(r, Ok(..))`, `assert!(matches!(r, Err(E::X)))` or check `r.unwrap_err()`. |
| `no-silent-skip` | Inside a `#[test]` function: an early `return`, `return eprintln!(..)` or `return Ok(())` under `if let Err/None = ..`, under a negated or `is_err()`/`is_none()` check on a prerequisite (`exists`, `is_file`, `env::var`, `ready`, `*present`, `*available`, `UdpSocket`, `TcpListener`, `find_*` and similar), or in any `let .. else`. | A test must not return early when a prerequisite is missing. It reports a pass. Provide the prerequisite in CI, and fail with a clear message if it is absent. |
| `no-fake-impls` | `impl SomeTrait for` a type named `Mock`, `Fake`, `Stub`, `Spy` or `Dummy` (alone or followed by a capital, digit or `_`, like `FakeClock`). Traits like `Debug`, `Display`, `Drop`, `Clone`, `Error` and `From<..>` are skipped, with or without a path. | Use the real implementation. A hand-written fake that stands in for a trait is a mock. A real local server on a socket is fine. |

</details>

"Test code" means a `.rs` file under a `tests/` directory, a file named `tests.rs` or `*_tests.rs`, or code inside a `mod` or `fn` whose attributes include `#[cfg(test)]`, `#[cfg(all(.., test, ..))]`, `#[test]` or `#[<path>::test]` (other attributes and comments may sit between them). `no-test-swap` skips both. Sleep calls are `sleep`, `sleep_until`, and those names under `thread::`, `std::thread::`, `time::`, `tokio::time::`, `task::` and `async_std::task::`.

Name files that `#[cfg(test)] mod x;` pulls in `tests.rs` or `*_tests.rs` (for example `view_tests.rs`), so they are scanned.

A loop search stops at closures, `async` blocks and function boundaries. A sleep inside `tokio::spawn(async move { .. })` counts as `no-fixed-sleep`, even if that block sits in a loop.

### Python

<details><summary>17 Python rules</summary>

| id | Matches | Message |
|---|---|---|
| `no-fixed-sleep` | In test code, outside a loop: `time.sleep`, `asyncio.sleep`, `trio.sleep` or `anyio.sleep`, or a bare `sleep(..)` in a file that does `from time/asyncio/trio/anyio import sleep`; `loop.call_later(n, ..)` (in a loop too). `sleep(0)`, `sleep(float("inf"))`/`sleep(math.inf)` and `call_later(0, ..)` are skipped. | Await the operation or an event it emits (`asyncio.Event`, a queue, a future). To prove something did not happen, send a sentinel after it and wait for the sentinel. For timers or timestamps, inject the clock or freeze time (`time-machine`, `freezegun`). |
| `no-deadline-poll` | The same sleeps (not `call_later`) inside `while` or `for` (including `async for`) in test code. The loop search stops at `def`, `lambda` and `class`. | Wait on a signal (`asyncio.Event`, `asyncio.Condition`, a queue, `threading.Event.wait()`), not on a deadline. |
| `no-test-swap` | Outside test code: `"pytest"`/`"unittest" in sys.modules` (or `sys.argv`), `sys.modules.get("pytest")`; a test key (`PYTEST*`, `TEST`, `TESTS`, `TESTING`, with prefixes like `IS_`/`RUNNING_` or suffixes `_MODE`/`_ENV`) read through `getenv`, `environ`, `config[..]`, `settings[..]`, `hasattr`/`getattr`; attributes like `.TESTING` or `.is_testing` (lowercase `.testing` is skipped: `np.testing` is a module); an env-style name (`ENV`, `APP_ENV`, `settings.environment`, `config["ENV"]`) compared with `"test"` or `"testing"`. | Production code must behave the same under test. Pass the dependency or setting in instead of checking whether a test is running. |
| `no-mock-libs` | Imports of `unittest.mock`, `mock` or `pytest_mock` (except `from unittest.mock import sentinel`), any `mocker.*(..)` call except `mocker.patch.dict(os.environ, ..)`, and `monkeypatch.setattr(..)`. | Use the real implementation, not a mock or a patched attribute. Pass the dependency in. For HTTP, a real local server (`pytest-httpserver`, a uvicorn app on a free port) is fine. `monkeypatch.setenv`, `chdir` and `syspath_prepend` are fine. |
| `no-mock-libs` | In test code, an assignment to `X.attr` or `X.Class.attr` (capitalised middle name) where `X` is a name the file imports (`import X`, `import a as X`, `from m import X`): `sqlalchemy.ARRAY = ..`, `requests.get = fake`, `DATETIME.bind_processor = ..`. Skipped: subscripts (`os.environ[..]`, `app.dependency_overrides[..]`), attributes of a call or a local object, a name shadowed by a parameter, local or `as` target, and code that undoes it: a function with `yield`, `finally`, `addCleanup`/`addfinalizer`/`enterContext`, a `setUp*`/`setup_*`/`tearDown*`/`teardown_*` function, or a class that has a teardown. | This replaces a library or module attribute for every later test and is never undone. Pass the dependency in; if the library needs a shim to run under the test database, put it in one fixture that undoes it, or allowlist the shim. |
| `no-stubbed-gate` | In test code, a FastAPI `dependency_overrides[..] = ..` (or `.update({..})`) whose replacement only raises `HTTPException` with 401 or 403: a lambda, or a `def` in the same file whose body raises it directly and has no `return`. In a `test*` function, only when that test asserts a 401/403; in a fixture or helper, always. A gate that checks something before it raises, and other statuses (a 503 to test an error handler), are skipped. | This test replaces the auth check with a stub that raises, then checks the stub raised. Override the user (the dependency that returns the current user) with a real non-admin user and let the real gate refuse. |
| `no-stubbed-gate` | A pytest fixture named for a regular user (`user`, `member`, `regular`, `normal`, `readonly`, `viewer`, `guest`, `non_admin` as a `_`-separated part, and no `admin` part) that overrides a dependency whose name contains `admin` with something that does not raise. | This fixture is named for a regular user but overrides the admin check so it lets every request through, so its tests run as admin. Override only the current user with a non-admin user and leave the admin check real. |
| `no-test-retries` | `pytest.mark.flaky` and the `flaky` package's `@flaky` in test code; `--reruns N` in `addopts`, or `reruns = N` (N > 0), in the pytest section of any `pyproject.toml`, `pytest.ini`, `setup.cfg` or `tox.ini` in the repo. | Make the test deterministic; a retry hides the flake. |
| `no-ignored-test` | `pytest.mark.skip`, `pytest.mark.xfail`, `unittest.skip` or `unittest.expectedFailure`, as a decorator, in `pytestmark` or in `pytest.param(marks=..)`. | An ignored test never runs in CI, and an xfail passes whether or not it fails. Make it run (fixture, dependency or a CI job), or delete it. |
| `no-silent-skip` | In test code: any `pytest.skip(..)`, `pytest.importorskip(..)` or `self.skipTest(..)`; `@pytest.mark.skipif`, `unittest.skipIf`/`skipUnless`; a `return` whose nearest function is `test*`, under an `if` with a negated or `is None` check on a prerequisite (`which`, `exists`, `environ`, `getenv`, `find_spec`, `*available` and similar) or in an `except ImportError` block. Each return is one hit, however many guards wrap it. | A test must not skip or return early when a prerequisite is missing. Provide the prerequisite in CI, and fail with a clear message if it is absent. |
| `no-fake-impls` | In test code, a `class` named `Mock`, `Fake`, `Stub`, `Spy` or `Dummy` (leading `_` allowed, alone or followed by a capital, digit or `_`), with or without a base class; a class whose base is named that way (`class SecondSendRaises(FakeMailer)`); a class named for a failure it fakes (`FlakyGateway`, `_BrokenStore`, `AlwaysDown`, `NeverReady`; `Test*` classes skipped); and a class with no base and a non-dunder method defined inside a `test*` function (`def test_x(): class Boom: def send(..)`). Exception, Error and Warning subclasses are skipped, and so are dataclasses and attrs classes in a test. | Use the real implementation. A hand-written fake class that stands in for a real type is a mock, with or without a base class. A real local server on a socket is fine. |
| `no-conditional-assert` | In a `test*` function (not a helper, not inside a `for`/`while`): an `if` with no `else`/`elif` whose block has an `assert` or `self.assert*(..)` and no `return`. Skipped when an earlier `assert` in the same block names a value in the condition (`assert r is not None` then `if r is not None:`) or the condition names a test parameter (a parametrize argument). | Assert the condition first, then check the value. An assertion inside an `if` with no `else` is skipped when the condition is false. |
| `no-weak-result-assert` | `pytest.raises(..)` or `self.assertRaises(..)` of `Exception`, `BaseException`, `SystemExit`, or `IntegrityError`/`DatabaseError` (any module prefix, e.g. `sqlalchemy.exc.`) with no `match=`, unless it is `with .. as e:` and a later statement reads `e.value` or `e.exception`. | Assert which error. Raise and catch the specific exception type (`pytest.raises(ValueError, match=..)`), not `Exception`, which passes on any bug. For `SystemExit` or `IntegrityError`, add `match=` or check `e.value` (the exit code, the constraint). |
| `no-constant-assert` | In test code: `assert True`, a nonzero number or a non-empty string; `assert x == x` on a name or attribute path; `assert len(x) >= 0`; `self.assertTrue(True)`; an assert whose condition ends in `or True`. `assert False`/`assert 0` and `assert f(x) == f(x)` (a determinism check) are skipped. | This assertion cannot fail. Compare what the code returns with an expected value written in the test. Delete a placeholder test; do not keep it green. |
| `no-constant-assert` | In test code: `assert all(.. for x in xs if ..)` or `self.assertTrue(all(..))` over a generator or list comprehension with an `if` filter. An unfiltered `all(..)` is skipped. | all() is true for an empty sequence. Assert how many items you expect first. |
| `no-coverage-pragma` | A comment that coverage.py reads as an exclusion (its default `# pragma: no cover` and `# pragma: no branch` regexes), in any file. Skipped where coverage.py already excludes the line, so the pragma changes nothing: `if TYPE_CHECKING:` and a stub whose body is only `...` (a `Protocol` method). | Cover this code with a test instead of excluding it from coverage. An excluded line lets a coverage threshold pass on code no test runs. |
| `no-source-text-test` | In test code: `inspect.getsource(..)`/`getsourcelines(..)`; `open(..)` (not for writing) or `.read_text()`/`.read_bytes()` whose call names a `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.svelte`, `.vue` or `.rs` file in a string literal. Skipped: paths that name a fixture, golden, snapshot or `testdata` file, or an output directory (`tmp*`, `out`/`outDir`, `dist`, `build`, `gen`); text passed to `exec`/`compile`/`eval` or copied with `.write_text(..)`; hash pins (`hashlib`, `sha*`, `*digest`); `getsource(a) == getsource(b)` parity checks. | Test what the code does, not how its source reads. Call it and assert on the result. Reading a source file or `inspect.getsource` passes whatever the code does at run time. |
| `no-swallowed-error` | Directly in a `test*` function: `except ..: pass` or `...` (comments allowed), and `with suppress(..)`/`contextlib.suppress(..)`. Skipped: a handler inside `finally`, a `try` or `with` body that only cleans up (`close`, `kill`, `terminate`, `unlink`, `remove`, `rmtree`, `stop` and similar), and a `try` that ends in `raise AssertionError`/`self.fail`/`pytest.fail`/`assert False` with a handler narrower than `Exception`. | Do not discard an error in a test. Let it fail the test, or assert which error you expect (`pytest.raises(X)`). Cleanup that may fail belongs in a fixture's teardown or `addCleanup`. |
| `no-weak-result-assert` | A `with pytest.raises(..)`/`raises(..)`/`self.assertRaises(Regex)(..)` body with more than one statement, or one `if`/`while`/`for`/`try`/`match`/`with` (ruff PT012). Allowed, as in PT012: a `def` or `class`, a `for` whose body is only `pass` or `...`, a nested `with` around one simple statement. | Put only the call that should raise inside `pytest.raises`. Do the setup before it and the asserts after it: the error may come from the setup, and nothing after the raising line runs. |
| `no-weak-result-assert` | In test code, an `assert` on a status (`r.status_code`, `r.status`, `status`) that lets a 500 through: `in` a tuple, list or set with a 5xx literal or constant (`HTTP_500_..`, `INTERNAL_SERVER_ERROR`); `>= 400`/`> 399` (any value below 500); `!= 200` or `not in (200, ..)` (2xx only); the same through `self.assertIn`/`assertNotIn`/`assertGreater(Equal)`/`assertNotEqual`. Skipped: `== expected`, `< 500`, `!= 500`, `400 <= s < 500`, `!= 401` (a check that one layer let the request past), and success tuples like `in (200, 201)`. | Assert the one status this request should return. A check that accepts 500 passes when the server crashes. |
| `no-test-filter` | In the pytest section of any `pyproject.toml`, `pytest.ini`, `setup.cfg` or `tox.ini`: `addopts` with `--deselect`, `--ignore`, `--ignore-glob` or `-k`. | Run the whole suite in CI. Fix or delete the test you are filtering out, and let a run that finds no tests fail. |
| `no-assertion-free-test` | In test code, a `test*` function with no `assert`, `raise`, `pytest.raises`/`warns`/`fail`, `self.assert*` or other `assert*`/`expect*`/`fail*` call, that also calls no function in Python test code (any file, `conftest.py` included) that asserts, directly or through another such function. `benchmark(..)` and `@pytest.mark.limit_memory`/`limit_leaks` tests are skipped. | This test checks nothing. Assert on the result. If 'does not raise' is the point, say so with an explicit assertion. |

</details>

"Test code" in Python means a file named `test_*.py`, `*_test.py` or `conftest.py`, or any file under a `tests/` or `test/` directory. `no-test-swap` checks only the other files; `no-mock-libs` and `no-coverage-pragma` check every file.

### TypeScript, JavaScript and Svelte

The rules are written for TypeScript. `sgconfig.yml` parses `.js`, `.mjs`, `.cjs`, `.mts` and `.cts` as TypeScript, `.tsx` and `.jsx` as tsx, and `.svelte` files as HTML, so the rules also run inside a component's `<script>` block. ast-grep treats tsx as its own language, so `rules/tsx/`, `utils/tsx/` and `rule-tests/tsx/` are generated copies of the `ts` ones: edit the `ts` file and run `scripts/gen-tsx.py`. A unit test fails if the copies are stale.

<details><summary>17 TypeScript, JavaScript and Svelte rules</summary>

| id | Matches | Message |
|---|---|---|
| `no-fixed-sleep` | In test code, outside a loop: `new Promise(r => setTimeout(r, n))` (arrow, function and block forms, `window.setTimeout`); `sleep`/`delay`/`wait`/`pause(n)` with a nonzero number or a duration-like name (`ms`, `*Ms`, `*_timeout`, `ALL_CAPS`); `await setTimeout(n)` from `timers/promises`; `x.waitForTimeout(..)`. A delay of `0`, a bare `setTimeout(cb, n)`, a Promise whose timer only calls its `reject` (a `Promise.race` timeout guard) and the sleep helper's own definition are skipped, and so is any file that calls `vi.useFakeTimers` or `jest.useFakeTimers`. Also, with its own message: `waitFor(..)`/`x.waitFor(..)` whose callback is `() => {}`, `async () => {}` or returns `undefined`/`null`/`true`/`false`. | Await the operation or an event it emits; for UI use `waitFor`/`findBy*` or Playwright's auto-waiting `expect(..)`. For timers, use `vi.useFakeTimers()` and `vi.advanceTimersByTime`. To prove something did not happen, wait for a later sentinel instead. For an empty `waitFor`: Wait for the condition: put the assertion in the `waitFor` callback, or use `findBy*`. |
| `no-deadline-poll` | The same sleeps inside `for`/`for..of`/`while`/`do` in test code, skipping fake-timer files the same way. The search stops at the nearest function or callback. | Wait on a signal (an event, a promise the code resolves, `expect.poll`/`waitFor` on the real condition), not a sleep in a loop. |
| `no-test-swap` | Outside test code and tool config: a read of `import.meta.env.VITEST` or `process.env.VITEST`/`VITEST_WORKER_ID`/`JEST_WORKER_ID`, or `import.meta.env.MODE`/`process.env.NODE_ENV` compared with `'test'`, in code or in a `.svelte` template (`{#if ..}`, `{..}`, `attr={..}`). `DEV`, `PROD`, `$app/environment` `dev`, `import.meta.vitest` and assignments are skipped. | Production code must behave the same under test. Pass the dependency in (a parameter, a context, a constructor argument) and give the test a real one. `dev`/`DEV`/`PROD` are fine; they are not test switches. |
| `no-mock-libs` | `vi`/`jest` `.mock`, `.doMock`, `.unstable_mockModule`; `vi.stubGlobal` of `fetch`/`XMLHttpRequest`/`WebSocket`/`EventSource`; `globalThis.fetch = vi.fn()`; the first `.mockImplementation/ReturnValue/ResolvedValue/RejectedValue(Once)` on a `vi.spyOn`/`jest.spyOn`, or `const s = vi.spyOn(..)` when `s.mock*(..)` follows in the same block; imports of `sinon`, `ts-mockito`, `testdouble`, `jest-mock-extended`, `vitest-mock-extended`, `fetch-mock`, `jest-fetch-mock`, `vitest-fetch-mock`. Skipped: `vi.fn()`, `vi.mocked`, spies on `console`, pass-through spies, msw, nock. | Use the real implementation; pass dependencies in instead of replacing modules or globals. For HTTP, use a real local server or msw (it serves real Responses to the real fetch). A `vi.fn()` callback spy is fine. |
| `no-test-retries` | `retry`/`retries` with a nonzero literal (including `CI ? 2 : 0`) in the `test:` object of a vite/vitest config, at the top level of a Playwright config, or in a `projects[]` entry (plugin and dev-server retry options are skipped); an options object passed to `it`/`test`/`describe`/`test.describe.configure`; `this.retries(n)`; `jest.retryTimes(n)`. | Make the test deterministic; a retry hides the flake. |
| `no-ignored-test` | `xit`/`xtest`/`xdescribe`; any `.todo`; `.skip`/`.fixme` with no arguments or with a test body, including `.concurrent.skip`, `test.describe.skip` and `it.skip.each(..)`; expected-to-fail tests in any form: vitest `.fails`, jest `.failing` (`.each` too) and Playwright `test.fail(..)`. | A skipped or todo test never runs in CI, and an expected-to-fail test (`.fails`, `.failing`, `test.fail`) passes while the code is broken. Make it run and pass (fixture, real dependency or a CI job), or delete it. |
| `no-focused-test` | `.only` on `it`/`test`/`describe` and friends (`.only.each` too), and `fit`/`fdescribe` (`.each` too) called as a test declaration. | `.only` silently skips every other test in the file. Remove it. |
| `no-silent-skip` | `.skipIf(..)`/`.runIf(..)`; Playwright's conditional `test.skip(cond, ..)`/`test.fixme(cond)`; `ctx.skip()`/`context.skip()`/`t.skip()`/`this.skip()`/bare `skip()` in a test body; an `if (!..)` on a prerequisite (`existsSync`, `process.env`, `import.meta.env`, `*Available`, `*Installed`, `ready`, `which`, `find*` and similar) whose branch does a bare `return` or `return console.x(..)` in an `it`/`test` callback. | A test must not skip itself when a prerequisite is missing; it reports a pass or a skip that nobody reads. Provide the prerequisite in CI and fail with a clear message if it is absent. |
| `no-fake-impls` | In test code, a class named `Mock`/`Fake`/`Stub`/`Spy`/`Dummy` (alone, or followed by a capital, digit or `_`) with `implements` or `extends`; a class that `extends` a class named that way (`class SecondSendRaises extends FakeClient`); a class named for a failure it fakes (`FlakyApi`, `AlwaysDown`, `NeverReady`) with a heritage clause or a method; and a class (declaration or expression) without `extends` and with a method other than `constructor`, declared directly in an `it`/`test`/`specify` callback. `*Error`/`*Exception` names are skipped. | Use the real implementation. A hand-written fake class that stands in for an interface or base class is a mock. A real local server on a socket is fine. |
| `no-conditional-assert` | In an `it`/`test` callback (not a helper, a `forEach`/`.each` callback or a loop body): an `if` with no `else` whose branch calls `expect(..)`, `assert(..)` or `assert.*(..)` (not `.fail`) and has no `return`. Skipped when an earlier statement does `expect(x)` on a value in the condition (narrowing: `expect(r.ok).toBe(true); if (r.ok) ..`), when the condition names a callback parameter (`browserName`), and when the test is one of a generated set (`it` inside a `for` or a `.each`/`.forEach`/`.map` callback). | Assert the condition first, then check the value. An assertion inside an `if` with no `else` is skipped when the condition is false. |
| `no-weak-result-assert` | `.toThrow()`/`.toThrowError()` with no argument, including `.rejects.`, but not `.not.toThrow()`; `assert.throws(fn)`/`assert.rejects(p)` with one argument. | Assert which error: pass the class, a message regex or a matcher, e.g. `toThrow(NotFoundError)`, `rejects.toThrow(/timed out/)`. A bare `toThrow()` passes on any error, including a TypeError from a typo. |
| `no-constant-assert` | In test code: `expect(<true/false/null/undefined/number>)` with `toBe`/`toEqual`/`toStrictEqual`/`toBeTruthy`/`toBeFalsy`/`toBeDefined`/`toBeNull`/`toBeUndefined` and a literal or no argument; `expect(x).toBe(x)` (`toEqual`, `toStrictEqual`) on a name or property path; `expect(x.length/.size).toBeGreaterThanOrEqual(0)`; `assert(true)`, `assert.ok(true)`. String subjects and `expect(f(x)).toBe(f(x))` (a determinism check) are skipped. | This assertion cannot fail. Compare what the code returns with an expected value written in the test. Delete a placeholder test; do not keep it green. |
| `no-constant-assert` | In test code: `.some`/`.every`/`.find`/`.findIndex`/`.findLast`/`.findLastIndex`/`.filter` called with an arrow that returns `true` or `false`, inline inside an `expect(..)`/`assert(..)` argument, or by the name of a `const x = (..) => true` declared in the same file. `vi.fn(() => true)`, `mockImplementation(() => true)` and callbacks passed to other functions are skipped. | This predicate always returns the same value, so the check never looks at the items. Write the condition the test means. |
| `no-coverage-pragma` | In any file, including a `.svelte` `<script>` (both langs) and JSX: `istanbul ignore next/if/else/file`, `c8`/`v8 ignore next/if/else/file/start`, `node:coverage ignore next`/`disable`, as `//` or `/* */`. A `start`/`stop` or `disable`/`enable` pair counts once. | Cover this code with a test instead of excluding it from coverage. An excluded line lets a coverage threshold pass on code no test runs. |
| `no-source-text-test` | In test code: `readFileSync`/`readFile` (`fs.`, `fs.promises.`, `fsp.` too) whose arguments name a `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts`, `.svelte`, `.vue`, `.py` or `.rs` file in a string, template or `new URL(..)` literal. Skipped: paths that name a fixture, golden, snapshot or `testdata` file, or an output directory (`tmp*`, `out`/`outDir`, `dist`, `build`, `gen`); text run by `vm.runIn*Context`, `new vm.Script`, `new Function` or `eval`, directly or through a `const` in the same block; hash pins (`.update(readFileSync(..))`). | Test what the code does, not how its source reads. Call it and assert on the result. Reading a source file passes whatever the code does at run time. |
| `no-swallowed-error` | Inside an `it`/`test`/`specify` callback: `await f().catch(..)` as a statement with an empty handler (`() => {}`, `() => undefined`/`null`/`void 0`, `function () {}`, `noop`); an empty `catch {}`/`catch (e) {}` (comments allowed) whose `try` awaits something. Skipped: a used result (`const b = await r.json().catch(() => null)`), a `.catch` that is not awaited, a sync `try`, `finally` blocks, before/after hooks, Playwright fixture code after `await use(..)`, and best-effort cleanup (`close`, `kill`, `rm`, `unlink`, `chmod`, `destroy`, `dispose`, `stop` and similar). | Do not discard an error in a test. Let it fail the test, or assert which error you expect (`rejects.toThrow(X)`). Cleanup that may fail belongs in `afterEach` or a fixture's teardown. |
| `no-weak-result-assert` | A `try` in an `it`/`test` callback (not in a nested function) whose `catch` has the only `expect`/`assert` calls: the `try` block has no assertion or `throw`, the `catch` does not `throw` or `return`, nothing after the `try` asserts or throws, and the test has no `expect.assertions(n)`/`expect.hasAssertions()`. | The catch only runs if something throws, so this test passes when nothing does. Use `expect(() => f()).toThrow(X)` or `await expect(p).rejects.toThrow(X)`. |
| `no-weak-result-assert` | In test code, a status check (`res.status`, `res.status()`, `res.statusCode`, `status`) that lets a 500 through: `expect([400, 500]).toContain(res.status)` or `expect(res.status).toBeOneOf([..])` with a 5xx in the list; `toBeGreaterThan(OrEqual)` with a value below 500; `.not.toBe(200)` (`toEqual`, `toStrictEqual`; 2xx only). Skipped: `toBe(expected)`, `toBeLessThan(500)`, `.not.toBe(401)` and success lists like `[200, 201]`. | Assert the one status this request should return. A check that accepts 500 passes when the server crashes. |
| `no-weak-result-assert` | A `try` in an `it`/`test` callback whose block ends the happy path with a sentinel (`throw ..`, `fail(..)`, `assert.fail(..)`, `expect.fail(..)`, `expect.unreachable()`) and whose `catch` asserts but does not `throw` or `return`, and has no assertion on the error that the sentinel would fail: none at all, or only `toBeTruthy()`/`toBeDefined()`/`not.toBeNull()`/`not.toBeUndefined()`/`not.toBeFalsy()`/`toBeInstanceOf(Error)`/`assert(e)`/`assert.ok(e)`/`assert.instanceOf(e, Error)`. Skipped with `expect.assertions(n)`/`expect.hasAssertions()`. | Use `await expect(p).rejects.toThrow(X)`. A sentinel thrown in the try is caught by your own catch. |
| `no-test-filter` | `--passWithNoTests` (or `--pass-with-no-tests`) in a `package.json` script; `passWithNoTests: true` in a vite/vitest/jest config or the `jest` key of `package.json`; `testIgnore` at the top level of a Playwright config (in a `projects[]` entry it is skipped: there it hands specs to another project). | Run the whole suite in CI. Fix or delete the test you are filtering out, and let a run that finds no tests fail. |
| `no-assertion-free-test` | An `it`/`test`/`specify` callback with no `expect(..)` (`expect.poll`, `.resolves`/`.rejects` and Playwright web-first assertions included), `assert`/`t.assert` call, `.should(..)`, `*.fail(..)`, Testing Library `getBy*`/`findBy*` query or `throw`, nested callbacks included, that also calls no test-code function that asserts. | This test checks nothing. Assert on the result. If 'does not throw' is the point, say so with an explicit assertion. |

</details>

"Test code" here means a file matching `*.test.*` or `*.spec.*`, or anything under `__tests__/`, `tests/`, `test/` or `e2e/`. `no-test-swap` skips those plus `*.config.*`, `vitest.*` and `__mocks__/`. `no-mock-libs` and `no-coverage-pragma` check every file.

## Known limits

- Directories named `vendor`, `node_modules` and `site-packages` are skipped by `caltrop` (not by a raw `ast-grep scan`): third-party code is not the repo's to judge. This also skips your own `src/vendor/`. Hidden directories (`.venv/`) and gitignored paths (`.svelte-kit/`, `build/`) are skipped too.

### Rust

<details><summary>5 Rust limits</summary>

- A test that runs itself as a child process and returns when its env var is unset is reported by `no-silent-skip`. Give it an allowlist entry.
- Inside macro arguments (`tokio::select!`, `assert!(..)`), any `sleep(..)` or `<path>::sleep(..)` counts, whatever the path.
- A bare `sleep()` counts whatever it was imported from.
- `#[cfg(any(test, ..))]` does not mark test code, since that code also builds outside tests.
- Test files not named `tests.rs` or `*_tests.rs` and not under `tests/` are only scanned inside inline test mods and test functions.

</details>

### Python

<details><summary>32 Python limits</summary>

- `sleep(0)` and `asyncio.sleep(0)` are skipped: they only yield to the event loop. `sleep(inf)` is skipped: it blocks until cancelled. A long sleep used the same way (`await asyncio.sleep(10)` in a handler that should hang, `create_task(asyncio.sleep(1000))`) still counts; use `asyncio.Event().wait()`.
- A sleep wrapper defined in test code (`async def sleep(s): await asyncio.sleep(s)`) is reported once, at its definition; its callers are not.
- `.call_later` counts only on a receiver named `loop` (`self.loop` too) or `get_running_loop()`/`get_event_loop()`. `threading.Timer` is not detected.
- A paced loop in a test server (`for chunk in data: await resp.write(chunk); await asyncio.sleep(0.1)`) is reported by `no-deadline-poll`, though it is not a poll.
- A bare `sleep()` counts only when the file imports it from `time`, `asyncio`, `trio` or `anyio`. `from time import sleep as nap` and `gevent.sleep` are not detected.
- `import unittest` followed by `unittest.mock.patch(..)` is not detected; `import unittest.mock` is.
- `monkeypatch.setattr` counts even when it only patches a constant.
- The assignment check in `no-mock-libs` misses `setattr(mod, ..)`, a lowercase middle name (`os.path.exists = ..`, `flask.g.x = ..` is skipped on purpose), and `os.environ[..] = ..` (a subscript, so not seen; an env var set at module level and never unset leaks too, but `monkeypatch.setenv` is the allowed form). A `setUp` with no `tearDown` is trusted to restore what it sets.
- The assignment check also reports a patch undone by a context manager (`with restore_state(): mod.X = None`) or a write to a stub module a fixture swapped in. Allowlist those.
- A settings attribute named lowercase `testing` (`settings.testing`) is not caught by `no-test-swap`.
- FastAPI `app.dependency_overrides[..] = ..` is not flagged: it passes a dependency in, it does not patch one. What it passes in is still checked (a `Fake*` class is reported by `no-fake-impls`), and a replacement that only raises 401/403 is reported by `no-stubbed-gate`.
- `no-stubbed-gate` only resolves a stub defined in the same file. A raising helper imported from `conftest.py` or a factory (`deny(403)`) is missed. A fixture named only `client` that opens the admin check is not caught: the rule has nothing to compare the name with.
- `@pytest.mark.skipif` on the interpreter or platform (`sys.version_info < (3, 11)`, `sys.platform == "win32"`) is reported like any other skip. Allowlist it if your CI matrix runs the test elsewhere.
- The `as e` exemption in `no-weak-result-assert` accepts any later read of `e.value`, including one that asserts nothing.
- The `pytest.raises` body check looks one `with` deep: a nested `with` whose body is itself one compound statement is allowed.
- The status check in `no-weak-result-assert` sees only a comparison that is the whole `assert` (not `assert a and b`), on a name or attribute ending in `status`/`status_code`. It misses `in range(400, 600)`, a status held in another name, and a test whose only check is `== 500` (in a private FastAPI codebase all 4 such tests patched a failure in on purpose). Permissive success tuples (`in (200, 201)`) are not flagged: they do not accept a crash, though they do hide which code the route returns.
- Tests whose only checks are presence checks (`assert x is not None`, `assert x`, `isinstance`) are not flagged. A draft rule hit 25 tests in food, MAL and CnesData once narrowed to `is not None`; 6 of a 16-test sample were tests where presence is the whole contract ("the claim is accepted", `find_spec(..) is not None`). Too noisy for a ratchet.
- `no-silent-skip` only sees a `return` whose nearest enclosing function is named `test*`, not one in a helper the test calls.
- Wall-clock timing asserts (`assert time.monotonic() - start < 1.0`) are not detected.
- `no-constant-assert` reports `all(..)` only with an `if` filter. An unfiltered `assert all(x.ok for x in xs)` is also true when `xs` is empty, but in fastapi, poetry and typer most such `xs` were constants or were checked another way (a set or list comprehension compared to a literal), so it is skipped.
- `no-constant-assert` only sees literal and self-compare forms. `assert x is x`, `self.assertEqual(x, x)`, `assert isinstance(x, object)` and `assert x == x` where `x` is a subscript (`c[0] == c[0]`) are not detected.
- `no-coverage-pragma` only reads comments. Exclusions in coverage config (`exclude_lines`/`exclude_also` in `.coveragerc`, `setup.cfg` or `pyproject.toml`, `omit`) are not read, and nor is a low `fail_under`.
- `no-coverage-pragma` cannot judge the reason. A pragma on code a test cannot reach (an `if __name__ == "__main__":` block, an alembic migration, a Windows-only branch, an optional-import fallback) is reported like any other; allowlist it. A `Protocol` method with a `pass` or `raise NotImplementedError` body is reported too (only a `...` body is skipped).
- `no-source-text-test` only sees a source path written in the read call itself. A path built in a variable on another line (`p = REPO / "x.py"`, then `p.read_text()`) is missed. Static guards that parse the source on purpose (`ast.parse(..)` to check imports) are reported; allowlist them.
- `no-conditional-assert` also reports an `if` that is a deliberate implication (`if a != b: assert marks`, "when it diverges, a trace is logged") and an `if` whose block runs setup that happens to assert. Assert the condition first, or allowlist it.
- `no-swallowed-error` only checks code directly in a `test*` function, so a swallowed error in a helper, a thread worker or a nested `def` is missed. `except ..: continue` is not flagged: in parse and retry loops it skips bad input.
- `no-swallowed-error` also flags a handler for the test's own sentinel exception (`raise Stop()` to end a run early) and `except E: pass` followed by an assert that fails anyway when `E` is raised. Allowlist those.
- `no-assertion-free-test` matches helpers by name only: a test that calls `run(..)` is skipped if any function named `run` in test code asserts. A helper outside test code, or in a file this Python cannot parse, is not seen, so a test whose only check lives there is reported. Allowlist it, or move the helper into test code.
- `no-test-filter` does not report `-m` in `addopts` (selecting by marker is how a suite is split into CI jobs) or `xfail_strict = false` (the default; every xfail is already reported by `no-ignored-test`).
- A test that only checks that nothing raises is reported by `no-assertion-free-test`. That is on purpose: write the check out (`assert validate(x) is None`), so a reader sees it is the point.
- `no-fake-impls` skips a class defined in a test that has a base class: a subclass of the real class that adds counting (`class CountingMailer(SmtpMailer)`) is allowed, and so is a subclass of a framework extension point under test (`class TimedRoute(APIRoute)`). A fake that subclasses an abstract base in a test (`class Down(Mailer)`) is missed too, unless its name or its base's name gives it away. Classes defined in a fixture or helper, rather than in the `test*` function, are only checked by name.
- `no-fake-impls` reports a duck-typed input defined in a test with a named method, as in a library's own tests (a file-like `BoomFile` with a failing `tell()`, a module stand-in with `create_app()`). That is a hand-written stand-in too; allowlist the ones you keep.

</details>

### TypeScript, JavaScript and Svelte

<details><summary>28 TypeScript, JavaScript and Svelte limits</summary>

- Playwright's conditional `test.fail(cond, ..)` counts as `no-ignored-test`, like a conditional `pytest.mark.xfail(cond)`, while a conditional `test.skip(cond, ..)` counts as `no-silent-skip`. An expected failure passes while the code is broken whatever the condition.
- An empty `waitFor` is only caught when the callback is literally empty or returns a literal. `waitFor(() => ready)` or a callback that calls something without asserting is not flagged.
- A `.svelte` `<script>` without `lang="ts"` is parsed as JavaScript, and only `no-test-swap` and `no-coverage-pragma` have a JavaScript copy (`*-js.yml`). Test files are `.ts`/`.js`, so the test rules still apply to them.
- Any file under a `test/`, `tests/` or `e2e/` directory counts as test code, so a production route such as `src/routes/test/+page.svelte` is skipped by `no-test-swap`.
- JSX inside a `.js` file is parsed as TypeScript and its JSX parts are not checked.
- In a Svelte template, `no-test-swap` reports one hit per run of text between tags, so two test checks there count once. Template text is matched by regex inside `{..}`, not parsed.
- A spy assigned in a hook (`let s; beforeEach(() => { s = vi.spyOn(..) })`) and given a mock return value in another block is not caught by `no-mock-libs`.
- The fake-timer skip is per file: a real sleep in a file where any test calls `useFakeTimers` is missed.
- `vi.stubGlobal` of non-network globals (`localStorage`, `Date`) is not flagged. In a node test environment it is often the only way to provide a global, or to remove `document`/`window` to test the no-DOM path.
- Playwright skips on a project setting (`test.skip(browserName !== 'chromium')`, `test.skip(!javaScriptEnabled)`) count as `no-silent-skip`, even when the test cannot apply to that project: the same line also hides a failure on one browser. Allowlist the deliberate ones.
- Sleeps in fixture app code under `test/` count too, e.g. a `+page.server.js` that delays a streamed promise on purpose.
- Production code that is itself test tooling (a Vite plugin or test runner reading `VITEST`/`JEST_WORKER_ID`, a library's own WebSocket mock assigned to `globalThis.WebSocket`) is reported. Allowlist it.
- `no-silent-skip` only checks prerequisite-style conditions, so `if (!el) return;` in a test is not caught.
- `no-constant-assert` skips `expect(x[0]).toBe(x[0])`, `expect(x).toBeGreaterThan(-1)`, `assert.equal(x, x)` and `assert.strictEqual(1, 1)`; it only sees `expect` literal subjects, self-compares on a name or property path, and `assert(true)`/`assert.ok(true)`.
- `no-coverage-pragma` only reads comments: `coverage.exclude` in a vitest config, jest `coveragePathIgnorePatterns`, c8/nyc `exclude` and low `thresholds` are not read. It cannot judge the reason either, so an ignore around entry-point wiring (`if (import.meta.main)`) is reported; allowlist it. A comment in a Svelte template (`<!-- istanbul ignore -->`) is not checked.
- `no-source-text-test` only sees a source path written in the read call itself. A path built in a variable on another line (`const p = join(__dirname, 'a.ts')`, then `readFileSync(p)`) is missed. Text that is read and then partly run (a regex sliced out of the source and passed to `new Function`) is still reported.
- `no-conditional-assert` reports a deliberate implication too (`if (literal) expect(url).toContain(SEGMENT)`, where the other case is legal and checked elsewhere). Narrowing counts only when the earlier `expect(..)` has exactly a value from the condition: `expect(r).toMatchObject({ ok: true }); if (r.ok)` is skipped through `r`, but `expect(r.kind === 'x').toBe(true); if (r.kind === 'x')` is not.
- `no-swallowed-error` only checks code inside an `it`/`test` callback and only an awaited `.catch(..)` or a `try` that awaits. It misses a swallowed sync call (`try { parse(x) } catch {}`), a floating `void f().catch(() => {})`, helpers outside the test, and e2e scripts that do not use `it`/`test`.
- `no-swallowed-error` flags `await p.catch(() => null)` on a promise the test already checked, and a `.catch(() => {})` in a mock implementation inside a test that imitates a retry. Allowlist those.
- The sentinel check in `no-weak-result-assert` judges the catch by its matchers, not by values: `expect(e.message).toMatch(/throw/)` passes on a sentinel whose message says "expected to throw" and is not flagged. A sentinel inside an `if` in the `try` is not seen.
- A constant predicate in `no-constant-assert` is seen only as an arrow whose body is `true` or `false` (`() => { return true }` and `function () { return true }` are missed), and a `.filter`/`.find` method on the code under test (`repo.find(() => true)`) inside an `expect(..)` is reported like an array method.
- The catch-only check in `no-weak-result-assert` sees `try`/`catch`, not `.catch(e => expect(..))` on a promise, and not a `try` inside a helper the test calls.
- The status check in `no-weak-result-assert` misses `expect(res.ok).toBe(false)`, `expect([400, 500].includes(res.status)).toBe(true)`, a status held in another name, and `toBe(500)` as a test's only check. Success lists (`[200, 201]`) are not flagged.
- Tests whose only checks are `toBeTruthy()`, `toBeDefined()`, `not.toBeNull()` or `not.toBeUndefined()` are not flagged. A draft rule that skipped Testing Library `getBy*`/`findBy*`/`queryBy*` and `querySelector` subjects still hit 57 tests in food, evia-manager and claude-orchestrator, and 6 of a 15-test sample were fine: presence was the contract ("rows are not swept", "each category is accepted") or a helper did the asserting.
- `no-assertion-free-test` matches helpers by name only, the same way as in Python, and only sees helpers that assert directly: a helper that asserts through another helper, or one outside test code, does not count. A Playwright `page.getByRole(..)` alone is not an assertion (it does not throw); Testing Library's `getBy*` is.
- `fit`/`fdescribe` count only as a statement whose first argument is a string or template and whose second, if any, is an inline function, since `fit` is also a common function name (`expect(fit(a, b))`). A focused test with a named callback (`fit('x', run)`) is missed.
- `no-test-filter` does not read `--passWithNoTests` passed from a script file (`spawn('vitest', ['--passWithNoTests'])`), nor `exclude`/`testPathIgnorePatterns`, which usually skip non-test files.
- `no-fake-impls` checks classes declared directly in an `it`/`test`/`specify` callback, not in `describe`, a hook or a helper, and skips any with `extends` (an instrumented subclass of the real class is allowed; a fake extending an abstract class is missed unless a name gives it away). An object literal fake (`{ send: async () => false }`) is not a class and is not detected.

</details>

## Pinning

Rule changes change the counts, and both too many and too few hits fail. So a consumer repo pins caltrop to a release tag, and pins ast-grep too. The version number says what a bump does to the counts: a PATCH never changes them, a MINOR can, a MAJOR can also need changes to `caltrop.toml` or CI. Bump the pin in its own PR and fix the new hits or lower the allowances there. See [docs/versions.md](docs/versions.md) for the scheme and how a release is cut.

The tag goes in `uses: Toby-Faucher/caltrop@<tag>`, the pre-commit `rev:` or the pipx URL. The action and the hook pin ast-grep for you. Without the action (v1.0.0, or another CI), clone outside the checkout so caltrop itself is not scanned:

```yaml
env:
  CALTROP_REF: v1.0.0
steps:
  - uses: actions/checkout@v4
  - run: |
      git clone https://github.com/Toby-Faucher/caltrop "$RUNNER_TEMP/caltrop"
      git -C "$RUNNER_TEMP/caltrop" checkout "$CALTROP_REF"
      pipx install ast-grep-cli==0.44.1
      echo "$RUNNER_TEMP/caltrop" >> "$GITHUB_PATH"
  - run: caltrop check
```

## Tests

```
ast-grep test -c sgconfig.yml --skip-snapshot-tests
python3 -m unittest discover -s tests -v
```

CI also runs `./caltrop check .` on this repo; `caltrop.toml` allows only the deliberate dirty fixture.

To add a rule or a language, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Credit

The approach is modelled on [landmines](https://github.com/interfere-inc/landmines) by interfere-inc.

## License

MIT. See [LICENSE](LICENSE).
