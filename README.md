# caltrop

caltrop fails your check when a Rust test takes a shortcut that coding agents like. It flags sleeping instead of waiting for an event, polling until a deadline, swapping behaviour under `cfg(test)`, mock crates, and nextest retries. Each failure says what to do instead, so the agent can fix it in the same loop. It is built on [ast-grep](https://ast-grep.github.io) rules plus a small Python script, and it is modelled on [landmines](https://github.com/interfere-inc/landmines), which does the same job for TypeScript.

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

Rule ids are stable. They key the allowlist.

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

## Known limits

- Directories named `vendor` are skipped by `caltrop` (not by a raw `ast-grep scan`): vendored third-party code is not the repo's to judge. This also skips your own `src/vendor/`.
- A test that runs itself as a child process and returns when its env var is unset is reported by `no-silent-skip`. Give it an allowlist entry.
- Inside macro arguments (`tokio::select!`, `assert!(..)`), any `sleep(..)` or `<path>::sleep(..)` counts, whatever the path.
- A bare `sleep()` counts whatever it was imported from.
- `#[cfg(any(test, ..))]` does not mark test code, since that code also builds outside tests.
- Test files not named `tests.rs` or `*_tests.rs` and not under `tests/` are only scanned inside inline test mods and test functions.

## Pinning in CI

Rule changes change the counts, and both too many and too few hits fail. So a consumer repo pins caltrop to a commit, and pins ast-grep too. Bumping the pin means re-running `caltrop baseline` or fixing hits in the same PR.

```yaml
env:
  CALTROP_REF: <commit sha>
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
