# Versions and releases

caltrop uses `vMAJOR.MINOR.PATCH`. One number covers the script, the rules and the allowlist format. `caltrop --version` prints it.

A consumer repo's `caltrop check` fails when its hit counts go up or down, so the number says what an upgrade does to those counts.

| Part | Meaning |
|---|---|
| MAJOR | A change that breaks a consumer's `caltrop.toml` or CI setup: a rule id removed or renamed, a changed allowlist format, command, exit code or output line format, or a new required ast-grep version. Say in the release notes what a consumer must change. |
| MINOR | New rules, new languages, or a rule change that finds more or fewer hits. A consumer's counts may move: after upgrading, fix the new hits or lower the allowances. Do not re-run `caltrop baseline` to hide new hits. |
| PATCH | No hit count changes in any repo: messages, docs, tests, bug fixes in error handling, internal cleanups. A consumer can bump without touching `caltrop.toml`. |

A rule fix that removes a false positive changes counts, so it is MINOR, not PATCH.

## Where we are

Before v1.0.0, caltrop had no versions and consumers pinned a commit (vesper pins `4a6ed53`).

- **v1.0.0**: the first version. Rust rules, plus Python and TypeScript, JavaScript and Svelte. Python and TypeScript rules share allowlist ids with the Rust ones (`no-fixed-sleep`, `no-test-swap` and the rest), and two ids are new: `no-mock-libs` and `no-focused-test`. `.svelte` files are parsed as HTML, so the TypeScript rules run inside `<script lang="ts">`. pytest reruns are read from `pyproject.toml`, `pytest.ini`, `setup.cfg` and `tox.ini` anywhere in the repo. `node_modules` and `site-packages` are skipped. Adds `caltrop --version`. For Rust code the counts are the same as at `b13ef7e`; a repo pinned earlier also gets that commit's five newer Rust rules (`no-ignored-test`, `no-weak-result-assert`, `no-silent-skip`, `no-fake-impls`, and `no-test-swap` on test-only cargo features). A repo with TypeScript, JavaScript or Python files gets new hits: fix them or add allowances. Checked against food-laptop (FastAPI and SvelteKit) and vesper (whose `web/` adds about 220 TypeScript and JavaScript hits, most of them sleeps in `web/e2e/*.mjs`). Not verified: other Python or Svelte codebases.

## How a release is cut

1. Work lands on `main` by pull request. CI must be green. Nothing is merged to `main` without a pull request.
2. Open a pull request named `Release vX.Y.Z` from a `release/X.Y.Z` branch, with one commit `chore(release): vX.Y.Z`. It sets `VERSION` in the `caltrop` script and adds the version's line under "Where we are" above, with what changes for consumers and what was not verified. Pick the number from the table above. Run the tests in the README first.
3. After it is merged, tag the merge commit: `git tag -a vX.Y.Z -m "caltrop vX.Y.Z" && git push origin vX.Y.Z`.
4. Create the GitHub release from the tag: `gh release create vX.Y.Z --generate-notes`. The notes are the merged pull requests. There is no CHANGELOG file.
5. Bump the consumers (vesper) to the tag in their own pull requests, and fix or allow the new hits there.
