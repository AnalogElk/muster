#!/usr/bin/env python3
"""Run 2 / P2 pre-probe: live state before creating os_ai_commits,
os_web_vitals, os_interactions. Prints only demo-content metadata, counts,
statuses. Never prints tokens."""
import json
import os
import urllib.request
import urllib.error

BASE = "https://cms.musterr.dev"
APP = "https://app.musterr.dev"


def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(path, method="GET", body=None, base=BASE, headers=None):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if base == BASE:
        h["Authorization"] = "Bearer " + TOKEN
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


print("== 1. target collections exist? ==")
for c in ("os_ai_commits", "os_web_vitals", "os_interactions"):
    st, _ = req(f"/collections/{c}")
    print(f"  {c}: HTTP {st}")

print("== 2. os_token_usage field types (reference for numeric types) ==")
st, data = req("/fields/os_token_usage")
if st == 200:
    for f in data["data"]:
        print(f"  {f['field']}: type={f['type']}")

print("== 3. os_token_usage sample row JSON value types ==")
st, data = req("/items/os_token_usage?limit=1")
if st == 200 and data.get("data"):
    row = data["data"][0]
    for k, v in row.items():
        print(f"  {k}: {type(v).__name__} = {json.dumps(v)[:80]}")

print("== 4. repositories (live) ==")
st, data = req("/repositories?limit=-1&fields=id,name,platform,status,project_id.id,project_id.name")
if st == 200:
    for r in data["data"]:
        proj = r.get("project_id") or {}
        print(f"  {r['name']} | platform={r.get('platform')} | status={r.get('status')} | project={proj.get('name')}")
else:
    # maybe items path
    st, data = req("/items/repositories?limit=-1&fields=id,name,platform,status,project_id.id,project_id.name")
    print(f"  via /items: HTTP {st}")
    if st == 200:
        for r in data["data"]:
            proj = r.get("project_id") or {}
            print(f"  {r['name']} | platform={r.get('platform')} | status={r.get('status')} | project={proj.get('name')}")

print("== 5. organizations ids ==")
st, data = req("/items/organizations?limit=-1&fields=id,name")
if st == 200:
    for o in data["data"]:
        print(f"  org {o['id']}: {o['name']}")

print("== 6. demo policy permission rows for targets ==")
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
st, data = req(f"/permissions?filter[policy][_eq]={DEMO_POLICY}&limit=-1&fields=id,collection,action")
if st == 200:
    rows = data["data"]
    print(f"  total permission rows on demo policy: {len(rows)}")
    for r in rows:
        if r["collection"] in ("os_ai_commits", "os_web_vitals", "os_interactions"):
            print(f"  MATCH: {r}")
    # sanity: confirm the policy exists at all
else:
    print(f"  HTTP {st}: {json.dumps(data)[:200]}")

print("== 7. team users (for user_id attribution) ==")
st, data = req("/users?limit=-1&fields=id,email,first_name,last_name")
if st == 200:
    for u in data["data"]:
        print(f"  {u['id']} {u.get('email')}")

print("== 8. portal end-to-end pre-check (demo session) ==")
st, login = req("/api/auth/login", "POST", {"email": "demo@muster.dev", "password": "muster-demo"}, base=APP)
print(f"  login: HTTP {st}")
# portal sets cookies; but the JSON may include tokens. Use cookie jar via headers.
# We need Set-Cookie; urllib basic req above discards headers. Do it manually:
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
lr = urllib.request.Request(APP + "/api/auth/login", data=json.dumps({"email": "demo@muster.dev", "password": "muster-demo"}).encode(), method="POST", headers={"Content-Type": "application/json"})
try:
    with opener.open(lr, timeout=30) as resp:
        print(f"  cookie login: HTTP {resp.status}, cookies={len(cj)}")
except urllib.error.HTTPError as e:
    print(f"  cookie login FAILED: HTTP {e.code}")

for path in ("/api/portal/analytics/ai-ledger", "/api/portal/analytics/vitals?days=7", "/api/portal/analytics/heatmap?days=7"):
    r2 = urllib.request.Request(APP + path)
    try:
        with opener.open(r2, timeout=30) as resp:
            body = json.loads(resp.read().decode() or "{}")
            print(f"  {path}: HTTP {resp.status} keys={list(body.keys())} preview={json.dumps(body)[:160]}")
    except urllib.error.HTTPError as e:
        print(f"  {path}: HTTP {e.code} body={e.read().decode()[:160]}")

print("== done ==")
