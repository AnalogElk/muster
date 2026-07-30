#!/usr/bin/env python
"""Generate/refresh golden request-sequence files from the CURRENT script code.

    python gen_goldens.py --all           # regenerate every in-scope script
    python gen_goldens.py seed-F1 seed-D1  # only scripts whose path matches an arg

Run from tests/characterization with the harness venv:
    .venv/bin/python gen_goldens.py --all

WARNING: only run this to establish the baseline (before refactoring) or after a
DELIBERATE, reviewed behavior change. During porting, goldens are the oracle and
must NOT be regenerated to make a failing port pass.
"""
import sys

from scope import GOLDENS, golden_path, read_scope, run_harness, slug


def main(argv):
    GOLDENS.mkdir(exist_ok=True)
    args = argv[1:]
    scripts = read_scope()
    if args and args != ["--all"]:
        scripts = [s for s in scripts if any(a in s for a in args)]
    if not scripts:
        print("no scripts matched", file=sys.stderr)
        return 1
    partials = 0
    for rel in scripts:
        out, err, rc = run_harness(rel)
        golden_path(rel).write_text(out)
        note = ""
        if err.strip():
            partials += 1
            note = "  PARTIAL: " + err.strip().splitlines()[-1]
        print("%-46s %4d reqs  rc=%d%s" % (slug(rel), len(out.splitlines()), rc, note))
    print("\n%d scripts, %d partial runs" % (len(scripts), partials))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
