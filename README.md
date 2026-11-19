# caltrop

caltrop fails your check when a test takes a shortcut that coding agents like. It covers Rust, Python, and TypeScript/JavaScript including Svelte components. It flags sleeping instead of waiting for an event, polling until a deadline, swapping behaviour under test, mocks, skipped tests and retries. Each failure says what to do instead, so the agent can fix it in the same loop. It is built on [ast-grep](https://ast-grep.github.io) rules plus a small Python script, and it is modelled on [landmines](https://github.com/interfere-inc/landmines).

## Install

You need ast-grep 0.44.1 and Python 3.11 or newer (standard library only).

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
caltrop check [REPO_DIR]      # default: current directory
caltrop baseline [REPO_DIR]   # write caltrop.toml from the current hits
```

`check` scans the repo, counts hits per rule and file, and compares them with `caltrop.toml` at the repo root. Exit codes: 0 pass, 1 violations, 2 usage or tool error (ast-grep missing, bad TOML).

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

Rule ids are stable. They key the allowlist. Each language has its own rule files, but a rule that means the same thing in every language shares one id: a Python sleep and a Rust sleep both count under `no-fixed-sleep`. The rule files carry a language suffix (`no-fixed-sleep-py.yml`, `no-test-swap-ts.yml`) that `caltrop` strips.

### Rust

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

"Test code" means a `.rs` file under a `tests/` directory, a file named `tests.rs` or `*_tests.rs`, or code inside a `mod` or `fn` whose attributes include `#[cfg(test)]`, `#[cfg(all(.., test, ..))]`, `#[test]` or `#[<path>::test]` (other attributes and comments may sit between them). `no-test-swap` skips both. Sleep calls are `sleep`, `sleep_until`, and those names under `thread::`, `std::thread::`, `time::`, `tokio::time::`, `task::` and `async_std::task::`.

Name files that `#[cfg(test)] mod x;` pulls in `tests.rs` or `*_tests.rs` (for example `view_tests.rs`), so they are scanned.

A loop search stops at closures, `async` blocks and function boundaries. A sleep inside `tokio::spawn(async move { .. })` counts as `no-fixed-sleep`, even if that block sits in a loop.

### Python

| id | Matches | Message |
|---|---|---|
| `no-fixed-sleep` | In test code, outside a loop: `time.sleep`, `asyncio.sleep`, `trio.sleep` or `anyio.sleep`, or a bare `sleep(..)` in a file that does `from time/asyncio/trio/anyio import sleep`. `sleep(0)` is skipped. | Await the operation or an event it emits (`asyncio.Event`, a queue, a future). To prove something did not happen, send a sentinel after it and wait for the sentinel. For timers or timestamps, inject the clock or freeze time (`time-machine`, `freezegun`). |
| `no-deadline-poll` | The same sleeps inside `while` or `for` (including `async for`) in test code. The loop search stops at `def`, `lambda` and `class`. | Wait on a signal (`asyncio.Event`, `asyncio.Condition`, a queue, `threading.Event.wait()`), not on a deadline. |
| `no-test-swap` | Outside test code: `"pytest"`/`"unittest" in sys.modules` (or `sys.argv`), `sys.modules.get("pytest")`; a test key (`PYTEST*`, `TEST`, `TESTS`, `TESTING`, with prefixes like `IS_`/`RUNNING_` or suffixes `_MODE`/`_ENV`) read through `getenv`, `environ`, `config[..]`, `settings[..]`, `hasattr`/`getattr`; attributes like `.TESTING` or `.is_testing` (lowercase `.testing` is skipped: `np.testing` is a module); an env-style name (`ENV`, `APP_ENV`, `settings.environment`, `config["ENV"]`) compared with `"test"` or `"testing"`. | Production code must behave the same under test. Pass the dependency or setting in instead of checking whether a test is running. |
| `no-mock-libs` | Imports of `unittest.mock`, `mock` or `pytest_mock` (except `from unittest.mock import sentinel`), any `mocker.*(..)` call, and `monkeypatch.setattr(..)`. | Use the real implementation, not a mock or a patched attribute. Pass the dependency in. For HTTP, a real local server (`pytest-httpserver`, a uvicorn app on a free port) is fine. `monkeypatch.setenv`, `chdir` and `syspath_prepend` are fine. |
| `no-test-retries` | `pytest.mark.flaky` and the `flaky` package's `@flaky` in test code; `--reruns N` in `addopts`, or `reruns = N` (N > 0), in the pytest section of any `pyproject.toml`, `pytest.ini`, `setup.cfg` or `tox.ini` in the repo. | Make the test deterministic; a retry hides the flake. |
| `no-ignored-test` | `pytest.mark.skip`, `pytest.mark.xfail`, `unittest.skip` or `unittest.expectedFailure`, as a decorator, in `pytestmark` or in `pytest.param(marks=..)`. | An ignored test never runs in CI, and an xfail passes whether or not it fails. Make it run (fixture, dependency or a CI job), or delete it. |
| `no-silent-skip` | In test code: any `pytest.skip(..)`, `pytest.importorskip(..)` or `self.skipTest(..)`; `@pytest.mark.skipif`, `unittest.skipIf`/`skipUnless`; a `return` whose nearest function is `test*`, under an `if` with a negated or `is None` check on a prerequisite (`which`, `exists`, `environ`, `getenv`, `find_spec`, `*available` and similar) or in an `except ImportError` block. Each return is one hit, however many guards wrap it. | A test must not skip or return early when a prerequisite is missing. Provide the prerequisite in CI, and fail with a clear message if it is absent. |
| `no-fake-impls` | In test code, a `class` named `Mock`, `Fake`, `Stub`, `Spy` or `Dummy` (leading `_` allowed, alone or followed by a capital, digit or `_`), with or without a base class. Exception, Error and Warning subclasses are skipped. | Use the real implementation. A hand-written fake class that stands in for a real type is a mock, with or without a base class. A real local server on a socket is fine. |
| `no-weak-result-assert` | `pytest.raises(Exception)`, `pytest.raises(BaseException)` or `self.assertRaises(Exception)` with no `match=`. | Assert which error. Raise and catch the specific exception type (`pytest.raises(ValueError, match=..)`), not `Exception`, which passes on any bug. |

"Test code" in Python means a file named `test_*.py`, `*_test.py` or `conftest.py`, or any file under a `tests/` or `test/` directory. `no-test-swap` checks only the other files; `no-mock-libs` checks every file.

### TypeScript, JavaScript and Svelte

The rules are written for TypeScript. `sgconfig.yml` parses `.js`, `.mjs`, `.cjs`, `.mts` and `.cts` as TypeScript, and parses `.svelte` files as HTML, so the rules also run inside a component's `<script>` block.

| id | Matches | Message |
|---|---|---|
| `no-fixed-sleep` | In test code, outside a loop: `new Promise(r => setTimeout(r, n))` (arrow, function and block forms, `window.setTimeout`); `sleep`/`delay`/`wait`/`pause(n)` with a nonzero number or a duration-like name (`ms`, `*Ms`, `*_timeout`, `ALL_CAPS`); `await setTimeout(n)` from `timers/promises`; `x.waitForTimeout(..)`. A delay of `0`, a bare `setTimeout(cb, n)` and the sleep helper's own definition are skipped, and so is any file that calls `vi.useFakeTimers` or `jest.useFakeTimers`. | Await the operation or an event it emits; for UI use `waitFor`/`findBy*` or Playwright's auto-waiting `expect(..)`. For timers, use `vi.useFakeTimers()` and `vi.advanceTimersByTime`. To prove something did not happen, wait for a later sentinel instead. |
| `no-deadline-poll` | The same sleeps inside `for`/`for..of`/`while`/`do` in test code, skipping fake-timer files the same way. The search stops at the nearest function or callback. | Wait on a signal (an event, a promise the code resolves, `expect.poll`/`waitFor` on the real condition), not a sleep in a loop. |
| `no-test-swap` | Outside test code and tool config: a read of `import.meta.env.VITEST` or `process.env.VITEST`/`VITEST_WORKER_ID`/`JEST_WORKER_ID`, or `import.meta.env.MODE`/`process.env.NODE_ENV` compared with `'test'`. `DEV`, `PROD`, `$app/environment` `dev`, `import.meta.vitest` and assignments are skipped. | Production code must behave the same under test. Pass the dependency in (a parameter, a context, a constructor argument) and give the test a real one. `dev`/`DEV`/`PROD` are fine; they are not test switches. |
| `no-mock-libs` | `vi`/`jest` `.mock`, `.doMock`, `.unstable_mockModule`; `vi.stubGlobal` of `fetch`/`XMLHttpRequest`/`WebSocket`/`EventSource`; `globalThis.fetch = vi.fn()`; the first `.mockImplementation/ReturnValue/ResolvedValue/RejectedValue(Once)` on a `vi.spyOn`/`jest.spyOn`; imports of `sinon`, `ts-mockito`, `testdouble`, `jest-mock-extended`, `vitest-mock-extended`, `fetch-mock`, `jest-fetch-mock`, `vitest-fetch-mock`. Skipped: `vi.fn()`, `vi.mocked`, spies on `console`, pass-through spies, msw, nock. | Use the real implementation; pass dependencies in instead of replacing modules or globals. For HTTP, use a real local server or msw (it serves real Responses to the real fetch). A `vi.fn()` callback spy is fine. |
| `no-test-retries` | `retry`/`retries` with a nonzero literal (including `CI ? 2 : 0`) in the `test:` object of a vite/vitest config, at the top level of a Playwright config, or in a `projects[]` entry (plugin and dev-server retry options are skipped); an options object passed to `it`/`test`/`describe`/`test.describe.configure`; `this.retries(n)`; `jest.retryTimes(n)`. | Make the test deterministic; a retry hides the flake. |
| `no-ignored-test` | `xit`/`xtest`/`xdescribe`; any `.todo`; `.skip`/`.fixme` with no arguments or with a test body, including `.concurrent.skip`, `test.describe.skip` and `it.skip.each(..)`. | A skipped or todo test never runs in CI. Make it run (fixture, real dependency or a CI job), or delete it. |
| `no-focused-test` | `.only` on `it`/`test`/`describe` and friends (`.only.each` too), `fit`, `fdescribe`. | `.only` silently skips every other test in the file. Remove it. |
| `no-silent-skip` | `.skipIf(..)`/`.runIf(..)`; Playwright's conditional `test.skip(cond, ..)`/`test.fixme(cond)`; `ctx.skip()`/`context.skip()`/`t.skip()`/`this.skip()`/bare `skip()` in a test body; an `if (!..)` on a prerequisite (`existsSync`, `process.env`, `import.meta.env`, `*Available`, `*Installed`, `ready`, `which`, `find*` and similar) whose branch does a bare `return` or `return console.x(..)` in an `it`/`test` callback. | A test must not skip itself when a prerequisite is missing; it reports a pass or a skip that nobody reads. Provide the prerequisite in CI and fail with a clear message if it is absent. |
| `no-fake-impls` | In test code, a class named `Mock`/`Fake`/`Stub`/`Spy`/`Dummy` (alone, or followed by a capital, digit or `_`) with `implements` or `extends`. | Use the real implementation. A hand-written fake class that stands in for an interface or base class is a mock. A real local server on a socket is fine. |
| `no-weak-result-assert` | `.toThrow()`/`.toThrowError()` with no argument, including `.rejects.`, but not `.not.toThrow()`; `assert.throws(fn)`/`assert.rejects(p)` with one argument. | Assert which error: pass the class, a message regex or a matcher, e.g. `toThrow(NotFoundError)`, `rejects.toThrow(/timed out/)`. A bare `toThrow()` passes on any error, including a TypeError from a typo. |

"Test code" here means a file matching `*.test.*` or `*.spec.*`, or anything under `__tests__/`, `tests/`, `test/` or `e2e/`. `no-test-swap` skips those plus `*.config.*`, `vitest.*` and `__mocks__/`. `no-mock-libs` checks every file.

## Known limits

- Directories named `vendor`, `node_modules` and `site-packages` are skipped by `caltrop` (not by a raw `ast-grep scan`): third-party code is not the repo's to judge. This also skips your own `src/vendor/`. Hidden directories (`.venv/`) and gitignored paths (`.svelte-kit/`, `build/`) are skipped too.

### Rust

- A test that runs itself as a child process and returns when its env var is unset is reported by `no-silent-skip`. Give it an allowlist entry.
- Inside macro arguments (`tokio::select!`, `assert!(..)`), any `sleep(..)` or `<path>::sleep(..)` counts, whatever the path.
- A bare `sleep()` counts whatever it was imported from.
- `#[cfg(any(test, ..))]` does not mark test code, since that code also builds outside tests.
- Test files not named `tests.rs` or `*_tests.rs` and not under `tests/` are only scanned inside inline test mods and test functions.

### Python

- `sleep(0)` and `asyncio.sleep(0)` are skipped: they only yield to the event loop.
- A bare `sleep()` counts only when the file imports it from `time`, `asyncio`, `trio` or `anyio`. `from time import sleep as nap` and `gevent.sleep` are not detected.
- `import unittest` followed by `unittest.mock.patch(..)` is not detected; `import unittest.mock` is.
- `monkeypatch.setattr` counts even when it only patches a constant.
- A settings attribute named lowercase `testing` (`settings.testing`) is not caught by `no-test-swap`.
- FastAPI `app.dependency_overrides[..] = ..` is not flagged: it is the framework's own way to pass a dependency in.
- `no-silent-skip` only sees a `return` whose nearest enclosing function is named `test*`, not one in a helper the test calls.
- Wall-clock timing asserts (`assert time.monotonic() - start < 1.0`) are not detected.

### TypeScript, JavaScript and Svelte

- `.tsx` and `.jsx` files are not scanned; tsx is a separate ast-grep language.
- A `.svelte` `<script>` without `lang="ts"` is parsed as JavaScript, and only `no-test-swap` has a JavaScript copy (`no-test-swap-js.yml`). Test files are `.ts`/`.js`, so the test rules still apply to them.
- Any file under a `test/`, `tests/` or `e2e/` directory counts as test code, so a production route such as `src/routes/test/+page.svelte` is skipped by `no-test-swap`.
- JSX inside a `.js` file is parsed as TypeScript and its JSX parts are not checked.
- Svelte template logic (`{#if import.meta.env.MODE === 'test'}`) is not checked, only `<script>`.
- A spy set up in two steps (`const s = vi.spyOn(..); s.mockReturnValue(..)`) is not caught by `no-mock-libs`.
- The fake-timer skip is per file: a real sleep in a file where any test calls `useFakeTimers` is missed.
- `vi.stubGlobal` of non-network globals (`localStorage`) is not flagged.
- `no-silent-skip` only checks prerequisite-style conditions, so `if (!el) return;` in a test is not caught.

## Pinning in CI

Rule changes change the counts, and both too many and too few hits fail. So a consumer repo pins caltrop to a release tag, and pins ast-grep too. The version number says what a bump does to the counts: a PATCH never changes them, a MINOR can, a MAJOR can also need changes to `caltrop.toml` or CI. Bump the pin in its own PR and fix the new hits or lower the allowances there. See [docs/versions.md](docs/versions.md) for the scheme and how a release is cut.

```yaml
env:
  CALTROP_REF: v1.0.0
steps:
  - uses: actions/checkout@v4
  # Clone outside the checkout so caltrop itself is not scanned.
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

## Credit

The approach is modelled on [landmines](https://github.com/interfere-inc/landmines) by interfere-inc.

## License

MIT. See LICENSE.
