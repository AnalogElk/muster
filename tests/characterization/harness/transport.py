"""Monkeypatch ``urllib.request.urlopen`` to record requests and answer from
the synthetic responder. No socket is ever opened.
"""
import io
import json
import urllib.error
import urllib.request
from email.message import Message
from urllib.parse import urlsplit

from .recorder import RequestRecord


class _FakeResponse:
    """Minimal stand-in for http.client.HTTPResponse used by ``with urlopen()``."""

    def __init__(self, status, body_bytes, url):
        self.status = status
        self.code = status
        self._body = body_bytes
        self.headers = Message()
        self._url = url

    def read(self, *_a):
        return self._body

    def getcode(self):
        return self.status

    def info(self):
        return self.headers

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _path_of(url):
    s = urlsplit(url)
    return s.path + (("?" + s.query) if s.query else "")


def install_transport(records, responder):
    """Patch urlopen; append a RequestRecord per call; return a restore fn."""
    orig = urllib.request.urlopen
    counter = {"n": 0}

    def fake_urlopen(req, data=None, timeout=None, *args, **kwargs):
        if isinstance(req, str):
            method, url, header_items, body = "GET", req, [], data
        else:
            method = req.get_method()
            url = req.full_url
            header_items = req.header_items()
            body = req.data
        seq = counter["n"]
        counter["n"] += 1
        records.append(RequestRecord.build(seq, method, url, header_items, body))

        status, obj = responder.respond(method, _path_of(url), body)
        payload = b"" if obj is None else json.dumps(obj).encode()
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "stubbed", Message(),
                                         io.BytesIO(payload))
        return _FakeResponse(status, payload, url)

    urllib.request.urlopen = fake_urlopen

    def restore():
        urllib.request.urlopen = orig

    return restore
