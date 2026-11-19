# Python, TypeScript and Svelte honesty patterns: candidate caltrop rules

Date: 2026-11-18. Scope: test shortcuts coding agents take in Python, TypeScript, JavaScript and Svelte that make CI pass while the test checks little or nothing. Not in scope: what caltrop v1.1.0 already catches (README rule tables): fixed sleeps, deadline polls, test swaps, mock libraries, retries, skipped/xfail/todo tests, `.only`, silent skips, `Fake*` classes, bare `toThrow()` and `pytest.raises(Exception)`.

How the evidence was gathered:

- Corpus A, Toby's repos (read-only): brisk, cloudberry, divergence-oracle, earshot, food, hush, lemonate, pika, vesper, vigil. food-laptop has the same root commit as food (`922c4b0`), so it was not counted twice. 54% to 99% of each repo's commits carry a `Co-Authored-By: Claude` trailer (e.g. vesper 581/734, food 383/628, vigil 182/183). divergence-oracle has none.
- Corpus B, 12 public repos found with `gh search commits "Co-Authored-By: Claude" "tests"`, shallow-cloned at the SHA in brackets: shipvo/shipvo [3e669ca], SkaffenAmtiskaw/meal-planning [db615e5], enricai/barnacle [6574945], iskhakovt/cogmo [4a79ee8], dawidvanzyl/panorama-music [8591cfa], RafaelFCarneiro/patty [156d5e5], konradkluz/evia-manager [dc74cda], phahadek/claude-orchestrator [53a9d84], mfittko/dev-loops [e893a14], vaanai/MAL [d532d30], VINIClUS/CnesData [0cd55a6], kv244/MLTrain [5747809]. Claude co-authored share, from the same search: shipvo 674/1152, meal-planning 584/836, barnacle 583/759, cogmo 597/793, panorama-music 131/248, patty 211/303. The other six hit the search rate limit; they have Claude co-authored commits, but the share was not measured.
- Scratch ast-grep 0.44.1 rules (not committed), kept in the session scratchpad, run with `ast-grep scan --json=stream` over each repo. Hits were then filtered to caltrop's test-code paths (`test_*.py`, `*_test.py`, `conftest.py`, `*.test.*`, `*.spec.*`, `tests/`, `test/`, `__tests__/`, `e2e/`). A copy of each TS rule was run as `tsx`, the way `scripts/gen-tsx.py` does it. Samples of every rule's hits were read by hand. `git blame` was used for Corpus A hits; Corpus B clones are depth 1, so no blame there.
- Linter rules were read at pinned tags in their repos (see Sources). Two background surveys did the first pass. I re-checked three claims at the source: ruff 0.16's new default set, the vitest plugin's recommended severities, and the removal of testing-library's `no-wait-for-empty-callback`.

One finding changes how much "a linter already covers it" counts: of the 19 repos with JavaScript, only one (panorama-music, in `e2e/package.json`) installs any of `@vitest/eslint-plugin`, `eslint-plugin-jest`, `eslint-plugin-playwright` or `eslint-plugin-testing-library`. None of the 9 Python repos selects ruff `PT` rules in `pyproject.toml`, `ruff.toml` or `setup.cfg`. Linter coverage is real, but in this corpus nobody has it switched on.

## Summary: top 5

1. `no-constant-assert`. An assertion that cannot fail: `expect(true).toBe(true)`, `expect(x).toBe(x)`, `assert.ok(true)`, `expect(s.size).toBeGreaterThanOrEqual(0)`, `assert c[..] == 0 or True`. claude-orchestrator keeps a test named "placeholder" whose only line is `expect(true).toBe(true)`, left behind when the real tests were removed. 9 real hits in 4 agent repos. No lint rule in any surveyed plugin catches the truthy side.
2. `no-source-text-test`. The test reads a source file (`readFileSync('./flow-runner.ts')`, `inspect.getsource(F.main)`) and regex-matches the text instead of running the code. barnacle has it in 282 test files, MAL in 119, claude-orchestrator in 48. It passes whether or not the code works at run time. No linter covers it.
3. `no-weak-result-assert`, TS extension: assertions only inside `catch`. `try { f() } catch (e) { expect(e.code).toBe('forbidden') }` passes when `f` does not throw. 6 of 6 hits are real (evia-manager 5, claude-orchestrator 1). `no-conditional-expect` in the jest and vitest plugins flags it at error level, but almost no repo here installs those plugins.
4. `no-weak-result-assert`, extension: a test whose only assertions are presence checks (`toBeTruthy`, `toBeDefined`, `not.toBeNull`, `assert x is not None`, `assert isinstance(..)`). 80 tests in claude-orchestrator, 70 in CnesData, 18 in evia-manager, 14 in meal-planning, 7 in food (6 Claude co-authored). Plugins only cover special cases (Playwright locators, Testing Library queries).
5. `no-swallowed-error`. An empty `catch {}`, `.catch(() => {})`, `except ..: pass` or `contextlib.suppress(..)` in test code. It hides the error that should fail the test. 13 to 152 per agent repo in test files; brisk `api.test.ts:35` swallows a rejection, then asserts on the fetch mock. Partly covered: ESLint `no-empty` (recommended) flags `catch {}` but not `.catch(() => {})`. ruff S110 (default since 0.16) flags `except Exception: pass`, but not typed handlers.

## Ranked table

Feasibility: A = works as an ast-grep rule today (tried). B = needs a small change to the `caltrop` script. C = not feasible. FP = false-positive risk. "Agent repos" = Corpus B. Counts are hits in test files.

| # | Candidate | Why dishonest code passes | Existing lint (default) | Evidence (Corpus A / B) | Feasibility | FP | Rule id and message |
|---|---|---|---|---|---|---|---|
| 1 | Constant or self-comparing assertion | The assertion is true whatever the code does | None for the truthy side. PLR0133 (on) only flags literal-vs-literal; PLW0129 and F631 (on) only flag string and tuple asserts; PT015 and B011 (off) only flag the falsy side | A: 0. B: 9 real (claude-orchestrator 1, barnacle 3, dev-loops 1, MAL 4 `or True`) | A | Low | `no-constant-assert`: "This assertion cannot fail. Compare what the code returns with an expected value written in the test. Delete a placeholder test; do not keep it green." |
| 2 | Test asserts on source text | Grepping the source passes even if the code is broken at run time | None | A: brisk 1 (Svelte SVG source). B: barnacle 373 hits / 282 files, MAL 187 / 119, claude-orchestrator 138 / 48, shipvo 29 / 7, evia-manager 18 / 14 | A | Med (golden-file and codegen tests, scripts loaded into `vm`) | `no-source-text-test`: "Test what the code does, not how its source reads. Call it and assert on the result. Reading a source file or `inspect.getsource` passes whatever the code does at run time." |
| 3 | Assertions only in `catch` (TS) | Nothing throws, so the `catch` never runs and the test passes | vitest/jest/playwright `no-conditional-expect` (vitest, jest: error; playwright: warn) flags `expect` in `catch` | A: 0. B: 6 of 6 real (evia-manager 5, claude-orchestrator 1). Python twin: 5 hits, all honest `self.fail`/`pytest.fail` uses, so no Python rule | A | Low | extend `no-weak-result-assert`: "The catch only runs if something throws, so this passes when nothing does. Use `expect(() => f()).toThrow(X)` or `await expect(p).rejects.toThrow(X)`." |
| 4 | Test whose only checks are presence checks | `toBeTruthy` / `is not None` passes on a wrong value | Playwright `no-unnecessary-assertions` (error, locators only); jest-dom `prefer-in-document` (error, Testing Library queries only); jest `no-unnecessary-assertion` (off, typed only); `no-restricted-matchers` (off, empty) | A: food 2 TS + 5 py (6 Claude co-authored). B: claude-orchestrator 80, CnesData 70 py, evia-manager 18, meal-planning 14, barnacle 12, MAL 10 | A | Med-high | extend `no-weak-result-assert`: "Assert the value, not that there is one. `toBeTruthy()`, `toBeDefined()` and `is not None` pass on a wrong result. Use `toEqual(expected)` or `assert x == expected`." |
| 5 | Swallowed error in a test | The failure that should fail the test is discarded | ESLint `no-empty` (recommended) flags empty `catch {}` only; ruff S110/BLE001 (on since 0.16) flag broad `except: pass` only | A: brisk 3, vesper 13 (e2e cleanup), food 1 py. B: dev-loops 152, barnacle 98, cogmo 41, claude-orchestrator 39, MAL 27 py, CnesData 19 py | A | Med-high (cleanup in `finally`/`afterEach`, best-effort `close()`) | `no-swallowed-error`: "Do not discard an error in a test. Let it fail the test, or assert which error you expect. Cleanup that may fail belongs in `afterEach`/a fixture." |
| 6 | Conditional assertion (`if (x) expect(..)`, no `else`) | The assertion is skipped when the condition is false | vitest/jest `no-conditional-expect` (error), playwright (warn). Python: none | A: 9 TS, 2 py. B: barnacle 87, cogmo 95, evia-manager 70, dev-loops 56, claude-orchestrator 42; MAL 156 py, CnesData 55 py | A | High (loops over table rows with per-row checks) | `no-conditional-assert`: "Assert the condition first, then check the value. An assertion inside an `if` with no `else` is skipped when the condition is false." |
| 7 | Coverage-exclusion pragmas | `fail_under` / thresholds pass by excluding code, not testing it | None (coverage.py excludes `# pragma: no cover` by default) | A: 0. B: CnesData 107 in production code with `fail_under = 100`; evia-manager 32 `v8 ignore` (each with a reason); MAL 12 | A (`kind: comment`) | Med | `no-coverage-pragma`: "Cover this code with a test instead of excluding it from coverage." |
| 8 | Test with no assertion at all | It only checks that nothing throws | vitest `expect-expect` (error), jest and playwright `expect-expect` (warn), all keyed on a list of assert function names. Python: none | A: food 9 py + 3 TS, hush 1. B: dev-loops 32, evia-manager 34 TS; CnesData 259 py, MAL 207 py | B (resolve helpers in the same file and in `conftest.py`) | High as plain ast-grep: about 9 in 10 Python samples call an assert helper (`refused(..)`, `_case_*(..)`) | `no-assertion-free-test`: "This test checks nothing. Assert on the result. If 'does not raise' is the point, say so with an explicit assertion." |
| 9 | Inverted tests: `test.fails`, jest `test.failing`, Playwright `test.fail` | Passes while the code is still broken; like `xfail` | None (vitest `no-disabled-tests` skips `fails`, jest's skips `failing`) | 0 | A (regex edit in `no-ignored-test`) | Low | extend `no-ignored-test` (same meaning as xfail) |
| 10 | Several statements in `pytest.raises` | The exception may come from setup, not the call under test | ruff PT012 (off, not in the 0.17.5 default list); bugbear B908 (opt-in) | A: food 1 (not Claude). B: MAL 11 | A | Med | extend `no-weak-result-assert`: "Put only the call that should raise inside `pytest.raises`. Do the setup before it." |
| 11 | Empty `waitFor(() => {})` | Waits one tick, checks nothing | None since testing-library v6.0.0 removed `no-wait-for-empty-callback` | 0 | A | Low | extend `no-fixed-sleep`: "Wait for the condition: put the assertion in the `waitFor` callback, or use `findBy*`." |
| 12 | Runner config that lets nothing count as a pass: `passWithNoTests`, `addopts --deselect/--ignore`, `strict_xfail = false`, Playwright `testIgnore` | Tests are dropped or empty runs pass | None (outside any linter's reach) | A: 0. B: claude-orchestrator 1 `--passWithNoTests` (in a scoped-test script); evia-manager and panorama-music 1 `testIgnore` each | B (config reading like `no-test-retries`) | Med | `no-test-filter`: "Run the whole suite in CI. Fix or delete the test you are filtering out." |

## Candidate details

### 1. no-constant-assert

What it is. An assertion that holds whatever the code does.

Evidence (Corpus B; Corpus A has none):
- claude-orchestrator `packages/backend/src/github/ReviewOrchestrator.test.ts:2087`: `it('placeholder — push_detected handled in server.ts, not ReviewOrchestrator', () => { expect(true).toBe(true); })`, under the comment "Tests removed: push_detected wiring moved to server.ts". https://github.com/phahadek/claude-orchestrator/blob/53a9d84/packages/backend/src/github/ReviewOrchestrator.test.ts#L2087
- barnacle `src/scripts/recon-browser.test.ts:4754` `expect(true).toBe(true)`; `recon-browser.frame-scoped-already-advanced.test.ts:55` `expect(WRAPPER_URL).toBe(WRAPPER_URL)`; `src/scraper/pool.test.ts:167` `expect(stats.size).toBeGreaterThanOrEqual(0)`.
- dev-loops `packages/core/test/lifecycle-state.test.mjs:564` `assert.ok(true)`.
- MAL, four asserts that end in `or True`: `tools/test_arena_screen.py:388` `assert c["refused_no_print_at_or_before_decision"] == 0 or True`, `tools/test_probe_withdraw.py:92`, `tools/test_hv4_scan_perf.py:182`, `tools/test_hv4_read.py:749`. https://github.com/vaanai/MAL/blob/d532d30/tools/test_arena_screen.py#L388

Existing lint coverage:
- ruff PT015 and B011 flag only always-false asserts. The PT015 code acts only when truthiness is `Some(false)`: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/flake8_pytest_style/rules/assertion.rs (PT015 #L175, logic #L605-L611). Neither is in ruff 0.17.5's default list: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/settings/mod.rs#L357-L765
- PLW0129 (on) flags string literals only, and F631 (on) non-empty tuples only: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/pylint/rules/assert_on_string_literal.rs , https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/pyflakes/rules/assert_tuple.rs . PLR0133 (on) flags literal-vs-literal comparisons, not `x == x`: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/pylint/rules/comparison_of_constant.rs
- pylint's `visit_assert` checks only tuple and string constants: https://github.com/pylint-dev/pylint/blob/v4.1.4/pylint/checkers/base/basic_checker.py#L761-L768
- No JS plugin checks the subject of `expect`. `expect-expect` is satisfied by `expect(true).toBe(true)`: https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/docs/rules/expect-expect.md

ast-grep feasibility (tried; A).
- TS: `call_expression` whose function matches `^expect\((true|false|null|undefined|-?\d+(\.\d+)?)\)\.(not\.)?(toBe|toEqual|toStrictEqual|toBeTruthy|toBeFalsy|toBeDefined|toBeNull|toBeUndefined)$` and whose arguments are a literal or empty. Plus `pattern: expect($A).toBe($A)` (and `toEqual`, `toStrictEqual`), limited by regex to a plain identifier or property path. Plus `expect(<..>.(length|size)).toBeGreaterThanOrEqual(0)`, `assert(true)` and `assert.ok(true)`.
- Python: `assert True|1|"str"`; `pattern: assert $A == $A` limited to a name or attribute; `assert len($A) >= 0`; `self.assertTrue(True)`.
- The `or True` form must be matched structurally: `assert_statement` whose first child is a `boolean_operator` with `field: right, kind: true`. A text regex also hit `or True` inside a lambda argument (MAL `test_arena_screen.py:2129,2535`). The structural rule gives exactly the 4 real hits.

False positives found and excluded:
- `expect(f(x)).toBe(f(x))` and `assert f(x) == f(x)` are determinism checks, not tautologies. Examples: cogmo `hashToolSchema(baseSnapshot)`, patty `deriveIdempotencyKey(..)`, MAL `R.boot_p(x)  # reproducible`. So calls are excluded from the self-compare form.
- `expect('literal').toMatch(RE)` tests a regex (evia-manager `privacy-content.test.ts:73`). So only boolean, number, null and undefined subjects count.
- `expect(r.top).toBeGreaterThanOrEqual(0)` is a real bound on a value that could be negative. Only `.length`/`.size` count.

### 2. no-source-text-test

What it is. The test loads the code under test as text and asserts on the string: an order of `indexOf` results, or a regex match. The code is never executed.

Evidence:
- barnacle `src/scraper/flow-runner.checkbox-state-primitive.test.ts:324`: `const src = readFileSync(`${__dirname}/flow-runner.ts`)`, then `expect(src.indexOf('await tryCheckboxStatePrimitive({')).toBeLessThan(..)`. https://github.com/enricai/barnacle/blob/6574945/src/scraper/flow-runner.checkbox-state-primitive.test.ts#L324
- claude-orchestrator `packages/backend/src/__tests__/zdrGate.test.ts:5-20`: reads `SessionManager.ts`, then `expect(sessionManagerSource).toMatch(/gates\.requireZDR/)`. And `compactionTracking.test.ts:310`: "wraps compaction_count column addition in try/catch", checked with a regex over `schema.ts`.
- MAL `tools/test_u1_funder_fetch.py:152`: `src = inspect.getsource(F.main)`, then `assert src.index('"rpc_errors": ..') < src.index('summary["pilot_record"]')`. https://github.com/vaanai/MAL/blob/d532d30/tools/test_u1_funder_fetch.py#L152
- Corpus A: brisk `web/src/modules/settings/pad.svg.test.ts:62` reads `PadDiagram.svelte` (`0c1da8c`, Claude co-authored). vigil `push.test.ts:33` reads `static/sw.js`, but runs it in `vm.runInNewContext`, so it executes the code: a false positive.

Counts (rule restricted to source extensions): barnacle 373 hits in 282 test files, MAL 187 in 119, claude-orchestrator 138 in 48, shipvo 29 in 7 (mostly parity checks between a JSON spec and Kotlin/Swift sources), evia-manager 18 in 14, cogmo 4, CnesData 2, patty 1, brisk 1, vigil 1. Zero in the other 12 repos.

Existing lint coverage: none in any surveyed plugin or in ruff, pylint or bugbear.

ast-grep feasibility (tried; A). TS: `call_expression` with function `(^|\.)(readFileSync|readFile)$` and arguments matching `\.(ts|tsx|js|mjs|cjs|svelte|vue|py|rs)['"`]`, plus `expect(<..>.toString()).toContain/toMatch`. Python: `inspect.getsource(lines)`, plus `open`/`.read_text()` calls whose text names a `.py`/`.ts`/`.js`/`.svelte` file. A first version that also matched a `src/` path segment picked up JSON schemas and built output, so it was dropped. Misses: a path built in a variable on another line (`const p = join(..)`).

False-positive risk: medium. Cases seen: parity checks between two hand-written files (shipvo), running a service worker in a `vm` (vigil), and golden tests on generated code. The ratchet handles these. A narrower variant could require that the read result reaches `toMatch`, `toContain`, `indexOf` or `in`.

### 3. Assertions only in `catch` (extend no-weak-result-assert, TS)

What it is. `try { call() } catch (e) { expect(e.code).toBe('x') }` with nothing after the `try` and no `expect.assertions(n)`. If `call()` stops throwing, the test passes.

Evidence: all 6 hits are real.
- evia-manager `apps/api/test/procedures/procedure-representation.test.ts:71`, `manual-rules.test.ts:110`, `composition-plan.test.ts:86`, `platform/email-config.test.ts:210`, `platform/session-creator.test.ts:32`. https://github.com/konradkluz/evia-manager/blob/dc74cda/apps/api/test/platform/session-creator.test.ts#L32
- claude-orchestrator `packages/backend/src/session/__tests__/branchModel.test.ts:430`.

The Python twin gave 5 hits, all honest: `except X: self.fail(..)` or `pytest.fail(..)` is the right way to say "must not raise" (MAL `test_hv4_live_c0_pr5a_graph.py:180`, CnesData `test_mode_canary_runtime.py:137`). PT017 covers only an assert on the `except .. as e` name, and it is off: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/flake8_pytest_style/rules/assertion.rs#L133 . So no Python rule is proposed.

Existing lint coverage: vitest `no-conditional-expect` is error in recommended (https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/src/index.ts), and flags `expect` in `catch` and in `.catch()` (https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/src/rules/no-conditional-expect.ts). jest's is error too: https://github.com/jest-community/eslint-plugin-jest/blob/v29.17.1/docs/rules/no-conditional-expect.md . Playwright's is warn: https://github.com/playwright-community/eslint-plugin-playwright/blob/v2.12.2/src/plugin.ts . None of the evidence repos installs these plugins.

ast-grep feasibility (tried; A). `try_statement` where:
- the `handler` has an `expect(`/`assert` call and no `throw` or `return`;
- the `body` and `finalizer` have no assertion;
- `not: precedes: {stopBy: end, has: <assert>}`, so nothing after the `try` checks the outcome;
- the nearest function is the test callback (`stopBy` at function boundaries), and that callback has no `expect.assertions`/`expect.hasAssertions`.

The first version without the `precedes`, `throw` and nearest-function checks also hit helpers like shipvo `share.test.mjs:22` (`const code = (o) => { try {..} catch (e) { ..; return e.code } }`).

### 4. Presence-only tests (extend no-weak-result-assert)

What it is. Every assertion in the test is `toBeTruthy()`, `toBeDefined()`, `not.toBeNull()`, `not.toBeUndefined()`, `assert x is not None`, `assert isinstance(..)`, `assert len(x) > 0` or bare `assert x`.

Evidence:
- claude-orchestrator `packages/backend/src/__tests__/dbIsolation.test.ts:31`: "allows an in-memory database in test mode" ends with only `expect(mod.db).toBeDefined()`.
- food `frontend/src/lib/__tests__/handoff.test.ts:12` and `bundle.test.ts:112`: `expect(problem(..)).not.toBeNull()` checks that some problem is reported, not which one. This is the TypeScript twin of Rust's `assert!(r.is_err())`. Commits `456464b` and `f021a54`, both Claude co-authored.
- food `backend/tests/test_models_notification.py:54` (`0a2a28e`, Claude co-authored). food `backend/tests/test_models.py:682`, `test_created_at_is_set`, asserts `is not None` and `isinstance(.., datetime)` (`f3740e8`, not Claude co-authored).
- Counts of tests with only presence checks: claude-orchestrator 80, CnesData 70 (py), evia-manager 18, meal-planning 14, barnacle 12, MAL 10 (py), patty 10, food 7 (2 TS, 5 py), cogmo 5, panorama-music 4, shipvo 1.

Important false positive, already excluded: `expect(screen.getByText('x')).toBeTruthy()` is honest, because `getBy*` and `findBy*` throw when the element is missing. In food this form was 211 of 225 weak matchers, and 61 of the 63 first-pass "presence-only" tests. Testing Library's `prefer-explicit-assert` (off) documents bare `getBy*` as an implicit assertion: https://github.com/testing-library/eslint-plugin-testing-library/blob/v7.16.2/docs/rules/prefer-explicit-assert.md . The rule skips any subject matching `(get|find)(All)?By`.

Existing lint coverage:
- Playwright `no-unnecessary-assertions` (error) flags these matchers only on a Locator: https://github.com/playwright-community/eslint-plugin-playwright/blob/v2.12.2/docs/rules/no-unnecessary-assertions.md
- jest-dom `prefer-in-document` (error) only on Testing Library query results: https://github.com/testing-library/eslint-plugin-jest-dom/blob/v5.10.2/docs/rules/prefer-in-document.md
- jest `no-unnecessary-assertion` is off and needs type information: https://github.com/jest-community/eslint-plugin-jest/blob/v29.17.1/docs/rules/no-unnecessary-assertion.md
- `no-restricted-matchers` is off with an empty list: https://github.com/jest-community/eslint-plugin-jest/blob/v29.17.1/docs/rules/no-restricted-matchers.md
- Python: no rule (see the py survey under Sources).

ast-grep feasibility (tried; A). The rule matches a test callback, or `def test*`, that `has` a weak assertion and does `not: has:` any assertion call that is not weak. In Python the weak forms are a regex on `assert_statement`. Lone weak matchers are too common to flag one by one: Python `assert X is not None` gave 754 hits and `assert isinstance(..)` 441 in two repos, mostly as type narrowing before real checks. Only the "whole test is presence checks" form is worth a rule. FP risk is medium-high: "it returns something" is sometimes the whole contract (food `test_created_at_is_set`). Ratchet it.

### 5. no-swallowed-error

What it is. In test code: `catch {}` with no statements, `.catch(() => {})` / `.catch(() => undefined)` / `.catch(noop)`, `except ..: pass|...|continue`, `contextlib.suppress(..)`.

Evidence:
- brisk `web/src/state/api.test.ts:35`: `await api.games().catch(() => {});`, then the test asserts on `f.mock.calls` (`33d71d6`, Claude co-authored). Two more at `:210` and `:225`.
- vesper: 13, all in `web/e2e/*.mjs` helpers (`b.close().catch(() => {})`, `process.kill` in `lib.mjs:43`). These are best-effort cleanup, so false positives under a test-dir glob.
- Corpus B: dev-loops 152, barnacle 98, cogmo 41, claude-orchestrator 39, shipvo 22, evia-manager 18, patty 13, panorama-music 6. Python: MAL 27, CnesData 19, cogmo 2. Not every hit was read; a sample of about 15 split roughly evenly between cleanup and swallowing a result the test then ignores.

Existing lint coverage:
- ESLint `no-empty` is recommended, with `allowEmptyCatch: false` by default, so `catch {}` is flagged: https://github.com/eslint/eslint/blob/v10.15.0/lib/rules/no-empty.js#L25-L31 . `.catch(() => {})` is not an empty block, so it is not flagged.
- ruff S110 is in the 0.17.5 default list, but only for bare, `Exception` and `BaseException` handlers unless `check-typed-exception = true`: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/flake8_bandit/rules/try_except_pass.rs , https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/flake8_bandit/settings.rs#L25
- SIM105 (off) recommends `contextlib.suppress`, which still swallows the error: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/flake8_simplify/rules/suppressible_exception.rs

ast-grep feasibility (tried; A). `catch_clause` whose `statement_block` has no non-comment child; `call_expression` `.catch` whose first argument matches `^(\(\w*\)|\w+)\s*=>\s*(\{\s*\}|undefined|null|void 0)$|^noop$`; Python `except_clause` whose `block` is `pass`/`...`/`continue`, and `suppress(..)`. To cut false positives, skip hits inside `afterEach`/`afterAll`/`finally`/fixture teardown (after `yield`). That was not tried.

### 6. no-conditional-assert

The same idea as the Rust candidate in the 2026-11-17 note: an assertion under `if` with no `else` is skipped when the condition is false.

Evidence: earshot `web/src/lib/boards.test.ts:165` `if (isRef) expect(c).toBeCloseTo(1);` (`ef12a9a`); food `ActiveAlarmGrid.test.ts:666` `if (inner !== rows[0]) expect(..)` (`7ee4c76`); vigil `shifts.test.ts:34` `if (!r.ok) assert.ok(r.error.length > 0)`. Corpus B counts are large (barnacle 87, cogmo 95, MAL 156 py). Most are loops over table rows where each row checks something different (MAL `test_c1nf_daily_check.py:657`).

Existing lint coverage: `no-conditional-expect` (see 3) is error in vitest and jest. vitest's `no-conditional-in-test` (off) only sees an `if` that is a direct child of the test body: https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/src/rules/no-conditional-in-test.ts . Python: none.

ast-grep (tried; A). `if_statement` with `not: has: {field: alternative, regex: '.'}` (a bare `has: {field: ..}` is rejected as "Rule must have one positive matcher") and an `expect`/`assert` call in the consequence, with the nearest function being the test callback. An `if (!x) throw` guard must not count as the assertion: the first version counted `throw` and hit barnacle's `if (!existsSync(TSC_BIN)) throw new Error(..)`. Low priority: high volume, high FP, and the plugins cover JS when installed.

### 7. no-coverage-pragma

coverage.py excludes `# pragma: no cover` by default and `fail_under` defaults to 0: https://github.com/nedbat/coveragepy/blob/7.17.3/coverage/config.py#L150-L156 , https://github.com/nedbat/coveragepy/blob/7.17.3/doc/config.rst#L747-L758 . Vitest's v8 provider honours `istanbul`, `v8`, `c8` and `node:coverage` ignore hints (TS needs `-- @preserve`): https://github.com/vitest-dev/vitest/blob/v5.1.1/docs/guide/coverage.md

Evidence: CnesData sets `fail_under = 100` (`pyproject.toml:188`) and has 107 `# pragma: no cover` in production code, so the 100% gate is met partly by exclusion. https://github.com/VINIClUS/CnesData/blob/0cd55a6/pyproject.toml#L188 . evia-manager has 32 `/* v8 ignore start -- process wiring ..; main() is covered by tests */`, each with a reason. That is the honest form, but a rule cannot tell. Corpus A: 0.

ast-grep (tried; A): `kind: comment`, regex `pragma:\s*no\s*(cover|branch)` (Python) or `(istanbul|c8|v8)\s+ignore` (TS). The rule is about production code, so it has no test-file glob. It is not about tests themselves, so it may be outside caltrop's scope. Medium priority. The alternative is a B-feasibility check that reads `fail_under`/`thresholds` only.

### 8. no-assertion-free-test

What it is. A test with no assertion: it only checks that nothing throws, or it prints.

Evidence: food `backend/tests/live/test_smx_probe.py:137..305`: six "probe" tests that call the live API and `note(..)` results with no assertion (`4946942`, Claude co-authored). They are opt-in live tests, but they run green whatever comes back.

Why B, not A. The plain rule ("no call named `expect*`/`assert*`/`check*`/`verify*`") is mostly false positives: in a sample of 20 Python hits from MAL and CnesData, about 18 called an assertion helper named something else (`refused(..)`, `must_refuse(..)`, `_case_rejection_loses_to_full(..)`). The TS samples had the same problem (evia-manager `refused(..)`, dev-loops `refused(f, ..)`). The JS plugins solve this with a configured name list (`assertFunctionNames`, default `['expect','assert']` in vitest): https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/docs/rules/expect-expect.md . A caltrop version would need the script to collect helper functions that contain an assertion (same file plus `conftest.py`/shared test utils) and treat calls to them as assertions. ast-grep metavariables do not bind across a `not:`, so a single rule cannot do this.

### 9. Inverted tests (extend no-ignored-test)

Vitest `test.fails` passes only when an assertion fails: https://github.com/vitest-dev/vitest/blob/v5.1.1/docs/api/test.md . Jest `test.failing` is the same: https://github.com/jestjs/jest/blob/v30.5.2/docs/GlobalAPI.md . Neither `no-disabled-tests` flags them (vitest source checks only `skip`, `x*`, a missing function and `pending`): https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/src/rules/no-disabled-tests.ts . It means the same as `xfail`, which `no-ignored-test` already counts. Zero hits in all 22 repos. Cheap: add `fails|failing|fail` to the modifier regex in `rules/ts/no-ignored-test-ts.yml`. Watch Playwright's `test.fail(condition)`: like `test.skip(cond)`, the conditional form belongs to `no-silent-skip`.

### 10. Several statements in pytest.raises

ruff PT012 flags it but is not in the 0.17.5 default list, even though its `warns` twin PT031 is: https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/rules/flake8_pytest_style/rules/raises.rs#L56 . Evidence: MAL 11; food `backend/tests/test_models_sevone_alert.py:89` (`73e945c`, not Claude co-authored). ast-grep (tried; A): `with_statement` whose `with_clause` matches `^(pytest\.)?raises\(|self\.assertRaises` and whose body has a second non-comment statement. Medium value: the exception type already narrows it.

### 11. Empty waitFor

testing-library removed `no-wait-for-empty-callback` in v6.0.0: https://github.com/testing-library/eslint-plugin-testing-library/blob/v7.16.2/docs/migration-guides/v6.md . Nothing flags `waitFor(() => {})` now. Zero hits in 22 repos. ast-grep (tried; A): `call_expression` `(^|\.)waitFor$` whose first argument matches `^(async\s*)?\(\)\s*=>\s*(\{\s*\}|undefined|null|true)$`. Low priority.

### 12. Runner config that hides tests (B)

- `passWithNoTests` defaults to false in Vitest and Jest: https://github.com/vitest-dev/vitest/blob/v5.1.1/docs/config/passwithnotests.md , https://github.com/jestjs/jest/blob/v30.5.2/docs/CLI.md . Found once, in claude-orchestrator `scripts/scoped-tests.mjs:62`, for scoped runs (reasonable there).
- pytest `strict_xfail` defaults to false, and an XPASS does not fail the suite: https://github.com/pytest-dev/pytest/blob/9.2.0/doc/en/reference/reference.rst#L2575-L2601 . `addopts` can hide `--deselect`/`--ignore`/`-p no:..`: same file #L1360-L1375, #L3014-L3026.
- Playwright `testIgnore`: evia-manager `apps/web/playwright.config.ts:12` (screenshot specs), panorama-music `e2e/playwright.config.ts:33`.

CnesData has its own test, `tests/production/infra/test_acceptance.py:160`, that fails if pytest flags contain `--ignore|--deselect|-k|-m|--lf|--maxfail`. That is evidence that agents do reach for these flags. Feasibility B: the TOML/INI/JS-config reading already in `caltrop` for `no-test-retries`. Low priority on this evidence.

## Variants of existing rules, checked

- Unawaited `expect(p).resolves/.rejects` and unawaited Playwright web-first assertions: 0 hits in 22 repos. Both are covered at error level by `valid-expect` (vitest, jest) and `missing-playwright-await`: https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/docs/rules/valid-expect.md , https://github.com/playwright-community/eslint-plugin-playwright/blob/v2.12.2/docs/rules/missing-playwright-await.md . Dropped.
- `expect(spy).toHaveBeenCalled()` with no arguments: about 580 hits (claude-orchestrator 186, cogmo 131, barnacle 79, meal-planning 64, vesper 45). `prefer-called-with` exists but is off. Too common to ratchet, and the spy itself is allowed by `no-mock-libs` (`vi.fn()`). Dropped.
- Svelte: neither eslint-plugin-svelte 3.24.1 nor svelte-check 4.7.8 has any test rule: https://github.com/sveltejs/eslint-plugin-svelte/tree/eslint-plugin-svelte%403.24.1/docs/rules , https://github.com/sveltejs/language-tools/blob/svelte-check%404.7.8/packages/svelte-check/README.md . No test code lives inside `.svelte` files in the corpus; component tests are `.test.ts`, which the TS rules already cover. No Svelte-specific candidate.

## Dropped

- `@ts-expect-error` / `@ts-ignore` / `# type: ignore` in tests: cogmo 17, claude-orchestrator 5, food 16 py. Most are deliberate invalid-input tests with a reason (claude-orchestrator `breadthOwnTreeExclusion.test.ts:315` `// @ts-expect-error ownTree is required`). typescript-eslint `ban-ts-comment` (recommended) bans `@ts-ignore` and allows `@ts-expect-error` with a 3+ character description: https://github.com/typescript-eslint/typescript-eslint/blob/v8.73.0/packages/eslint-plugin/src/rules/ban-ts-comment.ts . ruff PGH003 (blanket `type: ignore`) is off. Not a test-honesty signal on its own.
- `as any` in tests: thousands of hits (barnacle 2884). Normal for building partial inputs.
- Tests that return a value: pytest 9.2 only warns (`PytestReturnNotNoneWarning`), so the test passes: https://github.com/pytest-dev/pytest/blob/9.2.0/src/_pytest/python.py#L190-L197 . But all 7 value-return hits were helper functions whose names start with `test` (MAL `tools/r4bt_trainserve_counts.py:71`), not real tests. Dropped.
- Snapshot-only tests and `-u`: 13 snapshot calls in total. Vitest 5.1 writes no snapshots in CI and fails on missing or mismatched ones (https://github.com/vitest-dev/vitest/blob/v5.1.1/docs/config/update.md). Jest only refuses *new* snapshots under `--ci` (https://github.com/jestjs/jest/blob/v30.5.2/docs/CLI.md). No `-u` in any CI script or `package.json` in 22 repos. Dropped.
- `it.concurrent` with shared state: 4 uses (cogmo). Shared state cannot be seen syntactically. C.
- Hypothesis weakening (`max_examples=..`, `deadline=None`, `suppress_health_check`): 1 hit (CnesData). Note that hypothesis loads a CI profile with `deadline=None` and `too_slow` suppressed on its own: https://github.com/HypothesisWorks/hypothesis/blob/v6.170.15/hypothesis/src/hypothesis/_settings.py#L1227-L1239
- `eslint-disable` of a test-lint rule, and `noqa: PT..`: 0 hits for test rules. Generic `# noqa` is common (MAL 518 in tests), mostly `BLE001` with a reason.
- Empty `def test_x(): pass`: 3 hits, all already under `@pytest.mark.skip` (CnesData `test_010_migration.py:80`), so `no-ignored-test` counts them.

## Not checked

- `git blame` on Corpus B (depth-1 clones). The Claude share is per repo, from commit search, and was not measured for six repos (rate limit).
- None of the scratch rules ran through `caltrop check`, as rule-test YAML, or as a `.svelte` `<script>` (html injection). They ran with `ast-grep scan` on scratch files using copies of caltrop's `utils/ts` and `utils/python`.
- Swallowed-error hits were sampled, not all read. Cleanup-context exclusions (`afterEach`, `finally`, post-`yield`) were not tried.
- Jest's and Playwright's `expect-expect` default `assertFunctionNames` were taken from docs, not source. Whether any Playwright rule touches `test.fail` was searched only partially.
- That flake8 runs all codes of an installed plugin by default, and whether PLR0133 fires inside an `assert` (rule body read, call site not).
- Whether ruff actually runs in CI in the Python repos (only the config `select` was checked). MAL's `# noqa: BLE001` comments suggest it runs there with defaults.
- Svelte 5 runes-specific test patterns (`flushSync`, `$effect.root` in tests): no candidate found; not searched beyond the TS rules.

## Sources

Linters (pinned):
- @vitest/eslint-plugin v1.6.28 (`c5df105`): https://github.com/vitest-dev/eslint-plugin-vitest/blob/v1.6.28/src/index.ts (recommended severities: `expect-expect` error, `no-conditional-expect` error, `no-disabled-tests` warn, `valid-expect` error), rule docs under `docs/rules/`.
- eslint-plugin-jest v29.17.1 (`6870d67`): https://github.com/jest-community/eslint-plugin-jest/blob/v29.17.1/README.md
- eslint-plugin-playwright v2.12.2 (`d499b63`): https://github.com/playwright-community/eslint-plugin-playwright/blob/v2.12.2/src/plugin.ts
- eslint-plugin-testing-library v7.16.2 (`8ef0782`): https://github.com/testing-library/eslint-plugin-testing-library/blob/v7.16.2/docs/migration-guides/v6.md
- eslint-plugin-jest-dom v5.10.2 (`7dec406`): https://github.com/testing-library/eslint-plugin-jest-dom/blob/v5.10.2/src/index.js
- eslint-plugin-svelte 3.24.1 (`a18a0e4`), svelte-check 4.7.8 (`78f3b0a`): links in "Variants" above.
- typescript-eslint v8.73.0 (`a93b4b9`); ESLint v10.15.0 `no-empty`: links above.
- ruff 0.17.5 (`c91de8a`): default list https://github.com/astral-sh/ruff/blob/0.17.5/crates/ruff_linter/src/settings/mod.rs#L357-L765 (407 entries; S110 and PLW0129 present, PT011/PT012/PT015/PT017 absent), 0.16.0 default-set change https://github.com/astral-sh/ruff/blob/0.17.5/changelogs/0.16.x.md#L10-L15 . The 0.16.0 change ("413, up from 59") makes the old `E4,E7,E9,F` default out of date.
- flake8-pytest-style v2.2.0, flake8-bugbear 26.11.16, pylint v4.1.4, pytest 9.2.0, coverage.py 7.17.3, mypy v2.4.1, pyright 1.1.415, hypothesis v6.170.15: links in the candidate sections.
- Vitest docs v5.1.1 (`161e25f`), Jest docs v30.5.2 (`8dddf31`): links in the candidate sections.

Repos: Corpus B SHAs are listed at the top. URLs of the form `https://github.com/<owner>/<repo>/blob/<sha>/<path>#L<n>` resolve at those SHAs.
