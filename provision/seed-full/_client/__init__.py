"""Shared Directus client for the Muster provision seed scripts.

Extracted from the duplicated ``load_env`` / ``req`` / ``request`` / ``upsert``
helpers that had drifted across ~50 scripts. The factories are configurable so
each ported script reproduces its ORIGINAL behavior byte-for-byte (verified by
the golden request-sequence tests under tests/characterization).
"""
from .directus_client import (  # noqa: F401
    call,
    load_env,
    make_find_one,
    make_req,
    make_request,
    make_upsert,
    quote,
)
