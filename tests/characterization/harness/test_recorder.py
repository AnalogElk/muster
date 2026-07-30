from harness.recorder import (
    RequestRecord,
    canonical_headers,
    dumps_jsonl,
    loads_jsonl,
)


def test_canonical_headers_sorts_and_masks_bearer():
    h = canonical_headers(
        [
            ("Content-Type", "application/json"),
            ("Authorization", "Bearer REALTOKEN"),
        ]
    )
    assert list(h.items()) == [
        ("authorization", "Bearer <token>"),
        ("content-type", "application/json"),
    ]


def test_canonical_headers_leaves_non_bearer_auth_untouched():
    h = canonical_headers([("Authorization", "Basic abc123")])
    assert h == {"authorization": "Basic abc123"}


def test_jsonl_roundtrip_is_stable():
    r = RequestRecord.build(
        0, "POST", "https://x/y", [("Authorization", "Bearer t")], b'{"a":1}'
    )
    text = dumps_jsonl([r])
    assert loads_jsonl(text) == [r]
    # serialization is idempotent (re-dumping a parsed golden yields the same bytes)
    assert dumps_jsonl(loads_jsonl(text)) == text


def test_build_records_exact_body_bytes_and_hash():
    body = b'{"b":2,"a":1}'  # note: unsorted keys preserved verbatim
    r = RequestRecord.build(3, "patch", "https://x/z", [], body)
    assert r.method == "PATCH"
    import base64
    import hashlib

    assert base64.b64decode(r.body_b64) == body
    assert r.body_sha256 == hashlib.sha256(body).hexdigest()


def test_empty_body_is_stable():
    r = RequestRecord.build(0, "GET", "https://x/y", [], None)
    assert r.body_b64 == ""
    import hashlib

    assert r.body_sha256 == hashlib.sha256(b"").hexdigest()
