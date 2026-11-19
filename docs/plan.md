> Historical record: written before v1.0.0; README.md and docs/versions.md are current.

# caltrop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public repo `Toby-Faucher/caltrop` with ast-grep rules and a `caltrop` script that fails a Rust repo's check when tests sleep, poll deadlines, swap behaviour under `cfg(test)`, use mocking crates or enable retries, with a shrink-only per-file allowlist; adopted in vesper and lemonate through PRs.

**Architecture:** ast-grep rules (YAML) do the matching; one stdlib-only Python script runs `ast-grep scan --json=stream`, adds a nextest-retries check, counts hits per (rule, file) and compares with the target repo's `caltrop.toml`. Consumers pin caltrop by commit and ast-grep by version.

**Tech Stack:** ast-grep 0.44.1, Python 3.11+ stdlib (`tomllib`, `json`, `subprocess`, `unittest`), GitHub Actions.

**Spec:** `/home/toby/.t3/scratch/2026-11-18-hey-i-recently-found-this-e425a166/docs/superpowers/specs/2026-11-17-caltrop-design.md` (copied into the repo as `docs/design.md` in Task 1). Read it before starting any task.

## Global Constraints

- Repo at `/home/toby/Projects/caltrop`, default branch `main`, public on GitHub as `Toby-Faucher/caltrop`.
- ast-grep pinned at `0.44.1` everywhere. Locally installed from the prebuilt release binary at `~/.local/bin/ast-grep` (already done by the controller; `cargo install` failed here because /tmp is a small tmpfs). In CI: `pipx install ast-grep-cli==0.44.1`.
- Script: Python 3 standard library only. No third-party packages.
- Rule ids (stable, key the allowlist): `no-fixed-sleep`, `no-deadline-poll`, `no-test-swap`, `no-mock-crates`, `no-test-retries`.
- Exit codes: 0 pass, 1 violations, 2 usage or tool error.
- Hit output format: `file:line: rule: message` (file repo-relative, line 1-based).
- Never use `sudo`; root goes through `sudoq` (none should be needed).
- vesper rules (`/home/toby/Projects/vesper/CLAUDE.md`) apply to vesper changes: plain short sentences, no em dashes, `scripts/check-wording.sh` must pass, builds through `scripts/capped.sh`.
- Do not touch the vesper or lemonate main checkouts' working trees (vesper is on `release/1.7.2`). Adoption work happens in git worktrees under `~/Projects/vesper-wt/` and `~/Projects/lemonate-wt/`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Review Focus

1. **A repo with no `caltrop.toml`:** `check` treats it as an empty allowlist (every hit fails, exit 1, and says `run caltrop baseline` to adopt). Test in Task 3.
2. **Gitignored directories** (`target/`, lemonate's `.worktrees/`): never scanned. Test in Task 3 (fixture with an ignored dir holding a sleep).
3. **`check` right after `baseline` passes**, including `no-test-retries` hits and paths that need TOML quoting (spaces, quotes). Test in Task 3.
4. **Missing ast-grep or malformed `caltrop.toml`:** exit 2 with a one-line reason (and the install command for ast-grep), never a traceback. Test in Task 3.
5. **Called from another directory** (`caltrop check ../vesper`): paths in output and allowlist are relative to REPO_DIR, not the caller's cwd. Test in Task 3.

---

## File Structure

```
caltrop/
  caltrop                      # Python script (executable, no .py): CLI, scan, retries check, allowlist
  sgconfig.yml                 # ruleDirs: [rules], utilDirs: [utils], testConfigs: [{testDir: rule-tests}]
  utils/                       # shared ast-grep utility rules (test context, sleep call, loop)
  rules/
    no-fixed-sleep.yml
    no-fixed-sleep-tests-dir.yml
    no-deadline-poll.yml
    no-deadline-poll-tests-dir.yml
    no-test-swap.yml
    no-mock-crates.yml
  rule-tests/*-test.yml        # ast-grep snippet tests per rule
  tests/test_caltrop.py        # unittest, end-to-end via subprocess on temp fixture git repos
  docs/design.md               # copy of the spec
  docs/plan.md                 # copy of this plan
  README.md
  .github/workflows/ci.yml
  LICENSE                      # MIT, copyright Toby Faucher
```

**Path-scoped rules (decided):** ast-grep rule snippets have no file path, so "file under `tests/`" lives in separate rule files with a `files: ["**/tests/**"]` glob and an id ending `-tests-dir`. The base rule (e.g. `no-fixed-sleep`) matches inside a `#[cfg(test)]` mod in any file. The script maps `<id>-tests-dir` to `<id>` and dedupes hits by (rule, file, line), so a `cfg(test)` mod inside a `tests/` file counts once.

---

### Task 1: Repo, sleep rules, rule tests

**Files:**
- Create: `sgconfig.yml`, `utils/*.yml`, `rules/no-fixed-sleep.yml`, `rules/no-fixed-sleep-tests-dir.yml`, `rules/no-deadline-poll.yml`, `rules/no-deadline-poll-tests-dir.yml`, `rule-tests/no-fixed-sleep-test.yml`, `rule-tests/no-deadline-poll-test.yml`, `docs/design.md`, `docs/plan.md`, `LICENSE`, `.gitignore`

**Interfaces:**
- Produces: rule ids above; each rule's `message` is the fix text from the spec's Rules table, verbatim; `ast-grep test -c sgconfig.yml --skip-snapshot-tests` passes.

- [ ] **Step 1:** `mkdir /home/toby/Projects/caltrop && git init -b main`; copy spec to `docs/design.md`, this plan to `docs/plan.md`; MIT `LICENSE` (copyright 2026 Toby Faucher); `sgconfig.yml`.

- [ ] **Step 2: Write failing rule tests.** `rule-tests/no-fixed-sleep-test.yml` (id `no-fixed-sleep`):
  - invalid: `#[cfg(test)] mod tests { #[test] fn t() { std::thread::sleep(d); } }`; same with `tokio::time::sleep(d).await` in an `async fn`; same with bare `sleep(d).await`; a sleep inside `tokio::spawn(async move { loop { x().await; } ; sleep(d).await })` style spawned block that sits inside a `while` loop in a cfg(test) mod (loop search stops at closures/async blocks, so this is a fixed sleep).
  - valid: a sleep in a plain `fn` with no cfg(test) mod (production); a sleep inside a `loop`/`while`/`for` in a cfg(test) mod (belongs to the poll rule); `#[cfg(test)] mod tests { fn t() { let sleep = 3; } }` (not a call).
  `rule-tests/no-deadline-poll-test.yml` (id `no-deadline-poll`): invalid: sleep inside `while`, `loop`, `for` in a cfg(test) mod; valid: production loop with sleep; fixed sleep in cfg(test) mod not in a loop; sleep inside `async move {}` inside a loop.

- [ ] **Step 3:** Run `ast-grep test -c sgconfig.yml --skip-snapshot-tests`. Expected: FAIL (rules missing).

- [ ] **Step 4: Write utils and rules.**
  - `utils/sleep-call.yml`: a `call_expression` whose `function` text matches `^(std::thread::|thread::|tokio::time::|time::|async_std::task::|task::)?sleep(_until)?$`. Add a one-line `# shortcut: bare sleep() counts whatever it was imported from, switch to import tracking if a repo defines its own sleep` comment.
  - `utils/in-test-mod.yml`: inside a `mod_item` that is preceded by (`follows`) an `attribute_item` matching `#[cfg(test)]`, `stopBy: end`.
  - `utils/in-loop.yml`: inside `loop_expression` | `while_expression` | `for_expression`, with `stopBy` any of `closure_expression`, `async_block`, `function_item`.
  - Base rules: `all: [sleep-call, in-test-mod, not in-loop]` (fixed) and `all: [sleep-call, in-test-mod, in-loop]` (poll), `severity: error`, `language: rust`.
  - `-tests-dir` rules: same minus `in-test-mod`, with `files: ["**/tests/**"]`, same message.

- [ ] **Step 5:** Run `ast-grep test -c sgconfig.yml --skip-snapshot-tests`. Expected: all pass. Then sanity scan: `ast-grep scan -c /home/toby/Projects/caltrop/sgconfig.yml /home/toby/Projects/lemonate` must report `src/search/time_manager.rs` lines 590, 683, 694, 827 as `no-fixed-sleep` and `tests/uci.rs:65` as `no-deadline-poll-tests-dir`, and nothing in `src/uci/handler.rs`. If ast-grep cannot express a util as written, adjust the YAML (not the behaviour) and say so in the report.

- [ ] **Step 6: Commit** `feat: sleep and deadline-poll rules`.

### Task 2: Swap and mock rules

**Files:**
- Create: `rules/no-test-swap.yml`, `rules/no-mock-crates.yml`, `rule-tests/no-test-swap-test.yml`, `rule-tests/no-mock-crates-test.yml`

**Interfaces:**
- Consumes: `utils/in-test-mod.yml` from Task 1.
- Produces: rule ids `no-test-swap`, `no-mock-crates`.

- [ ] **Step 1: Write failing rule tests.**
  - `no-test-swap` invalid: `fn f() { if cfg!(test) { a() } else { b() } }`; `fn f() { if cfg!(not(test)) {} }`; `#[cfg(not(test))] fn real() {}`. valid: `#[cfg(test)] mod tests { fn t() { if cfg!(test) {} } }`; `#[cfg(test)] mod tests {}`; `#[cfg(feature = "x")] fn f() {}`.
  - `no-mock-crates` invalid: `use mockall::predicate::*;`, `use mockall::automock;`, `#[automock] trait T {}`, `#[cfg_attr(test, mockall::automock)] trait T {}`, `mock! { Foo {} }`, `use faux;`, `#[faux::create] struct S;`, `use mockers::Scenario;`, `use mry;`. valid: `use wiremock::MockServer;`, `use httpmock::MockServer;`, `struct MockLike;`.
- [ ] **Step 2:** Run `ast-grep test -c sgconfig.yml --skip-snapshot-tests`. Expected: FAIL for the two new rules.
- [ ] **Step 3:** Write the rules. `no-test-swap`: `cfg!(test)`/`cfg!(not(test))` macro invocations and `#[cfg(not(test))]` attributes, `not: in-test-mod`, `ignores: ["**/tests/**"]`. `no-mock-crates`: use declarations, attributes and `mock!` invocations by regex on node text for `mockall|mockers|faux|mry`, everywhere. Messages verbatim from the spec.
- [ ] **Step 4:** Run tests again. Expected: all pass. Sanity: scanning vesper and lemonate reports zero hits for both rules.
- [ ] **Step 5: Commit** `feat: test-swap and mock-crate rules`.

### Task 3: The `caltrop` script

**Files:**
- Create: `caltrop` (executable), `tests/test_caltrop.py`

**Interfaces:**
- Consumes: `sgconfig.yml` and rule ids from Tasks 1–2. The script locates `sgconfig.yml` next to its own resolved path (`Path(__file__).resolve().parent`), so a `~/.local/bin` symlink works.
- Produces: CLI `caltrop check [REPO_DIR]`, `caltrop baseline [REPO_DIR]`, `caltrop --help`. Allowlist file `REPO_DIR/caltrop.toml`:
  ```toml
  [allow.no-fixed-sleep]
  "crates/x/tests/a.rs" = 2
  ```
  Internal function names are the implementer's choice.

- [ ] **Step 1: Write failing tests** in `tests/test_caltrop.py` (unittest; each test builds a temp git repo fixture with `git init` and files, runs `caltrop` via `subprocess` with `sys.executable`-independent invocation of the script path):
  - `test_clean_repo_passes`: no hits, no `caltrop.toml` → exit 0.
  - `test_hit_without_allowlist_fails`: `tests/a.rs` with one `std::thread::sleep(d);` in a fn → exit 1, stdout contains `tests/a.rs:<line>: no-fixed-sleep:` and `caltrop baseline`.
  - `test_baseline_then_check_passes`: two sleeps in `tests/a b.rs` (space in name) and a nextest retry → `baseline` exit 0, `caltrop.toml` contains `[allow.no-fixed-sleep]` and `"tests/a b.rs" = 2` and `[allow.no-test-retries]`; `check` exit 0.
  - `test_over_allowance_fails` / `test_under_allowance_fails` (stdout contains `lower the allowance for no-fixed-sleep in tests/a.rs to 1`) / `test_stale_file_fails` / `test_unknown_rule_in_allowlist_fails`: exit 1 each.
  - `test_tests_dir_and_mod_dedupe`: a `#[cfg(test)] mod` inside `tests/a.rs` with one sleep → counted once, rule printed as `no-fixed-sleep` (not `-tests-dir`).
  - `test_gitignored_dir_skipped`: `.gitignore` with `target/`, sleep in `target/tests/x.rs` → exit 0.
  - `test_nextest_retries`: `.config/nextest.toml` with `[profile.default] retries = 2` and an override `retries = { backoff = "fixed", count = 1 }` → 2 `no-test-retries` hits in `.config/nextest.toml`; `retries = 0` → none.
  - `test_other_cwd`: run from `/` with an absolute REPO_DIR → same output paths as from inside.
  - `test_missing_ast_grep`: `PATH` without ast-grep → exit 2, stderr contains `cargo install ast-grep`.
  - `test_bad_toml`: malformed `caltrop.toml` → exit 2, no `Traceback` in stderr.
- [ ] **Step 2:** Run `python3 -m unittest discover -s tests -v`. Expected: FAIL (script missing).
- [ ] **Step 3: Implement `caltrop`.** `#!/usr/bin/env python3`. Run `ast-grep scan -c <sgconfig> --json=stream .` with `cwd=REPO_DIR`; parse each line (`ruleId`, `file`, `range.start.line` 0-based, `message`); map `-tests-dir` suffix; dedupe by (rule, file, line). Retries: parse `.config/nextest.toml` if present; one hit per `retries` > 0 (int, or table `count` > 0) in `profile.*` and `profile.*.overrides[*]`; line found by scanning the text for `retries` occurrences in order (fallback line 1). Compare counts; print hits for over-allowance files, `lower the allowance ...` for under, stale and unknown-rule messages; one-line summary. `baseline` writes sorted sections/keys with TOML basic-string escaping (`\` and `"`). A missing `caltrop.toml` is an empty allowlist, and the failure output ends with `run caltrop baseline to adopt caltrop in this repo`. ast-grep missing (`FileNotFoundError`) or non-zero exit with no JSON → exit 2 with `install ast-grep 0.44.1: cargo install ast-grep --version 0.44.1 --locked`. `tomllib.TOMLDecodeError` → exit 2, one line.
- [ ] **Step 4:** Run `python3 -m unittest discover -s tests -v` and `ast-grep test -c sgconfig.yml --skip-snapshot-tests`. Expected: all pass.
- [ ] **Step 5: Acceptance.** `./caltrop check /home/toby/Projects/lemonate` and `./caltrop check /home/toby/Projects/vesper` (read only, no `caltrop.toml` there): hits include every location in the spec's "Existing hits" list (files and counts, per the spec the rules win where they find more); no hit in any `src/` production path listed in the spec. Paste the per-rule, per-file counts into the task report.
- [ ] **Step 6: Commit** `feat: caltrop check and baseline`.

### Task 4: README, CI, publish

**Files:**
- Create: `README.md`, `.github/workflows/ci.yml`

- [ ] **Step 1:** `README.md`: one-paragraph intro (what and why, credit landmines with link), install (clone, symlink `caltrop` into `~/.local/bin`, ast-grep 0.44.1), usage (`check`, `baseline`, the allowlist format and ratchet), the rules table with messages, the known limits (macro bodies invisible; bare `sleep()` counted regardless of import; `#[test]` fns outside `tests/` and `cfg(test)` mods not seen), how a consumer CI pins it (snippet with `CALTROP_REF` env, `git clone` + `git -C caltrop checkout $CALTROP_REF`, `pipx install ast-grep-cli==0.44.1`). Plain short sentences, no em dashes.
- [ ] **Step 2:** `.github/workflows/ci.yml` on push/PR: ubuntu-24.04, `pipx install ast-grep-cli==0.44.1`, `ast-grep test -c sgconfig.yml --skip-snapshot-tests`, `python3 -m unittest discover -s tests -v`.
- [ ] **Step 3: Commit** `docs: readme and ci`.
- [ ] **Step 4: Publish:** `gh repo create Toby-Faucher/caltrop --public --source /home/toby/Projects/caltrop --push --description "Lints that keep AI-written Rust tests honest"`. Wait for the CI run (`gh run watch` is fine here) and confirm it passes. Report the commit SHA on `main`.

### Task 5: Adopt in vesper

**Files (in worktree `~/Projects/vesper-wt/caltrop`, branch `chore/caltrop` from `origin/main`):**
- Modify: `scripts/check.sh` (new step `caltrop`, in `all` and `fast`, listed in `--help`)
- Modify: `.github/workflows/ci.yml` (`lint-rust` job: env `CALTROP_REF: <SHA from Task 4>`, clone, `pipx install ast-grep-cli==0.44.1`, put caltrop on PATH, include `caltrop` in its `scripts/check.sh` call)
- Create: `caltrop.toml` (from `caltrop baseline`)
- Modify: `docs/dev.md` (one line: install caltrop and ast-grep locally)

- [ ] **Step 1:** `git -C ~/Projects/vesper fetch && git -C ~/Projects/vesper worktree add ~/Projects/vesper-wt/caltrop -b chore/caltrop origin/main`.
- [ ] **Step 2:** Locally, symlink: `ln -sf /home/toby/Projects/caltrop/caltrop ~/.local/bin/caltrop`.
- [ ] **Step 3:** Add the step. The step fails with `caltrop is not installed: see docs/dev.md` when `caltrop` is not on PATH (spec: no skip).
- [ ] **Step 4:** `caltrop baseline .` then `scripts/check.sh caltrop wording shell scripts`. Expected: pass.
- [ ] **Step 5:** Commit `chore: add caltrop test-honesty checks`, push, open a PR against `main` with a body listing the baseline counts per rule and that the hits are debt to pay down, not fixed here. Report the PR URL.

### Task 6: Adopt in lemonate

**Files (worktree `~/Projects/lemonate-wt/caltrop`, branch `chore/caltrop` from `origin/main`):**
- Modify: `.github/workflows/ci.yml` (new job `caltrop`, ubuntu same as other jobs, same pin, clone, pipx, `caltrop check`)
- Create: `caltrop.toml`
- Modify: `readme.md` only if it has a contributing or checks section; otherwise leave it.

- [ ] **Step 1:** Worktree as in Task 5.
- [ ] **Step 2:** `caltrop baseline .`, `caltrop check .`. Expected: exit 0.
- [ ] **Step 3:** Add the CI job. Commit, push, open PR with baseline counts. Report the PR URL.
