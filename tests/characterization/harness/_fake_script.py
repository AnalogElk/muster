"""Tiny stand-in seed script for the harness self-check. Not a test module
(underscore prefix keeps pytest from collecting it). Does one existence GET
then a POST, mirroring the real idempotency pattern.
"""
import json
import os
import urllib.error
import urllib.request

BASE = "https://cms.musterr.dev"
TOKEN = os.environ["DIRECTUS_ADMIN_TOKEN"]


def req(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN}
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


st, _ = req("GET", "/fields/os_tasks/workspace")
if st != 200:
    req("POST", "/fields/os_tasks", {"field": "workspace", "type": "string"})
print("fake script done")  # captured by the harness sink, not stdout
