# Contributing

Report a false positive or a missed shortcut with the issue forms.

## Adding a rule

1. Write the rule in `rules/` (Rust), `rules/python/` or `rules/ts/`. Name the file after its id, with a language suffix for Python and TypeScript: `no-fixed-sleep-py.yml`, `no-test-swap-ts.yml`, `no-test-swap-js.yml`. A Rust rule that needs a second copy for test files (a `files:` glob instead of a util match) gets `-tests-dir`: `no-fixed-sleep-tests-dir.yml`. A case of an existing rule that needs its own message gets its own file with a dotted variant before the suffix: `no-weak-result-assert.catch-ts.yml`. `base_id()` in `caltrop` strips the variant, `-py`, `-ts`, `-js` and `-tests-dir`, so all the variants count under one allowlist id. A rule that means the same thing as an existing one must reuse its id; a new id is a new allowlist key for every consumer.
2. Shared matchers go in `utils/` (Rust), `utils/python/` or `utils/ts/`. Prefix Python utils with `py-` and TypeScript utils with `ts-` (`py-sleep-call`, `ts-in-loop`): util ids are global.
3. Add `rule-tests/<lang>/<rule-file-name>-test.yml` with the same `id`. It needs `invalid` cases and `valid` near-misses: code that looks like the shortcut but is fine (`sleep(0)`, a sleep inside a loop for the fixed-sleep rule, a helper named `sleep`). Without them, false positives get in.
4. Run both test commands from the [README](README.md#tests):
   ```
   ast-grep test -c sgconfig.yml --skip-snapshot-tests
   python3 -m unittest discover -s tests -v
   ```
5. Check the rule on a real repo that uses the language: a shallow clone (`git clone --depth 1 <url> /tmp/x`), then `caltrop check /tmp/x`. Read the hits. Each one should be a real shortcut; fix the rule or add a `valid` case for each one that is not. Put what you checked, and the hit counts, in the PR. The clone is read-only: never run its code, never run `caltrop baseline` on someone else's repo, and never commit a `caltrop.toml` to it.
6. Update the README: a row in the language's rules table (id, what it matches, the message) and anything it misses under Known limits.

## Adding a language

1. Check ast-grep parses it. If the files need another grammar's parser, map them in `languageGlobs` in `sgconfig.yml`, as `.svelte` (html) and `.js` (typescript) are.
2. Add `rules/<lang>/`, `utils/<lang>/` and `rule-tests/<lang>/`, with a suffix for the rule files and a prefix for the utils, and add the suffix to `base_id()` in `caltrop`.
3. Define "test code" once and reuse it in every rule: a util like `in-test-code` (Rust), or the same `files:` globs in each rule (Python, TypeScript). Rules like `no-test-swap` use the inverse.
4. Add a README section: the rules table, what "test code" means, and Known limits.

## Versions

Say the version impact in the PR, from [docs/versions.md](docs/versions.md). A new rule, a new language, or a fix that removes a false positive changes hit counts: MINOR. Messages, docs and tests: PATCH. A removed or renamed rule id: MAJOR. Do not change `VERSION`; the release PR does.
