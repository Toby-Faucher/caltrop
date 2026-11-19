> Historical record: written before v1.0.0; README.md and docs/versions.md are current.

# caltrop: design

Date: 2026-11-17. Status: approved by Toby.

## Intent

caltrop is a guardrail for Toby's own Rust repos (first vesper and lemonate). It fails the
check when a test takes one of the shortcuts coding agents use to get a green run: sleeping
instead of waiting for an event, polling until a deadline, swapping behaviour under
`cfg(test)`, mocking crates, retries. Every failure message says what to do instead, so the
agent fixes it in the same loop.

It is modelled on [interfere-inc/landmines](https://github.com/interfere-inc/landmines)
(Oxlint rules for TypeScript), adapted to Rust. It is a separate project with its own repo.

Why: agents write most of the commits in these repos (vesper: 458 commits co-authored by
Claude). vesper's history shows the cost: `fbc6325` fixed two flaky signaling tests, and
`25e4ed2` replaced a 1 s sleep with a 60 s polling loop after "a fixed sleep was too short
under CPU load".

## Goals

- Catch, in test code, the patterns listed under Rules.
- A per-repo allowlist with exact counts per file and rule, which can only shrink, so a repo
  adopts caltrop on day one and pays the debt down later.
- One command a repo calls from its check script and CI.
- Failure messages that name the fix.

## Non-goals

- Publishing to crates.io or supporting other people's repos. Own repos only.
- Fixing the existing hits in vesper and lemonate. Adoption allowlists them; fixing is
  separate work.
- Helper crates for the fixes (sentinel helpers, clock injection). Messages point at
  existing tools instead.
- Clippy configuration. vesper already sets the useful lints in `[workspace.lints]`; the
  sleep rule below is scoped to tests, which clippy's `disallowed-methods` cannot be.
- Rules beyond the list below (for example "`is_err()` must check which error": 133 hits
  today, too noisy for v1).
- Style rules from landmines (no comments, no explicit return types, file naming).

## Anti-goals

- A rule that fires on legitimate production code. Rules run on test code only, except the
  `cfg(test)` swap rule, which targets production code by definition.
- An allowlist that can grow silently. More hits than allowed fails; fewer hits than allowed
  also fails until the count is lowered.

## Constraints

- Approach A, picked by Toby: ast-grep rules plus a small script. Not a `syn` binary.
- ast-grep 0.44 (Arch `extra/ast-grep`; on this machine install it without root, e.g.
  `cargo install ast-grep --locked`, or through `sudoq` for pacman).
- The script uses Python 3 standard library only (`tomllib` needs 3.11+; this machine has
  3.14).
- vesper rules from its `CLAUDE.md` apply when adopting there: builds through
  `scripts/capped.sh`, `scripts/check.sh` must pass, plain wording.
- ast-grep sees macro bodies as token trees, so code inside `tokio::select!`, `assert!(..)`
  and similar is not matched. Accepted for v1.

## Approaches considered

- **A. ast-grep rules plus a counting script (picked).** A few days. YAML rules, built-in
  rule tests (`ast-grep test`), a Python script for the allowlist. Weak spots: test-context
  matching in YAML is fiddly; macro bodies are invisible.
- **B. A `syn`-based Rust binary.** One to two weeks. Exact test detection, plain Rust.
  More code than a guardrail for own repos needs. The rules port over unchanged if A
  outgrows YAML.
- **C. Clippy config only.** Hours, but cannot tell test code from production code and
  misses polling, sleeps that prove nothing happened, and `cfg(test)` swaps, which are the
  issues found in vesper.

## Test context

"Test code" means either:

1. any `.rs` file under a `tests/` directory (any depth, e.g. `crates/x/tests/foo.rs`,
   `tests/common/mod.rs`), or
2. code inside a `mod` item carrying `#[cfg(test)]`.

`#[test]` functions outside those two places are rare in these repos and are not detected in
v1 (builder: confirm with a grep during tuning).

## Rules

Rule ids are stable; they key the allowlist.

| id | Matches | Message (the fix) |
|---|---|---|
| `no-fixed-sleep` | `std::thread::sleep`, `thread::sleep`, `tokio::time::sleep`, `time::sleep`, bare `sleep(..)` when imported from those, in test code, **not** inside a loop. | Await the operation or an event it emits. To prove something did not happen, send a sentinel after it and wait for the sentinel. For timers, use `#[tokio::test(start_paused = true)]`. For distinct timestamps, inject the clock. |
| `no-deadline-poll` | The same sleep calls inside a `loop`, `while` or `for` in test code (covers `wait_until`-style helpers). | Wait on a signal (`tokio::sync::Notify`, `watch`, a channel, an event stream), not on a deadline. |
| `no-test-swap` | `cfg!(test)` and `#[cfg(not(test))]` anywhere outside test code. | Production code must behave the same under test. Pass the dependency in instead. |
| `no-mock-crates` | `use mockall..`, `#[automock]`, `mock!{..}`, and the same for `mockers`, `faux`, `mry`. | Use the real implementation. For HTTP, a real local server (`wiremock`, `httpmock` are fine). |
| `no-test-retries` | Script check, not ast-grep: `retries` > 0 in any profile or override of `.config/nextest.toml`. | Make the test deterministic; a retry hides the flake. |

**The rule definitions are the target, not the hit list below.** The list came from a partial
scan; where a rule finds more real cases (the builder check found `signaling.rs:1038`,
`:1781` and `forwarding.rs:479` as further deadline polls), the list is updated, not the
rule bent. (Claude's call.)

**Loop search stops at closures and `async` blocks** (Claude's call). A sleep inside
`tokio::spawn(async move { .. })` that sits in a loop is not that loop's poll: it counts as
`no-fixed-sleep`, not `no-deadline-poll`. Example: the fake push server in
`crates/vesper-server/tests/push.rs:69` holds a connection open with a 3600 s sleep; it is
a `no-fixed-sleep` hit and gets allowlisted.

Existing hits these should produce (partial acceptance reference, from the 2026-11-17 scan):

- vesper `no-fixed-sleep`: `crates/vesper-server/tests/push.rs:254`, `signaling.rs:1052`,
  `:2381`, `:2472`, `crates/vesper-sfu/tests/forwarding.rs:583`, `:594`, `:720`, `:723`,
  `crates/vesper-server/tests/cli.rs:491`, `uploads.rs:688`, plus the deliberate slow-client
  sleeps in `crates/vesper-server/tests/timeouts.rs` (allowlisted, they are the subject).
- vesper `no-deadline-poll`: `signaling.rs:282` (`wait_until`), the `wait_until` in
  `forwarding.rs`, `push.rs:705`, `cli.rs:546`, `:562`, `:608`.
- lemonate `no-fixed-sleep`: `src/search/time_manager.rs:590, 683, 694, 827`.
- lemonate `no-deadline-poll`: `tests/uci.rs:65` (a kill deadline; allowlisted).
- `no-test-swap`, `no-mock-crates`, `no-test-retries`: none in either repo.

Production sleeps (`vesper-server/src/lib.rs:322`, `voice.rs:664`,
`vesper-loadtest`, lemonate `src/uci/handler.rs:225`) must **not** be reported.
(`uploads.rs:493` was listed here first, but it sits in a `#[cfg(test)] mod` test helper, so it is a correct `no-fixed-sleep` hit.)

## The command

```
caltrop check [REPO_DIR]      # default: current directory
caltrop baseline [REPO_DIR]   # write caltrop.toml from the current hits
```

`check` runs `ast-grep scan` with caltrop's rules over `REPO_DIR` (JSON output), adds the
nextest retries check, counts hits per (rule, file), and compares with `REPO_DIR/caltrop.toml`:

- count > allowed: fail, print each hit as `file:line: rule: message`.
- count < allowed: fail, print "lower the allowance for <rule> in <file> to <n>".
- allowlist entry for a file that no longer exists: fail, same wording.
- otherwise exit 0 with a one-line summary.

Exit codes: 0 pass, 1 violations, 2 usage or tool error (ast-grep missing, bad TOML).

`baseline` writes the current counts, sorted, overwriting `caltrop.toml`. Used once at
adoption.

Allowlist format (`caltrop.toml` at the repo root):

```toml
[allow.no-fixed-sleep]
"crates/vesper-server/tests/timeouts.rs" = 5
"crates/vesper-server/tests/push.rs" = 1
```

## Repo layout (caltrop)

```
caltrop/
  caltrop              # the Python script, executable
  sgconfig.yml         # ast-grep project config pointing at rules/ and rule-tests/
  rules/*.yml          # one file per ast-grep rule
  rule-tests/*.yml     # ast-grep valid/invalid snippets per rule
  tests/               # script tests (allowlist logic) with small fixture repos
  README.md            # install, usage, the rules table
```

## Distribution and versions

Rule changes change per-file counts, and both over and under fail, so every consumer pins
caltrop and ast-grep. (Claude's call.)

- **CI:** the workflow clones caltrop at a pinned commit (an `env` value in the workflow
  file) and installs ast-grep with `pip install ast-grep-cli==0.44.1` (prebuilt wheel, no
  compile). Bumping caltrop means bumping the pin and re-running `caltrop baseline` or
  fixing hits in the same PR.
- **Locally (bawn):** caltrop cloned at `~/Projects/caltrop`, `caltrop` symlinked into
  `~/.local/bin`. ast-grep from `cargo install ast-grep --locked` (no root) or pacman via
  `sudoq`.
- **Public repo** (Toby's decision, 2026-11-17), so consumer CI clones it without secrets.

## Adoption

- **vesper:** add a `caltrop` step to `scripts/check.sh` (included in `all` and `fast`) and
  run it in the `lint-rust` CI job; commit a `caltrop.toml` from `caltrop baseline`.
- **lemonate:** add a CI step and a `caltrop.toml`.
- Both through normal PRs in those repos.
- **Missing tool locally:** unlike the `shell` step (which skips when shellcheck is
  missing), the `caltrop` step fails with an install hint when `caltrop` or `ast-grep` is
  not on PATH. A guardrail that agents can skip by not having it installed protects nothing.
  (Claude's call.)

## Testing

- `ast-grep test` over `rule-tests/`: each rule has matching and non-matching snippets,
  including a production-code sleep (must not match), a sleep in `tests/`, a sleep in a
  `#[cfg(test)] mod`, and a sleep in a loop (poll rule only, not fixed-sleep).
- Script tests for the allowlist: over, under, exact, stale file, missing config.
- Acceptance: `caltrop check` on vesper and lemonate before baselining reports exactly the
  hits listed under Rules (line numbers may drift; the files and counts are what matter).

## Left to the builder

- Exact ast-grep rule YAML, including how to express "inside a `#[cfg(test)]` mod" and
  import-aware matching of bare `sleep`.
- Script structure, argument parsing, output formatting.
- README wording (plain, short sentences, matching vesper's wording rules).
