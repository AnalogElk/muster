"""Freeze all sources of non-determinism so a script's recorded request
sequence is reproducible byte-for-byte.

Frozen: wall clock + monotonic time (freezegun), ``time.sleep`` (no-op so
retry loops don't wait), ``uuid.uuid4`` (a stable counter), ``random`` (seed 0).
Entering :func:`freeze` before a script imports guarantees ``from uuid import
uuid4`` / ``from time import sleep`` bind to the patched versions.
"""
import contextlib
import itertools
import os
import random
import time
import uuid

from freezegun import freeze_time

FROZEN_INSTANT = "2026-01-01T00:00:00Z"


@contextlib.contextmanager
def freeze():
    counter = itertools.count()

    def fake_uuid4():
        return uuid.UUID(f"00000000-0000-4000-8000-{next(counter):012x}")

    # Deterministic entropy: secrets.token_* -> os.urandom (call-time lookup);
    # random.SystemRandom -> random._urandom (bound at import). Patch both so
    # generated passwords/tokens are stable across runs.
    det = random.Random(0)

    def fake_urandom(n):
        return bytes(det.getrandbits(8) for _ in range(n))

    orig_uuid4 = uuid.uuid4
    orig_sleep = time.sleep
    orig_urandom = os.urandom
    orig_rand_urandom = getattr(random, "_urandom", None)
    with freeze_time(FROZEN_INSTANT):
        uuid.uuid4 = fake_uuid4
        time.sleep = lambda *_a, **_k: None
        os.urandom = fake_urandom
        if orig_rand_urandom is not None:
            random._urandom = fake_urandom
        random.seed(0)
        try:
            yield
        finally:
            uuid.uuid4 = orig_uuid4
            time.sleep = orig_sleep
            os.urandom = orig_urandom
            if orig_rand_urandom is not None:
                random._urandom = orig_rand_urandom
