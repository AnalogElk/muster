import time
import uuid
from datetime import datetime, timezone

from harness.determinism import freeze


def test_uuid_and_sleep_are_deterministic():
    with freeze():
        assert str(uuid.uuid4()) == "00000000-0000-4000-8000-000000000000"
        assert str(uuid.uuid4()) == "00000000-0000-4000-8000-000000000001"
        t0 = time.time()
        time.sleep(9999)  # must be a no-op, or the test hangs
        t1 = time.time()
        assert t0 == t1  # clock frozen


def test_datetime_is_frozen():
    with freeze():
        assert datetime.now(timezone.utc).isoformat() == "2026-01-01T00:00:00+00:00"
        assert datetime.utcnow().isoformat() == "2026-01-01T00:00:00"


def test_uuid_counter_resets_each_freeze():
    with freeze():
        assert str(uuid.uuid4()).endswith("000000000000")
    with freeze():
        assert str(uuid.uuid4()).endswith("000000000000")


def test_restores_originals_on_exit():
    orig_sleep = time.sleep
    with freeze():
        assert time.sleep is not orig_sleep
    assert time.sleep is orig_sleep
    # real uuid4 is random again
    assert str(uuid.uuid4()) != "00000000-0000-4000-8000-000000000000"
