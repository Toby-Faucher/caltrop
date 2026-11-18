# More Rust honesty patterns: candidate caltrop rules

Date: 2026-11-17. Scope: shortcuts coding agents take in Rust that make CI pass while the code or the tests are not honest. Not in scope: what caltrop already catches (fixed sleeps, deadline polls, `cfg(test)` swaps, the four mock crates, nextest retries).

How the evidence was gathered: ast-grep 0.44.1 scratch rules (not committed) run over `git ls-files`-tracked code in vesper, lemonate, brisk, cloudberry, hush, earshot, pika. Then `git blame` on each hit, and a check whether the commit has a `Co-Authored-By: Claude` trailer. Clippy lint groups were read from the clippy source at master (links below), not from memory.

## Summary: top 5

1. `no-silent-skip`. A test that returns early when a file, browser or socket is missing reports a pass and checks nothing. 18 real sites in 3 repos, all in Claude co-authored commits. No lint covers it.
2. `no-test-feature-swap`. `cfg!(feature = "test-push")` swaps production behaviour for tests and slips past `no-test-swap`, because the regex wants a bare `test` token. Verified miss in vesper (`push.rs:443`). Six hits, all Claude co-authored. A regex change, not a new rule.
3. `no-ignored-test`. 28 `#[ignore]` tests across 5 repos. No CI job in any repo runs them. In vesper a CI failure was answered by ignoring the golden-hash tests (`cd36998`). Clippy only checks that an ignore has a reason, and only when enabled.
4. `no-fake-impls`. Hand-rolled `impl Trait for Fake` that records calls is a mock without the crate. Seven in brisk. Not caught by `no-mock-crates`.
5. `no-weak-result-assert`. `assert!(r.is_ok())` and `assert!(r.is_err())`. 103 sites, 89 in Claude co-authored commits. The clippy lint exists but is off by default. design.md deferred this as too noisy (133 by grep); the ratchet makes it adoptable.

## Ranked table

Feasibility: A = works as an ast-grep rule today (tried). B = needs a small Python change in `caltrop`. FP = false-positive risk. Counts are hits per repo: vesper/lemonate/brisk/cloudberry/hush/earshot/pika.

| # | Candidate | Why dishonest code passes | Existing lint (default) | Repo evidence | Feasibility | FP | Rule id and message |
|---|---|---|---|---|---|---|---|
| 1 | Early return when a prerequisite is missing | Test is green without running its body | None | 1/4/1(FP)/0/0/13/0 | A, needs `in-test-code` plus a tests-dir twin | Low-med | `no-silent-skip`: "A test must not return early when a prerequisite is missing. It reports a pass. Provide the prerequisite in CI and fail if it is absent." |
| 2 | Feature-flag behaviour swap (`feature = "test-*"`, `mock`, `fake`, `stub`) | Production path differs from the tested path, same as `cfg(test)` | `clippy::cfg_not_test` (restriction, off) covers only `not(test)` | 6/0/0/0/0/0/0 | A (regex edit in `no-test-swap`) | Low | extend `no-test-swap` message, or `no-test-feature-swap`: "Production code must behave the same under test. Pass the dependency in instead of a test feature." |
| 3 | `#[ignore]` | Test is compiled but never run in CI | `clippy::ignore_without_reason` (pedantic, off) only checks for a reason | 7/1/7/0/0/12/1 | A | Med (2 child-process helpers in brisk) | `no-ignored-test`: "An ignored test never runs in CI. Make it run (fixture, feature, or a CI job), or delete it." |
| 4 | Hand-rolled trait fakes | Test checks the fake, not the code | None | 1(FP)/0/7/0/0/0/0 | A | Med (socket fakes are allowed by design.md) | `no-fake-impls`: "Use the real implementation. A hand-written fake that records calls is a mock." |
| 5 | `assert!(r.is_ok())` / `is_err()` | Passes on the wrong error or an unchecked Ok value | `clippy::assertions_on_result_states` (restriction, off) | 38/3/47/6/2/1/6 | A (regex on `macro_invocation`) | Low | `no-weak-result-assert`: "Assert the value or which error. Use `assert_eq!(r, Ok(..))`, `matches!(r, Err(E::X))` or `r.unwrap_err()`." |
| 6 | `#[allow]`/`#[expect]` without `reason` | Silences the lint instead of fixing it, no record why | `clippy::allow_attributes_without_reason` (restriction, off); `clippy::allow_attributes` (restriction, off) | 3/2/12/0/4/4/0 (25 of 33 lint attrs) | A | Med (FFI `unsafe_code`, test `dead_code`) | `no-bare-lint-allow`: "Fix the lint. If it is a real false positive, use `#[expect(lint, reason = \"...\")]`." |
| 7 | `#[doc(hidden)] pub` test seams | Production API widened so tests can reach in or replace parts (rng, timeouts) | None | 8/0/6/0/0/5/0 (about 11 are test seams) | A | Med (4 FFI in earshot-abi) | `no-test-seam`: "Do not widen production API for tests. Inject the dependency through the constructor." |
| 8 | nextest escape hatches: `on-timeout = "pass"`, `flaky-result`, `default-filter`, `test-threads`, `global-timeout` | Timeout or flake counts as a pass, or tests are filtered out | None (nextest has no policy lint) | 0 (hypothetical) | B (same TOML path as `no-test-retries`) | Low | `no-nextest-escape`: "A timeout must fail the run. Fix the test, do not change how the runner counts it." |
| 9 | `deny.toml` advisory ignores | `cargo deny` goes green without fixing or upgrading | None | 3 in vesper, 7 in brisk; one added by Claude (`d24524d`) | B (TOML) | Low | `no-advisory-ignore`: "Upgrade or replace the crate. If it is not reachable, say why next to the entry." |
| 10 | CI soft-fail: `continue-on-error: true` | A failing job does not fail the run | None | lemonate `ci.yml:49`, brisk `ci.yml:72` | A with `language: yaml` and `--no-ignore hidden` | Low | `no-ci-soft-fail`: "A job that cannot fail is not a check. Fix it or remove it." |
| 11 | `if let Some(x) = .. { assert!(..) }` with no `else` | Assertion skipped when the value is absent | None | 0/5/2/0/0/0/0 | A | Med (some are intentional "either" checks) | `no-conditional-assert`: "Assert that the value is present first, then check it." |
| 12 | Mock crates caltrop does not list | Same as `no-mock-crates` | None | 0 | A (regex edit) | Low | extend `no-mock-crates`: add `unimock`, `mockiato`, `mocktopus`, `mockall_double`, `mock_it`, `double` |
| 13 | `#[test]` with no assertion | Test cannot fail | None | 14 candidates, about 10 are false positives (helper methods like `expect_error`) | A but noisy | High | not recommended, see Dropped |

## Candidate details

### 1. no-silent-skip

What it is. A test begins with `if !prerequisite { return; }`, often with `eprintln!("skipping ...")`. The test passes without running. Inference, not cited: libtest has no way to report a run-time skip, so an early return is reported as `ok`. The Rust reference describes only the static `#[ignore]`, which at least shows as ignored: https://doc.rust-lang.org/reference/attributes/testing.html

Existing lint coverage: none found in the clippy list (https://rust-lang.github.io/rust-clippy/master/index.html). rustc has nothing either.

Evidence (rule run, then `git blame`; 19 of 19 hits are in Claude co-authored commits, 1 of them a false positive):
- lemonate `src/book/mod.rs:350` `book_present()` prints "skipping" and returns false. Used at `:357`, `:370`, `:402`, `:427`. Added in `6083274`. The comment at `:343` says the tests "skip instead of failing".
- earshot `crates/earshot/tests/browser.rs:217,235,257,271,291,318,346,370,397`: `if !ready(..) { return; }`. These tests are also `#[ignore]`, so a manual `--ignored` run still passes when the models are missing. Added in `64ca9cf`.
- earshot `crates/earshot/tests/run.rs:19,27`: `return eprintln!("skip: ..")` (`59572aa`).
- vesper `crates/vesper-sfu/tests/forwarding.rs:464`: returns when `UdpSocket::bind("[::]:0")` fails (`2908063`). This one is honest about why, but still passes on a host without IPv6.
- False positive: brisk `crates/brisk-hostd/src/notify.rs:177`. The test is a child-process helper (`#[ignore = "run by sends_ready_watchdog_stopping_in_order"]`) that returns when its env var is unset. A real skip rule needs an allowlist entry here.

ast-grep feasibility (tried). Match `if_expression` whose consequence holds a `return_expression` that is bare or `return eprintln!(..)`, and whose condition or body mentions `exists|is_file|is_dir|env::var|available|present|ready|installed|skip|UdpSocket|TcpListener`. Needs `in-test-code`, plus a twin with `files:` for `tests/` like the existing `-tests-dir` rules. A plain `if $C { $$$S return; }` pattern failed when the block held a macro statement, so the `has: kind: return_expression` form is needed. Without the condition regex there are false hits on value-returning helpers (vesper `timeouts.rs:109`, brisk `quit.rs:202`).

Honest alternatives for the message: fail with a clear error, or provide the prerequisite in CI.

### 2. no-test-feature-swap

What it is. `cfg!(feature = "test-push")` (or `mock`, `fake`, `stub`, `test-support`) changes production behaviour, or exposes extra API, only for tests. It is the same dishonesty as `cfg(test)`: the code that ships is not the code that was tested.

Why the current rule misses it. `no-test-swap` matches `test` as a bare token: `^cfg!\((.*[(,\s])?test([),\s].*)?\)$`. In `feature = "test-push"` the word sits inside a string, so the regex fails. Confirmed by running `no-test-swap` over vesper: zero hits, while the rule below finds 6.

Existing lint coverage: `clippy::cfg_not_test` is restriction and covers only `cfg(not(test))`: https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/cfg_not_test.rs

Evidence (6 of 6 in Claude co-authored commits):
- vesper `crates/vesper-server/src/push.rs:443`: `let allow_loopback = cfg!(feature = "test-push");` lets push reach 127.0.0.1 (`09d96fe`). The feature is on for integration tests (`crates/vesper-server/Cargo.toml:48`) and CI builds with it (`.github/workflows/ci.yml:129`). Line 35 is a `compile_error!` that blocks release builds with the feature. That guard is good practice, but the tested binary still differs from the shipped one.
- vesper `crates/vesper-sfu/src/lib.rs:14,169,261` and `room.rs:219`: `#[cfg(feature = "test-support")]` gates a fake client and extra pub items (`313c057`). This is API, not behaviour. Lower severity.

ast-grep feasibility (tried). `macro_invocation` `^cfg!\(.*feature\s*=\s*"[^"]*(test|mock|fake|stub)[^"]*"` and the same on `attribute_item`, `not: in-test-code`. Hits: vesper 6, others 0. Simplest delivery: widen the regex in `no-test-swap` and keep the id. Allowlist the 5 gating hits, fix `push.rs:443`.

### 3. no-ignored-test

What it is. `#[ignore]` keeps a test compiled but not run: https://doc.rust-lang.org/reference/attributes/testing.html ("Ignored tests are still compiled when in test mode, but they are not executed"). Nothing in any of the 7 repos runs ignored tests: grep for `--ignored`, `--run-ignored` and `include-ignored` in scripts, justfiles and `.github` found nothing in vesper, brisk, earshot or pika.

Existing lint coverage: `clippy::ignore_without_reason`, group pedantic (off by default), needs a reason string only and only sees test targets (https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/attrs/mod.rs). vesper enables it (`Cargo.toml:38`). Clippy does not ask whether the test ever runs.

Evidence (27 of 28 in Claude co-authored commits):
- vesper `cd36998` ("ci: make golden hash tests dev-only"): CI failed on a hash that differs per CPU, so `denoiser_matches_golden_hash` and `default_pipeline_matches_golden_hash` were marked `#[ignore]` (`crates/vesper-dsp/src/lib.rs:95,104`). The reason is real, but this is the exact move a rule should make a human look at. Other vesper ignores: `vesper-audiolab/tests/full_corpus.rs` (4), `vesper-store/tests/perf.rs:17`.
- earshot: 12 ignored (`tests/browser.rs`, `dataset.rs`, `native.rs`, `run.rs`). brisk: 7. lemonate `src/magic/mod.rs:310` is bare `#[ignore]` with no reason. pika `pc_corpus.rs:27` is a print-for-review "test".
- False positives: brisk `notify.rs:175,234` are child-process helpers run by another test.

ast-grep feasibility (tried). `attribute_item` regex `^#\[ignore\b`. Hits: 7/1/7/0/0/12/1. Ratchet fits: existing hits are allowlisted, new ones fail. Test-context scoping not needed.

### 4. no-fake-impls

What it is. A mock with no crate: `struct Fake { calls: Mutex<Vec<String>>, .. }` plus `impl Runner for Fake`. The test then asserts on recorded calls. `no-mock-crates` does not see it.

Existing lint coverage: none.

Evidence (7 of 8 hits in Claude co-authored commits; the 8th is vesper's `impl Drop for FakeClient`, a false positive):
- brisk `crates/brisk-hostd/tests/hosting.rs:48` (`impl Runner for Fake`, `d32fb93`), `tests/quit.rs:153,184` (`cdee136`), `tests/clipfiles.rs:47` (`impl Backend for Fake`), `src/host.rs:359,369` (`Runner`, `Clock`; introduced in `cc3fd12`), `src/machines.rs:893` (`impl Power for Fake`).
- Not a hit by design: struct fakes that are real local servers on a socket (brisk `tests/common/fake_host.rs`, vesper `tests/push.rs:29`). design.md says a real local server is fine. A name-based rule can hit those struct names, so the rule is on `impl <Trait> for <Fake|Mock|Stub|Spy|Dummy>*` only.

ast-grep feasibility (tried). `impl_item` with a `trait` field and `type` field regex `^(Mock|Fake|Stub|Spy|Dummy)`. Exclude `Drop`, `Debug`. The 7 hits show that brisk will need an allowlist and a design change (inject the command runner as a real small script).

### 5. no-weak-result-assert

What it is. `assert!(r.is_ok())` hides the error value; `assert!(r.is_err())` passes on any error, including the wrong one.

Existing lint coverage: `clippy::assertions_on_result_states`, group restriction, off by default: https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/assertions_on_result_states.rs . Its own docs say the form "does not show any of the information present in the `Result`", and note the suggested fix (`unwrap()`) hurts readability, so a plain `unwrap` swap is not the right message for `is_err`.

Evidence: 103 hits, 89 in Claude co-authored commits: vesper 38, lemonate 3, brisk 47, cloudberry 6, hush 2, earshot 1, pika 6. Examples: brisk `crates/brisk-client/tests/identity.rs:44,45,50` (`load_identity(..).is_err()` with no check of which error), vesper `crates/vesper-server/src/config.rs:255-257,275`. design.md already counted 133 by grep and deferred it as noisy. A shrink-only allowlist is the answer to noise: baseline 103, then pay down.

ast-grep feasibility (tried). `macro_invocation` with `pattern: assert!($$$)` and regex `(?s)^assert!\(\s*[^&|]*?\.is_(ok|err)\(\)\s*(,.*)?\)$`. Metavariables inside macros match single tokens only, so `assert!($X.is_ok())` misses `assert!(f(a, b).is_ok())`. The regex form does not. Test-context scoping not needed (asserts only appear in tests). Messages that include `{r:?}` are still flagged; decide whether to exempt a format argument. Negated forms (`!r.is_ok()`) are matched and are equally weak.

### 6. no-bare-lint-allow

What it is. An agent that hits a clippy error can add `#[allow(..)]` or `#[expect(..)]` instead of fixing it.

Existing lint coverage: `clippy::allow_attributes` and `clippy::allow_attributes_without_reason`, both restriction (off): https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/attrs/mod.rs . rustc has a `reason` parameter on all lint attributes: https://doc.rust-lang.org/reference/attributes/diagnostics.html . `#[expect]` warns when the expectation is unfulfilled, so it is better than `allow`.

Evidence: 33 lint attributes found; 25 lack a `reason = ` argument; 23 of those in Claude co-authored commits. Without reason: vesper 3 (`push.rs:1008`, `vesper-sfu/src/client.rs:61`, `tests/common/mod.rs:3`), lemonate 2 (`src/magic/mod.rs:189,217`), brisk 12 (five `#[expect(clippy::too_many_arguments)]`), hush 4, earshot 4 (`passes.rs:14,102` `deprecated`). Many carry a trailing `//` comment instead (hush, earshot-abi). The history is mixed and mostly good: brisk `819eb71` converted `allow` to `expect`, and brisk `art.rs:12` has a reasoned crate-level allow (`fc012df`, Claude moved it module-wide). vesper's `7bf439e` turned on lints and fixed hits.

ast-grep feasibility (tried). `attribute_item` or `inner_attribute_item` with regex `^#!?\[(allow|expect)\(` and `not: regex: 'reason\s*='`. Note `inner_attribute_item` is a separate node kind and must be listed. Exempt candidates: `dead_code` in `tests/common/`, `unsafe_code` in FFI crates. Medium value, because the set is small and mostly justified.

### 7. no-test-seam (`#[doc(hidden)] pub`)

Evidence: 19 hits, all Claude co-authored. About 11 are test seams by their own doc comments: vesper `limits.rs:111`, `push.rs:424`, `hub.rs:95`, `vesper-store/src/lib.rs:289,296,325`; brisk `session.rs:55,58,97` ("Replaces the CSPRNG (tests only)"), `tap.rs:85` ("Test knob"), `control.rs:298`, `rtp.rs:313`; earshot `paths.rs:17`. earshot-abi (4) are FFI exports, so false positives. Also brisk `lib.rs:42` `pub mod steam_info; // pub for tests`. No clippy lint covers `doc(hidden)`.

Feasibility: `attribute_item` regex `^#\[doc\(hidden\)\]$`, hits 8/0/6/0/0/5/0. Honesty risk: a predictable-CSPRNG constructor in the public API is a real hazard, not only a smell. FP risk medium; ratchet handles it. Ranked 7 because the harm is design, not CI passing.

### 8. no-nextest-escape

Verified in the nextest docs:
- `slow-timeout = { period = .., terminate-after = .., on-timeout = "pass" }` marks timed-out tests as successes (TMPASS): https://nexte.st/docs/features/slow-tests/ and https://nexte.st/docs/configuration/reference/
- `flaky-result` defaults to `"pass"`, so a flaky test passes after a retry: https://nexte.st/docs/features/retries/ . The `retries` ratchet in caltrop already blocks the retry itself.
- `default-filter` (profile) and per-test overrides can drop tests from the run; `test-threads` and `global-timeout` change scheduling: https://nexte.st/docs/configuration/per-test-overrides/

Evidence: none of the 7 repos use these. vesper has one override block that gives three named slow tests `slow-timeout = { period = "30s", terminate-after = 3 }` (`.config/nextest.toml`), with comments; the file has one commit (`5493391`), so no loosening history. Hypothetical but severe and cheap, because `caltrop` already parses this file for `no-test-retries`. Suggest forbidding `on-timeout = "pass"`, `flaky-result = "pass"` when `retries > 0`, and `default-filter`.

### 9. no-advisory-ignore

`deny.toml` `[advisories] ignore` makes `cargo deny` green. Counts: vesper 3 (`RUSTSEC-2026-0217`, `RUSTSEC-2023-0071`, `RUSTSEC-2026-0459`), brisk 7. vesper `d24524d` ("ignore RUSTSEC-2026-0459, not reachable here") was a Claude commit. Both repos already require a written reason per entry, so they are honest today. Value is catching a new entry without review. Feasibility: TOML via Python `tomllib`, like the nextest check. Clippy does not apply. Low priority.

### 10. no-ci-soft-fail

`continue-on-error: true`: lemonate `.github/workflows/ci.yml:49` (clippy "report only", added in `fb8c189`, a Claude commit), brisk `.github/workflows/ci.yml:72` (shellcheck, `9a0cac6`, with a `shortcut:` comment). Both are documented. Feasibility: ast-grep `language: yaml`, `kind: block_mapping_pair`, regex `^continue-on-error:\s*true`. It works, but only with `--no-ignore hidden`, because `.github` is a hidden directory; caltrop's script must pass that flag. Not Rust code, so it may be out of caltrop's scope. Low priority.

### 11. no-conditional-assert

`if let Some(x) = opt { assert_eq!(..) }` with no `else` passes when `opt` is `None`. Hits (rule run): lemonate `src/book/mod.rs:440`, `src/search/transposition.rs:979,1012` and 2 more; brisk `crates/brisk-proto/tests/tap.rs:119`, `src/notify.rs:192`. 7 hits, 2 in Claude commits (the rest by Toby). Some are deliberate ("Either our entry survived", `transposition.rs:1012`). Rule: `if_expression` with a `let_condition`, no `alternative`, an `assert*!` inside, `in-test-code`, not nested in another `if`. Note: `has: {field: alternative}` alone is rejected by ast-grep ("must have one positive matcher"); add `regex: '.'`. Low priority.

### 12. Mock crates not listed

The rule lists `mockall`, `mockers`, `faux`, `mry`. These crates exist and do the same job; crates.io pages: https://crates.io/crates/unimock , https://crates.io/crates/mockiato , https://crates.io/crates/mocktopus , https://crates.io/crates/mockall_double , https://crates.io/crates/mock_it , https://crates.io/crates/double . `mockito` is an HTTP mock server (https://crates.io/crates/mockito); it fits the existing "real local server is fine" carve-out, so leave it out. Hits in Toby's repos: zero. Regex edit only.

### Variants of existing rules, checked

- Fixed sleep and poll: counted other waiting calls in test files. `recv_timeout` 1 (lemonate), `yield_now` 2 (brisk), `park_timeout`, `wait_timeout`, `interval(`, `timeout(.., pending)` 0. Not worth a rule yet.
- brisk `eventually` helper (`crates/brisk-hostd/tests/api.rs:614`) is a bounded `for _ in 0..100 { sleep(50ms) }` loop, which `no-deadline-poll` already covers (it matches `for`).
- Timeouts widened: scanned history for a changed duration on a timeout/deadline line. 3 commits raised a number, none in a test timeout. Float tolerances: scanned history for a larger `abs() <`, `eps`, `tol` number. 0 commits. Both are dropped below.
- `no-test-swap` also misses `cfg!(debug_assertions)`-based swaps. Zero hits (`debug_assertions` only appears in vesper `push.rs:35` as part of a `compile_error!` guard).

## Dropped

- `#[should_panic]` without `expected`: zero bare uses in 7 repos (two uses, both with `expected`: brisk `steam_info/mod.rs:191`, earshot `sources.rs:275`). Covered by `clippy::should_panic_without_expect` (pedantic, off). https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/attrs/mod.rs
- `assert!(true)` and constants: zero hits; `clippy::assertions_on_constants` is style (on by default): https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/assertions_on_constants.rs
- insta snapshot auto-accept (`INSTA_UPDATE`, `INSTA_FORCE_PASS`): no repo uses insta. Documented behaviour (`auto` writes `.snap.new` when no CI is detected; `always` overwrites; `INSTA_FORCE_PASS` forces a pass): https://insta.rs/docs/advanced/ . Revisit if insta is adopted.
- Lowered proptest case counts: no `ProptestConfig` or `with_cases` anywhere (brisk has 22 proptest mentions, all default config; only a doc line mentions `PROPTEST_CASES`).
- `#[serial]`, `--test-threads=1`, `serial_test`: zero uses.
- `catch_unwind`: 3 uses (brisk `client/src/session.rs:610`, earshot-abi `lib.rs:84`), all in production at an FFI or poll boundary, none in tests.
- `todo!()` and `unimplemented!()`: no real uses (brisk has one in a comment); `clippy::todo` and `clippy::unimplemented` are restriction and vesper and brisk already enable them.
- Production `unwrap()`: 73 bare sites (vesper 14, lemonate 22, brisk 9, hush 1, earshot 4, pika 23), mostly mutex locks. `clippy::unwrap_used` is restriction; vesper tried it and left it off because `allow-unwrap-in-tests` does not cover `tests/common` helpers (`7bf439e`). Not dishonest, only panic-prone. No `expect("")` anywhere.
- Discarded Results (`let _ =`, `.ok();`): in tests, 74 `let _ =` hits, almost all cleanup (`remove_dir_all`) or deliberate no-panic fuzz-style calls (brisk `http_parse.rs:89`). In production, about 28 `.ok();`, mostly best-effort shutdown (earshot `run.rs:115,183`). Clippy: `let_underscore_must_use` and `unused_result_ok` are restriction, and `unused_result_ok` tells you to write `let _ =` instead. A rule would drown in legitimate hits.
- `.unwrap_or_default()` hiding errors: 107 sites, but about 30 sit on a parse or read. Most are intended "missing file means empty" (brisk `steam.rs:179`, `running.rs:34`). `clippy::unwrap_or_default` is style and recommends this form, so clippy will not help. Needs types to tell a missing file from a corrupt one, which ast-grep does not have.
- Widened float tolerances: 63 tolerance sites, zero loosening in history.
- Raised test timeouts: 83 `timeout(` sites in brisk, all guards, no loosening in history. The one real incident (vesper `25e4ed2`, a 1 s sleep replaced by a 60 s poll) is already in `no-deadline-poll`.
- Deleted or merged tests: scanned every commit for a net loss of `#[test]` lines. Two in brisk (`c2a9368` merged 16 tests into tables, `3ee570b` dropped 14 covered by property tests); both look like honest consolidation. A diff check is not an ast-grep rule anyway.
- Tests with no assertion: see row 13. The rule gave 14 hits and about 10 were false positives (tests that call helpers named `expect_error`, `forwards_with_bind`). Method-name heuristics are too weak.
- `unsafe` to dodge the borrow checker: lemonate has a documented seqlock (`unsafe impl Sync for SharedEntry`, `transposition.rs:365`, by Toby); cloudberry has three `static mut` with SAFETY comments for wasm32 (`smear/src/lib.rs:263,264`, `visualizer/src/lib.rs:285`). vesper forbids `unsafe_code` and hush and earshot deny it. This is a Cargo `[lints]` setting, not a caltrop rule; lemonate, cloudberry and brisk have no `unsafe_code` lint (rustc default is allow).
- Detached `tokio::spawn` that swallows panics: 92 spawn sites, almost all servers and background tasks. No syntactic signal.
- Visibility widened with `pub(crate)`: 193 hits, normal Rust. Dropped in favour of the narrower `#[doc(hidden)]` check.

## Not checked

- Running `cargo clippy` with the restriction lints on any repo (only counted with ast-grep).
- Whether the ast-grep rules behave inside `macro_rules!` bodies or generated code.
- Hits in web/JS or shell parts of the repos.
- `cargo mutants` or coverage as a way to find vacuous tests.
- Agent behaviour outside these 7 repos. Counts here are small, so the ranking leans on blame data and severity, not on frequency.
- I did not run the rules through `caltrop check` end to end. They were run with `ast-grep scan -c` on scratch rule files under `/tmp/claude-1000/`, using caltrop's `utils/` for `in-test-code`.
