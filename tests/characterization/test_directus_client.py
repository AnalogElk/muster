"""Unit tests for the shared Directus client, in isolation from any seed script.

These inspect RAW request headers/bodies (not the masked golden records) so we
can assert exact token values and serialization — the divergent auth semantics
are the whole reason a single shared client is risky.
"""
import importlib.util
import io
import json
import pathlib
import urllib.error
import urllib.request
from email.message import Message
from urllib.parse import urlsplit

from harness.determinism import freeze
from harness.responder import Responder

_CLIENT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "provision"
    / "seed-full"
    / "_client"
    / "directus_client.py"
)
_spec = importlib.util.spec_from_file_location("directus_client", _CLIENT_PATH)
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

BASE = "https://cms.musterr.dev"


def capture(fn, overrides=None):
    """Run fn() with urlopen stubbed; return (raw_requests, fn_result)."""
    responder = Responder(overrides or [])
    raw = []
    orig = urllib.request.urlopen

    def fake(req, data=None, timeout=None, *a, **k):
        raw.append(
            {
                "method": req.get_method(),
                "url": req.full_url,
                "headers": dict(req.header_items()),
                "body": req.data,
            }
        )
        s = urlsplit(req.full_url)
        path = s.path + (("?" + s.query) if s.query else "")
        status, obj = responder.respond(req.get_method(), path, req.data)
        payload = b"" if obj is None else json.dumps(obj).encode()
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "stub", Message(), io.BytesIO(payload))

        class _R:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_):
                return payload

            @property
            def status(self_):
                return status

        return _R()

    urllib.request.urlopen = fake
    try:
        result = fn()
    finally:
        urllib.request.urlopen = orig
    return raw, result


# ---------------------------------------------------------------- load_env
def test_load_env_parses_dotenv(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nDIRECTUS_ADMIN_TOKEN = abc123 \n\nEMPTY=\nX=y=z\n")
    env = dc.load_env(str(p))
    assert env["DIRECTUS_ADMIN_TOKEN"] == "abc123"
    assert env["EMPTY"] == ""
    assert env["X"] == "y=z"  # only first '=' splits


# ---------------------------------------------------------------- make_req
def test_req_default_token_sends_bearer_and_no_body_on_get():
    req = dc.make_req(BASE, "DEF", timeout=45)
    raw, _ = capture(lambda: req("GET", "/items/x?limit=1"))
    assert raw[0]["url"] == "https://cms.musterr.dev/items/x?limit=1"
    assert raw[0]["headers"]["Authorization"] == "Bearer DEF"
    assert raw[0]["body"] is None


def test_req_token_none_omits_auth():
    req = dc.make_req(BASE, "DEF")
    raw, _ = capture(lambda: req("GET", "/items/x?limit=1", token=None))
    assert "Authorization" not in raw[0]["headers"]


def test_req_post_body_is_exact_json_dumps_bytes():
    req = dc.make_req(BASE, "DEF")
    payload = {"b": 2, "a": 1}
    raw, _ = capture(lambda: req("POST", "/items/x", payload))
    assert raw[0]["body"] == json.dumps(payload).encode() == b'{"b": 2, "a": 1}'


def test_req_raw_url_overrides_base():
    req = dc.make_req(BASE, "DEF")
    raw, _ = capture(lambda: req("GET", "/ignored", raw_url="https://picsum.photos/seed/x/1/1"))
    assert raw[0]["url"] == "https://picsum.photos/seed/x/1/1"


def test_req_swallows_http_error_returns_status_and_json():
    req = dc.make_req(BASE, "DEF")
    # existence GET -> responder returns 404 with an errors body
    _, result = capture(lambda: req("GET", "/fields/os_tasks/workspace"))
    status, body = result
    assert status == 404
    assert body["errors"][0]["message"] == "not found"


# ---------------------------------------------------------------- make_request
def test_request_default_token_uses_base_bearer():
    request = dc.make_request(BASE, "DEF")
    raw, _ = capture(lambda: request("GET", "/items/x?limit=1"))
    assert raw[0]["headers"]["Authorization"] == "Bearer DEF"


def test_request_custom_token_overrides():
    request = dc.make_request(BASE, "DEF")
    raw, _ = capture(lambda: request("GET", "/items/x?limit=1", token="OTHER"))
    assert raw[0]["headers"]["Authorization"] == "Bearer OTHER"


def test_request_no_auth_sentinel_omits_auth():
    request = dc.make_request(BASE, "DEF", no_auth_sentinel="__no_auth__")
    raw, _ = capture(lambda: request("GET", "/items/x?limit=1", token="__no_auth__"))
    assert "Authorization" not in raw[0]["headers"]


def test_request_retries_5xx_then_returns_raw():
    request = dc.make_request(BASE, "DEF", retries=3)
    always_500 = [(lambda m, p, b: True, (503, {"boom": 1}))]
    with freeze():  # no-op sleep so the backoff doesn't actually wait
        raw, result = capture(lambda: request("POST", "/items/x", {"a": 1}), overrides=always_500)
    assert len(raw) == 3  # 3 attempts
    assert result == (503, {"_raw": '{"boom": 1}'})


# ---------------------------------------------------------------- call (core transport)
def test_call_returns_status_and_body_bytes():
    raw, result = capture(
        lambda: dc.call("GET", BASE + "/items/x?limit=1", headers={"Authorization": "Bearer T"})
    )
    status, body = result
    assert status == 200
    assert body == b'{"data": []}'
    assert raw[0]["headers"]["Authorization"] == "Bearer T"


def test_call_httperror_returns_code_and_error_body():
    status, body = capture(lambda: dc.call("GET", BASE + "/fields/os_tasks/workspace"))[1]
    assert status == 404
    assert b"not found" in body


def test_call_retries_5xx_then_returns():
    always_500 = [(lambda m, p, b: True, (503, {"boom": 1}))]
    with freeze():
        raw, result = capture(
            lambda: dc.call("POST", BASE + "/items/x", data=b"{}", retries=3, retry_5xx=True),
            overrides=always_500,
        )
    assert len(raw) == 3
    assert result[0] == 503


# ---------------------------------------------------------------- make_upsert
def test_upsert_create_path():
    request = dc.make_request(BASE, "DEF")
    seen = []
    upsert = dc.make_upsert(request, bump=lambda coll, key: seen.append((coll, key)))
    raw, result = capture(lambda: upsert("os_deals", {"name": "X"}, {"name": "X"}))
    assert [r["method"] for r in raw] == ["GET", "POST"]
    assert raw[0]["url"] == "https://cms.musterr.dev/items/os_deals?filter[name][_eq]=X&fields=id&limit=1"
    assert result == ("SEED-0001", True)
    assert seen == [("os_deals", "created")]


def test_upsert_skip_path_when_existing():
    request = dc.make_request(BASE, "DEF")
    seen = []
    upsert = dc.make_upsert(request, bump=lambda coll, key: seen.append((coll, key)))
    existing = [
        (lambda m, p, b: m == "GET" and p.startswith("/items/os_deals"),
         (200, {"data": [{"id": "EXISTING"}]}))
    ]
    raw, result = capture(lambda: upsert("os_deals", {"name": "X"}, {"name": "X"}), overrides=existing)
    assert [r["method"] for r in raw] == ["GET"]  # no POST
    assert result == ("EXISTING", False)
    assert seen == [("os_deals", "skipped")]
