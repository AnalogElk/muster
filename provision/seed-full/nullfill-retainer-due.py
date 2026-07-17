#!/usr/bin/env python3
"""Null-fill (authorized, run 2 full-auto): set due_date on the Care Plan
Retainer project so the client projects card stops reading 'Due Not set'.
Only writes when the field is null (never overwrites non-null). Idempotent.
Prints demo content only; the token never renders."""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://cms.musterr.dev"


def load_env():
    env = {}
    path = os.path.join(os.path.expanduser("~"), "elk-os", ".env")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(path, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    data = None
    if body is not None:
        r.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(r, data=data, timeout=30) as resp:
        return json.load(resp)


rows = req("/items/os_projects?filter[name][_icontains]=" + urllib.parse.quote("Care Plan Retainer") + "&fields=id,name,due_date,start_date,organization")["data"]
if not rows:
    print("no Care Plan Retainer project found; nothing to do")
    raise SystemExit(0)

for p in rows:
    if p.get("due_date"):
        print(f"skip {p['name']} ({p['id']}): due_date already {p['due_date']}")
        continue
    # Current retainer term end: end of 2026. Realistic for an active care plan.
    req(f"/items/os_projects/{p['id']}", method="PATCH", body={"due_date": "2026-12-31"})
    print(f"null-filled {p['name']} ({p['id']}): due_date -> 2026-12-31")
