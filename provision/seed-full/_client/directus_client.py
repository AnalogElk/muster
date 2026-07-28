"""Configurable Directus client factories shared by the Muster seed scripts.

Two request styles existed in the wild and must both be reproducible exactly:

  * ``make_req``     -- F1/gapfix style: swallows HTTP errors and returns
                        ``(status, json|None)``; ``token=None`` omits the auth
                        header; default token is the base token.
  * ``make_request`` -- D1/run2 style: retries 5xx (+ URLError) with backoff,
                        raises URLError after the last attempt, returns
                        ``(status, json|{})``; ``token`` defaults to the base
                        token, a sentinel omits auth.

Bodies are always ``json.dumps(payload).encode()`` (default separators, no
``sort_keys``) so recorded request bytes match every original call site.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_SENTINEL = object()


def call(method, url, data=None, headers=None, timeout=45, retries=1,
         retry_5xx=False, retry_urlerror=False, backoff=None):
    """Low-level urllib transport shared by every seed script's request helper.

    Does ONLY the mechanical part: build the Request, urlopen with a timeout,
    optional retry, read the body. Returns ``(status, body_bytes, error)``:
      * success -> (status, body_bytes, None)
      * HTTP >=400 -> (code, error_body_bytes, HTTPError)  # body already read
    The caller decides whether to RAISE ``error`` (raise-style helpers), SWALLOW
    it and shape a return (swallow-style helpers), or ignore it. URLError is
    retried only when ``retry_urlerror`` and re-raised after the final attempt.
    ``backoff(attempt)`` -> seconds to sleep (default ``2*(attempt+1)``).

    The caller assembles the final url (query string included), body bytes, and
    headers, so params/ctype/multipart/raw_url/timeout variations all stay in the
    thin adapter -- this core stays universal.
    """
    if backoff is None:
        def backoff(attempt):
            return 2 * (attempt + 1)
    attempts = max(1, retries)
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(), None
        except urllib.error.HTTPError as e:
            body = e.read()
            if retry_5xx and e.code >= 500 and attempt < attempts - 1:
                time.sleep(backoff(attempt))
                continue
            return e.code, body, e
        except urllib.error.URLError:
            if retry_urlerror and attempt < attempts - 1:
                time.sleep(backoff(attempt))
                continue
            raise
    return 0, b"", None


def load_env(path="~/elk-os/.env"):
    """Parse a dotenv file into a dict (strip, skip blank/#, split on first =)."""
    env = {}
    with open(os.path.expanduser(path)) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def quote(v):
    """urllib.parse.quote(str(v), safe="") -- the query-value encoder used by
    the seed scripts' find_one/upsert filters."""
    return urllib.parse.quote(str(v), safe="")


def make_req(base, default_token, timeout=45):
    """F1/gapfix-style ``req(method, path, payload=None, token=<default>, raw_url=None)``.

    Returns ``(status, parsed_json_or_None)``. Never raises on HTTP errors.
    ``token`` omitted -> use ``default_token``; ``token=None`` (or falsy) -> no
    Authorization header; otherwise -> that token.
    """

    def req(method, path, payload=None, token=_SENTINEL, raw_url=None):
        tok = default_token if token is _SENTINEL else token
        url = raw_url or (base + path)
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if tok:
            headers["Authorization"] = "Bearer %s" % tok
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                body = resp.read()
                return resp.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
                parsed = json.loads(body) if body else None
            except Exception:
                parsed = None
            return e.code, parsed
        except Exception as e:  # noqa: BLE001 - matches original transport-error shape
            return 0, {"errors": [{"message": "transport: %s: %s" % (e.__class__.__name__, e)}]}

    return req


def make_request(base, default_token, timeout=60, retries=3, no_auth_sentinel="__no_auth__"):
    """D1/run2-style ``request(method, path, payload=None, token=None, retries=<default>)``.

    Retries on HTTP 5xx and URLError with ``sleep(2*(attempt+1))`` backoff;
    raises URLError after the final attempt; returns ``(status, json|{})`` on
    success and ``(code, {"_raw": body})`` on a non-retryable HTTP error.
    ``token`` omitted/None -> ``default_token``; ``token == no_auth_sentinel``
    -> no Authorization header.
    """

    def request(method, path, payload=None, token=None, retries=retries):
        url = base + path
        data = json.dumps(payload).encode() if payload is not None else None
        for attempt in range(retries):
            headers = {"Content-Type": "application/json"}
            if token != no_auth_sentinel:
                headers["Authorization"] = "Bearer " + (token or default_token)
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                    return r.status, json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")
                if e.code >= 500 and attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return e.code, {"_raw": body}
            except urllib.error.URLError:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        return 0, {}

    return request


def make_find_one(request_fn, quote_fn=quote):
    """``find_one(coll, filters) -> id|None`` using ``filter[f][_eq]=..&fields=id&limit=1``."""

    def find_one(coll, filters):
        parts = ["filter[%s][_eq]=%s" % (f, quote_fn(v)) for f, v in filters.items()]
        st, r = request_fn("GET", "/items/%s?%s&fields=id&limit=1" % (coll, "&".join(parts)))
        if st == 200 and r.get("data"):
            return r["data"][0]["id"]
        return None

    return find_one


def make_upsert(request_fn, bump=None, quote_fn=quote, find_one=None):
    """``upsert(coll, filters, payload) -> (id, created_bool)``.

    find_one -> skip if present; else POST /items/<coll>. Calls ``bump(coll,
    key)`` when provided and prints a FAIL line on a non-2xx create (matching
    the original D1 helper).
    """
    _find_one = find_one or make_find_one(request_fn, quote_fn)

    def upsert(coll, filters, payload):
        existing = _find_one(coll, filters)
        if existing is not None:
            if bump:
                bump(coll, "skipped")
            return existing, False
        st, r = request_fn("POST", "/items/" + coll, payload)
        if st in (200, 201):
            if bump:
                bump(coll, "created")
            return r["data"]["id"], True
        if bump:
            bump(coll, "failed")
        print("  FAIL %s %s -> %s %s" % (coll, filters, st, str(r)[:200]))
        return None, False

    return upsert
