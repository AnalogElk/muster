"""Per-script golden test: run each in-scope seed script through the harness and
assert its recorded HTTP request sequence is byte-identical to the committed
golden. This is the safety net for the shared-client refactor.
"""
import difflib

import pytest
from scope import golden_path, read_scope, run_harness, slug

SCRIPTS = read_scope()


def test_scope_is_non_empty():
    assert SCRIPTS, "SCOPE.txt yielded no scripts"


@pytest.mark.parametrize("rel", SCRIPTS, ids=[slug(s) for s in SCRIPTS])
def test_request_sequence_matches_golden(rel):
    gp = golden_path(rel)
    assert gp.exists(), (
        "missing golden for %s; run: .venv/bin/python gen_goldens.py --all" % rel
    )
    out, err, rc = run_harness(rel)
    assert rc == 0, "harness process crashed for %s:\n%s" % (rel, err)
    expected = gp.read_text()
    if out != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                out.splitlines(),
                fromfile="golden",
                tofile="actual",
                lineterm="",
            )
        )
        pytest.fail("request sequence changed for %s:\n%s" % (rel, diff[:6000]))
