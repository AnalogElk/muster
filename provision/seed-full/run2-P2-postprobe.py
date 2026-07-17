#!/usr/bin/env python3
"""Run 2 / P2 post-probe: end-to-end evidence for os_ai_commits,
os_web_vitals, os_interactions. Prints counts/statuses/shapes only.
Never prints tokens (session tokens stay in variables)."""
import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

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


ADMIN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def jreq(url, method="GET", body=None, token=None, opener=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    op = opener.open if opener else urllib.request.urlopen
    try:
        with op(r, timeout=45) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


print("== A. demo-user-scoped Directus reads (proves the permission grants) ==")
st, data = jreq(BASE + "/auth/login", "POST",
                {"email": "demo@muster.dev", "password": "muster-demo"})
if st != 200:
    print(f"  demo directus login FAILED: HTTP {st}")
else:
    demo_token = data["data"]["access_token"]  # never printed
    for c in ("os_ai_commits", "os_web_vitals", "os_interactions"):
        st, d = jreq(f"{BASE}/items/{c}?limit=1&meta=filter_count", token=demo_token)
        n = (d.get("meta") or {}).get("filter_count")
        print(f"  demo read {c}: HTTP {st} filter_count={n}")
    # write must still be denied (read-only policy)
    st, d = jreq(f"{BASE}/items/os_ai_commits", "POST",
                 {"commit_sha": "deny-check"}, token=demo_token)
    print(f"  demo CREATE os_ai_commits (must be 403): HTTP {st}")

print("== B. portal API routes as demo session (the three tabs' data calls) ==")
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
st, _ = jreq(APP + "/api/auth/login", "POST",
             {"email": "demo@muster.dev", "password": "muster-demo"}, opener=opener)
print(f"  portal login: HTTP {st} cookies={len(cj)}")

st, d = jreq(APP + "/api/portal/analytics/ai-ledger", opener=opener)
rows = d.get("rows", [])
first = rows[0] if rows else {}
print(f"  ai-ledger: HTTP {st} rows={len(rows)}")
if rows:
    print(f"    first: sha={str(first.get('commit_sha'))[:8]} repo={first.get('repo_slug')} "
          f"type={first.get('commit_type')} cost={first.get('est_cost_usd')} "
          f"(json type {type(first.get('est_cost_usd')).__name__}) "
          f"tokens_in={first.get('input_tokens')} outcome={first.get('outcome')}")
    repos = sorted({r.get("repo_slug") for r in rows})
    total_cost = round(sum(r.get("est_cost_usd") or 0 for r in rows), 2)
    print(f"    repos({len(repos)}): {', '.join(repos)}")
    print(f"    total est cost across ledger: {total_cost}")

for days in (7, 30):
    st, d = jreq(f"{APP}/api/portal/analytics/vitals?days={days}", opener=opener)
    ov = {o["metric"]: (o["p75"], o["rating"], o["count"]) for o in d.get("overall", [])}
    print(f"  vitals?days={days}: HTTP {st} total={d.get('total')} routes={len(d.get('routes', []))}")
    for m, (p75, rating, cnt) in ov.items():
        print(f"    {m}: p75={p75} rating={rating} n={cnt}")

for days in (7, 30):
    st, d = jreq(f"{APP}/api/portal/analytics/heatmap?days={days}", opener=opener)
    print(f"  heatmap?days={days}: HTTP {st} total={d.get('total')} "
          f"routes={len(d.get('routes', []))} selected={d.get('selectedRoute')} "
          f"points={len(d.get('points', []))} "
          f"scrollBands_nonzero={sum(1 for b in d.get('scrollBands', []) if b.get('pct'))}")
    for r in d.get("routes", [])[:4]:
        print(f"    route {r['route']}: clicks={r['clicks']} scrolls={r['scrollSamples']}")

print("== C. day-spread sanity (admin): rows outside the last 7 days exist ==")
now = datetime.now(timezone.utc)
cut = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
for c in ("os_web_vitals", "os_interactions"):
    st, d = jreq(f"{BASE}/items/{c}?filter[date_created][_lt]={cut}&aggregate[count]=id", token=ADMIN)
    cnt = d.get("data", [{}])[0].get("count", {})
    cnt = cnt if not isinstance(cnt, dict) else cnt.get("id")
    print(f"  {c} rows older than 7d: {cnt}")
st, d = jreq(f"{BASE}/items/os_ai_commits?filter[committed_at][_lt]={cut}&aggregate[count]=id", token=ADMIN)
cnt = d.get("data", [{}])[0].get("count", {})
cnt = cnt if not isinstance(cnt, dict) else cnt.get("id")
print(f"  os_ai_commits commits older than 7d: {cnt}")
print("done")
