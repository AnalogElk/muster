import base64
import pathlib
import subprocess
import sys

from harness.recorder import loads_jsonl

HARNESS_DIR = pathlib.Path(__file__).parent
CCHAR_DIR = HARNESS_DIR.parent  # tests/characterization


def _run():
    import os

    proc = subprocess.run(
        [sys.executable, "-m", "harness.run_script", str(HARNESS_DIR / "_fake_script.py")],
        cwd=str(CCHAR_DIR),
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONHASHSEED="0"),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_selfcheck_is_deterministic_masked_and_captures_body():
    a = _run()
    b = _run()
    assert a == b, "harness output must be byte-identical across runs"

    recs = loads_jsonl(a)
    assert [r.method for r in recs] == ["GET", "POST"]

    # bearer masked everywhere; the fake token never leaks into the golden
    assert "SEED_TEST_TOKEN" not in a
    for r in recs:
        assert dict(r.headers).get("authorization") in (None, "Bearer <token>")

    # POST body captured as the exact json.dumps bytes (serialization fidelity)
    post = recs[1]
    assert base64.b64decode(post.body_b64) == b'{"field": "workspace", "type": "string"}'
