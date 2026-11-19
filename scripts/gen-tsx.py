#!/usr/bin/env python3
"""Write the tsx copies of the TypeScript rules, utils and rule-tests. ast-grep parses .tsx/.jsx as a separate
language, so each typescript rule needs a tsx twin. Edit the ts files, then run this. --check: fail if out of date."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEAD = "# Generated from {} by scripts/gen-tsx.py; edit that file and re-run.\n"
# JSX cases on top of the copied ts tests, to show the rules see through JSX.
EXTRA = {
    "no-fixed-sleep": ("invalid", "it('x', async () => { render(<App />); await sleep(100); });"),
    "no-mock-libs": ("invalid", "vi.mock('./api'); it('x', () => { render(<List items={[]} />); });"),
    "no-ignored-test": ("invalid", "it.skip('renders', () => { render(<App />); });"),
    "no-test-swap": ("invalid", "export const App = () => process.env.NODE_ENV === 'test' ? <Fake /> : <Real />;"),
}


def outputs():
    utils = sorted((ROOT / "utils/ts").glob("ts-*.yml"))
    util_ids = [u.stem for u in utils]

    def convert(src, text):
        text = text.replace("language: typescript", "language: tsx")
        text = re.sub(r"^id: (\S+)-ts$", r"id: \1-tsx", text, flags=re.M)
        for u in util_ids:
            text = re.sub(rf"\b{u}\b", "tsx-" + u.removeprefix("ts-"), text)
        return HEAD.format(src.relative_to(ROOT).as_posix()) + text

    out = {}
    for u in utils:
        out[ROOT / "utils/tsx" / ("tsx-" + u.name.removeprefix("ts-"))] = convert(u, u.read_text())
    for r in sorted((ROOT / "rules/ts").glob("*-ts.yml")):
        out[ROOT / "rules/tsx" / (r.stem + "x.yml")] = convert(r, r.read_text())
    for t in sorted((ROOT / "rule-tests/ts").glob("*-ts-test.yml")):
        text = convert(t, t.read_text())
        rule = t.name.removesuffix("-ts-test.yml")
        if rule in EXTRA:
            kind, case = EXTRA[rule]
            text = text.replace(f"{kind}:\n", f"{kind}:\n  - {json.dumps(case)}\n", 1)
        out[ROOT / "rule-tests/tsx" / (rule + "-tsx-test.yml")] = text
    return out


def main(argv):
    out = outputs()
    stale = [p for p, text in out.items() if not p.is_file() or p.read_text() != text]
    extra = [p for d in ("rules/tsx", "utils/tsx", "rule-tests/tsx") for p in (ROOT / d).glob("*.yml") if p not in out]
    if argv[1:] == ["--check"]:
        for p in stale + extra:
            print(f"out of date: {p.relative_to(ROOT)}; run scripts/gen-tsx.py")
        return 1 if stale or extra else 0
    for p in extra:
        p.unlink()
    for p in stale:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out[p])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
