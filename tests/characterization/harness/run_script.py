"""Run a real seed script under the stubbed transport + frozen clock and emit
its exact HTTP request sequence as JSONL on stdout.

Usage:  python -m harness.run_script /abs/path/to/seed-X.py

The script's own stdout is redirected to a sink so stdout carries ONLY the
JSONL golden. If the script raises (or exits), whatever prefix was recorded is
still emitted — a partial golden is a valid byte-identical bar for a port.
"""
import contextlib
import importlib.util
import io
import os
import runpy
import sys
import tempfile

from .determinism import freeze
from .recorder import dumps_jsonl
from .responder import Responder
from .transport import install_transport

FAKE_TOKEN = "SEED_TEST_TOKEN"


def _load_overrides(stem, base_dir):
    path = os.path.join(base_dir, "overrides", stem + ".py")
    if not os.path.exists(path):
        return []
    spec = importlib.util.spec_from_file_location("override_" + stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "OVERRIDES", [])


def _fake_home():
    home = tempfile.mkdtemp(prefix="seedhome-")
    os.makedirs(os.path.join(home, "elk-os"), exist_ok=True)
    with open(os.path.join(home, "elk-os", ".env"), "w") as f:
        f.write("DIRECTUS_ADMIN_TOKEN=%s\n" % FAKE_TOKEN)
    return home


def run(target, base_dir):
    stem = os.path.splitext(os.path.basename(target))[0]
    records = []
    responder = Responder(_load_overrides(stem, base_dir))

    os.environ["HOME"] = _fake_home()
    os.environ["DIRECTUS_ADMIN_TOKEN"] = FAKE_TOKEN
    os.environ.pop("DIRECTUS_URL", None)

    restore = install_transport(records, responder)
    real_stdout, real_stderr = sys.stdout, sys.stderr
    exc = None
    try:
        with freeze():
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    runpy.run_path(target, run_name="__main__")
                except SystemExit as e:
                    exc = ("SystemExit", str(e))
                except Exception as e:  # noqa: BLE001 - partial run is intentional
                    exc = (type(e).__name__, str(e))
    finally:
        restore()

    real_stdout.write(dumps_jsonl(records))
    real_stdout.flush()
    if exc:
        real_stderr.write("[harness] %s: ended with %s: %s\n" % (stem, exc[0], exc[1]))


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    target = os.path.abspath(argv[1])
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run(target, base_dir)


if __name__ == "__main__":
    main()
