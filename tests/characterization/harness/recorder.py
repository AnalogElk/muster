"""Canonical request-record format for golden HTTP-sequence tests.

A golden is a JSONL file, one :class:`RequestRecord` per line, capturing the
exact ordered sequence of outbound requests a seed script makes under the
stubbed transport. "Byte-identical" acceptance compares these records.
"""
import base64
import hashlib
import json
from dataclasses import asdict, dataclass

# The real bearer token is replaced with this constant in every golden so a
# secret can never land in a committed file (DevProd rule 2).
MASK = "Bearer <token>"


def canonical_headers(items):
    """Return headers as a sorted lower-cased dict with the bearer masked.

    ``items`` is any iterable of ``(key, value)`` pairs (e.g. the output of
    ``urllib.request.Request.header_items()``). Header *order* on the wire is
    not semantically meaningful to Directus, so we compare a canonical sorted
    map; the raw order is intentionally discarded here.
    """
    out = {}
    for k, v in items:
        lk = str(k).lower()
        if lk == "authorization" and str(v).startswith("Bearer "):
            v = MASK
        out[lk] = v
    return dict(sorted(out.items()))


@dataclass(frozen=True)
class RequestRecord:
    seq: int
    method: str
    url: str
    headers: tuple  # tuple of (key, value) pairs, canonical-sorted
    body_b64: str
    body_sha256: str

    @classmethod
    def build(cls, seq, method, url, header_items, body):
        body = body or b""
        if isinstance(body, str):
            body = body.encode()
        return cls(
            seq,
            str(method).upper(),
            url,
            tuple(canonical_headers(header_items).items()),
            base64.b64encode(body).decode(),
            hashlib.sha256(body).hexdigest(),
        )


def dumps_jsonl(records):
    lines = []
    for r in records:
        d = asdict(r)
        d["headers"] = [list(pair) for pair in r.headers]
        lines.append(json.dumps(d, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + ("\n" if lines else "")


def loads_jsonl(text):
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(
            RequestRecord(
                d["seq"],
                d["method"],
                d["url"],
                tuple((k, v) for k, v in d["headers"]),
                d["body_b64"],
                d["body_sha256"],
            )
        )
    return out
