"""Deterministic, synthetic Directus responder.

The responder is NOT trying to be a faithful Directus. Its only jobs are to be
(a) deterministic and (b) shaped enough to carry each seed script through its
logic without crashing so early that the golden captures nothing. The recorded
*request* sequence is what we lock; responses just steer the script down a
fixed path. Both the pre-port and post-port runs use this exact policy, so the
synthetic ids line up and the sequences are comparable.

Default policy:
  POST /auth/login|/auth/refresh -> 200 access_token
  POST .../graphql               -> 200 {"data":{}}   (no errors -> retry exits)
  GET single-resource (no query) -> 404               (drives create paths)
  GET list/query                 -> 200 {"data":[]}
  POST                           -> 200 created item, id "SEED-000N" in call order
  PATCH                          -> 200 echo
  DELETE                         -> 204
  else                           -> 200 {"data":null}

Per-script fixtures override the default via ``overrides`` — a list of
``(matcher(method, path, body) -> bool, (status, json))`` consulted first.
"""
from urllib.parse import urlsplit

_LOGIN_BODY = {
    "data": {
        "access_token": "FAKE_DEMO_TOKEN",
        "refresh_token": "FAKE_REFRESH",
        "expires": 900000,
    }
}

# single-resource existence checks: GET /<kind>/<...>/<id> with no query string
_COLL_KINDS = ("items", "fields", "relations", "permissions")
_ROOT_KINDS = ("users", "roles", "policies", "files", "folders", "presets")


class Responder:
    def __init__(self, overrides=None):
        self.overrides = list(overrides or [])
        self._post_counter = 0

    def respond(self, method, path, body):
        method = method.upper()
        for matcher, result in self.overrides:
            if matcher(method, path, body):
                return result

        split = urlsplit(path)
        p = split.path
        has_query = bool(split.query)

        if method == "POST" and p in ("/auth/login", "/auth/refresh"):
            return (200, _dup(_LOGIN_BODY))
        if method == "POST" and p.rstrip("/").endswith("/graphql"):
            return (200, {"data": {}})

        if method == "GET":
            if self._is_existence(p, has_query):
                return (404, {"errors": [{"message": "not found",
                                          "extensions": {"code": "RECORD_NOT_FOUND"}}]})
            return (200, {"data": []})

        if method == "POST":
            self._post_counter += 1
            sid = "SEED-%04d" % self._post_counter
            echo = _parse(body)
            if isinstance(echo, dict):
                data = dict(echo)
                data.setdefault("id", sid)
            elif isinstance(echo, list):
                data = echo
            else:
                data = {"id": sid}
            return (200, {"data": data})

        if method == "PATCH":
            echo = _parse(body)
            data = dict(echo) if isinstance(echo, dict) else {}
            data.setdefault("id", "SEED-PATCHED")
            return (200, {"data": data})

        if method == "DELETE":
            return (204, None)

        return (200, {"data": None})

    @staticmethod
    def _is_existence(p, has_query):
        if has_query:
            return False
        segs = [s for s in p.split("/") if s]
        if len(segs) >= 3 and segs[0] in _COLL_KINDS:
            return True
        if len(segs) == 2 and segs[0] in _ROOT_KINDS:
            return True
        return False


def _parse(body):
    if not body:
        return None
    if isinstance(body, bytes):
        try:
            import json

            return json.loads(body)
        except Exception:
            return "<non-json>"
    return body


def _dup(obj):
    import copy

    return copy.deepcopy(obj)
