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
| `no-test-swap` | `cfg!(test)`, `cfg!(not(test))` and `#[cfg(not(test))]` outside test code. | Production code must behave the same under test. Pass the dependency in instead. |
| `no-mock-crates` | `use` of `mockall`, `mockers`, `faux` or `mry`; `#[automock]` and similar attributes; `mock!`. | Use the real implementation. For HTTP, a real local server (`wiremock`, `httpmock` are fine). |
| `no-test-retries` | `retries` above 0 in any profile or override of `.config/nextest.toml`. | Make the test deterministic; a retry hides the flake. |

"Test code" means a `.rs` file under a `tests/` directory, a file named `tests.rs` or `*_tests.rs`, or code inside a `mod` marked `#[cfg(test)]`. `no-test-swap` skips both. Sleep calls are `sleep`, `sleep_until`, and those names under `thread::`, `std::thread::`, `time::`, `tokio::time::`, `task::` and `async_std::task::`.

Name files that `#[cfg(test)] mod x;` pulls in `tests.rs` or `*_tests.rs` (for example `view_tests.rs`), so they are scanned.

A loop search stops at closures, `async` blocks and function boundaries. A sleep inside `tokio::spawn(async move { .. })` counts as `no-fixed-sleep`, even if that block sits in a loop.

## Known limits

- ast-grep sees macro bodies as token trees. Code inside `tokio::select!`, `assert!(..)` and similar is invisible.
- A bare `sleep()` counts whatever it was imported from.
- `#[test]` functions outside `tests/` and `#[cfg(test)]` mods are not seen.
- `#[cfg(test)]` must be the attribute directly above `mod`. A stacked `#[cfg(test)] #[allow(..)] mod` is missed.
- Compound forms such as `cfg(all(not(test), unix))` are not matched.
- `cfg!(test)` inside a `#[cfg(test)] fn` (not a mod) is reported as `no-test-swap`.
- A test mod marked `#[cfg(all(test, ..))]`, or with a doc comment between `#[cfg(test)]` and `mod`, is not recognised.
- Test files not named `tests.rs` or `*_tests.rs` and not under `tests/` are only scanned inside inline `#[cfg(test)]` mods.

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
