#!/usr/bin/env python3
"""Client-dashboard top-up for the Muster demo portal (2026-07-16), wave 2b.

Companion to gapfix-tools-help-client.py. Fixes the three quality gaps still
visible on the captured client dashboard:

  A. Site Analytics card showed a red "MATOMO_AUTH_TOKEN env var is not
     configured" error: another gap-fix wave set matomo_site_id on orgs 2..8,
     which pushed /api/portal/analytics past its 404 guard into the live
     Matomo call (env empty on the box). BUT the route consults the
     `analytics_snapshots` CMS collection FIRST (lib/portal/analytics/
     snapshot-storage.ts, app/api/portal/analytics/route.ts:118) whenever
     trend==summary, range in {last7,last30,last90}, compare=prev, which is
     exactly the dashboard's request shape. Create the collection additively
     and seed fresh synthetic SiteOverviewPayload rows for sites 2..8 x the
     three ranges. NOTE: snapshots are treated as stale after 26 hours
     (SNAPSHOT_MAX_AGE_HOURS); re-running this script refreshes collected_at.
  B. Project Timeline chart hidden: buildClientSeries plots invoices via
     inv.dueDate (camelCase) but getInvoices returns due_date, so the invoice
     line is always 0 (frozen-portal field drift, not seedable); the project
     line plots p.dueDate within the PAST 90-day window and both Cedar
     projects are due in the future. Seed two COMPLETED org-2 projects with
     due dates inside the window so the chart renders (and the Completed
     Projects metric card appears).
  C. Recent Activity showed a single item: the feed fetches only the 8 most
     recent os_activity_log rows GLOBALLY, then filters to the client org.
     Seed six very recent org-2 events (client-visible targets, metadata.name
     set) so the global head contains Cedar rows.

Idempotent: collection/fields/relations/permissions checked before create;
snapshots upserted by (matomo_site_id, range_key); projects by name; activity
events by (verb, target_id, timestamp). is_test_data:false everywhere the
field exists. Admin token read from ~/elk-os/.env inside this script, never
printed. Output: counts and demo content names only.
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- access

def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

ENV = load_env()
BASE = "https://cms.musterr.dev"
TOKEN = ENV["DIRECTUS_ADMIN_TOKEN"]
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"

TODAY = datetime(2026, 7, 16, tzinfo=timezone.utc).date()

ORG_CEDAR = 2
PROJ_CEDAR_WEB = "430df3e9-7f6d-4369-81cf-d9e5dc0fab00"
PROJ_CEDAR_WHOLESALE = "a42f4921-7747-4319-b09e-644f639e89c5"


def req(path, method="GET", body=None, token=TOKEN):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, None


def die_on(status, data, ctx):
    if status >= 400:
        msg = ""
        if isinstance(data, dict):
            errs = data.get("errors") or []
            if errs:
                msg = errs[0].get("message", "")
        raise SystemExit(f"FATAL {ctx}: HTTP {status} {msg}")


def upsert(collection, natural_filter, payload):
    q = "&".join(f"filter[{k}][_eq]={urllib.parse.quote(str(v))}"
                 for k, v in natural_filter.items())
    st, data = req(f"/items/{collection}?{q}&fields=id&limit=1")
    die_on(st, data, f"search {collection}")
    if data["data"]:
        return data["data"][0]["id"], False
    st, data = req(f"/items/{collection}", "POST", payload)
    die_on(st, data, f"create {collection} row")
    return data["data"]["id"], True


def ensure_collection(name, icon, note, fields):
    st, _ = req(f"/collections/{name}")
    if st == 200:
        print(f"  collection {name}: exists")
        return False
    st, data = req("/collections", "POST", {
        "collection": name,
        "meta": {"icon": icon, "note": note, "hidden": False},
        "schema": {},
        "fields": fields,
    })
    die_on(st, data, f"create collection {name}")
    print(f"  collection {name}: CREATED")
    return True


def ensure_relation(collection, field, related, on_delete="SET NULL"):
    st, _ = req(f"/relations/{collection}/{field}")
    if st == 200:
        return False
    st, data = req("/relations", "POST", {
        "collection": collection, "field": field, "related_collection": related,
        "meta": {"one_field": None, "sort_field": None},
        "schema": {"on_delete": on_delete},
    })
    die_on(st, data, f"relation {collection}.{field} -> {related}")
    print(f"  relation {collection}.{field} -> {related}: CREATED")
    return True


def ensure_read_permission(collection):
    flt = (f"filter[policy][_eq]={DEMO_POLICY}"
           f"&filter[collection][_eq]={collection}&filter[action][_eq]=read")
    st, data = req(f"/permissions?{flt}&fields=id")
    die_on(st, data, f"list permissions {collection}")
    if data["data"]:
        return False
    st, data = req("/permissions", "POST", {
        "policy": DEMO_POLICY, "collection": collection, "action": "read",
        "fields": ["*"], "permissions": {}, "validation": None,
    })
    die_on(st, data, f"grant read {collection}")
    print(f"  permission read {collection}: GRANTED to demo policy")
    return True

# =====================================================================
# A. analytics_snapshots: collection + synthetic overview payloads
# =====================================================================
print("== A. analytics_snapshots ==")

ensure_collection("analytics_snapshots", "monitoring", "Persisted Matomo overviews (demo)", [
    {"field": "id", "type": "uuid",
     "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
     "schema": {"is_primary_key": True, "length": 36, "has_auto_increment": False}},
    {"field": "matomo_site_id", "type": "integer", "meta": {"interface": "input"}, "schema": {}},
    {"field": "organization", "type": "integer",
     "meta": {"interface": "select-dropdown-m2o", "special": ["m2o"]}, "schema": {}},
    {"field": "range_key", "type": "string",
     "meta": {"interface": "select-dropdown", "options": {"choices": [
         {"text": "Last 7", "value": "last7"},
         {"text": "Last 30", "value": "last30"},
         {"text": "Last 90", "value": "last90"}]}}, "schema": {}},
    {"field": "collected_at", "type": "timestamp", "meta": {"interface": "datetime"}, "schema": {}},
    {"field": "payload", "type": "json", "meta": {"interface": "input-code"}, "schema": {}},
    {"field": "is_test_data", "type": "boolean", "meta": {"interface": "boolean"},
     "schema": {"default_value": False}},
])
ensure_relation("analytics_snapshots", "organization", "organizations")
ensure_read_permission("analytics_snapshots")

SITE_PAGES = {
    2: ("Cedar & Co Coffee", ["/", "/menu", "/locations", "/wholesale", "/about", "/blog/spring-menu"]),
    3: ("Northlight Law", ["/", "/practice-areas", "/attorneys", "/contact", "/insights", "/careers"]),
    4: ("Vellum Studio", ["/", "/work", "/motion", "/studio", "/contact", "/journal"]),
    5: ("Harbor Fitness", ["/", "/classes", "/schedule", "/membership", "/trainers", "/contact"]),
    6: ("Bloom Botanicals", ["/", "/shop", "/collections/houseplants", "/care-guides", "/about", "/cart"]),
    7: ("Sterling & Vine", ["/", "/menu", "/reservations", "/private-dining", "/wine", "/contact"]),
    8: ("Meridian Fund", ["/", "/grants", "/apply", "/recipients", "/reports", "/contact"]),
}
RANGES = {"last7": 7, "last30": 30, "last90": 90}


def rng(seed_text):
    """Deterministic 0..1 float from a seed string (stable across runs)."""
    h = hashlib.sha256(seed_text.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def ranked(labels, total, seed):
    """Distribute `total` visits across labels, descending."""
    weights = [rng(f"{seed}:{i}:{lab}") + 0.3 for i, lab in enumerate(labels)]
    s = sum(weights)
    rows = []
    for lab, w in sorted(zip(labels, weights), key=lambda x: -x[1]):
        rows.append({"label": lab, "visits": max(1, int(total * w / s))})
    return rows


def build_payload(site_id, range_key, days):
    base_daily = 18 + int(rng(f"site{site_id}:base") * 55)  # 18..73 visits/day
    start = TODAY - timedelta(days=days - 1)
    trend = []
    visits = uniq = pv = 0
    for i in range(days):
        d = start + timedelta(days=i)
        weekend = d.weekday() >= 5
        wobble = 0.6 + rng(f"s{site_id}:{d.isoformat()}") * 0.9
        v = max(3, int(base_daily * wobble * (0.55 if weekend else 1.0)))
        u = max(2, int(v * 0.78))
        p = int(v * (2.1 + rng(f"pv{site_id}:{d.isoformat()}") * 0.9))
        trend.append({"date": d.isoformat(), "visits": v, "uniqueVisitors": u, "pageviews": p})
        visits += v
        uniq += u
        pv += p
    prior_factor = 0.82 + rng(f"prior{site_id}:{range_key}") * 0.3  # 0.82..1.12
    pvisits = int(visits * prior_factor)
    puniq = int(uniq * prior_factor)
    ppv = int(pv * prior_factor)
    avg_time = 95 + int(rng(f"time{site_id}") * 120)
    pavg_time = int(avg_time * (0.9 + rng(f"ptime{site_id}") * 0.2))
    bounce = 38 + int(rng(f"bounce{site_id}") * 18)
    pbounce = 38 + int(rng(f"pbounce{site_id}") * 18)

    def delta(cur, prev):
        absolute = cur - prev
        direction = "up" if absolute > 0 else ("down" if absolute < 0 else "flat")
        pct = round((cur - prev) / prev * 1000) / 10 if prev > 0 else None
        return {"absolute": absolute, "pct": pct, "direction": direction}

    name, pages = SITE_PAGES[site_id]
    # Shapes mirror lib/portal/analytics/matomo-overview.ts exactly:
    # topPages {label,url,visits,pageviews,avgTimeSpent}, entryPages carry
    # `entrances`, exitPages carry `exits` (site-analytics-section.tsx maps
    # p.entrances / p.exits; a missing field crashes fmtNumber at render).
    top_pages = []
    entry_pages = []
    exit_pages = []
    page_rows = ranked(pages, visits, f"pages{site_id}:{range_key}")
    for row in page_rows:
        url = f"https://site{site_id}.example{row['label']}"
        top_pages.append({
            "label": row["label"], "visits": row["visits"],
            "pageviews": int(row["visits"] * 1.6),
            "avgTimeSpent": 40 + int(rng(f"ts{site_id}:{row['label']}") * 150),
            "url": url,
        })
        lab = row["label"]
        entry_pages.append({
            "label": lab, "url": url, "visits": row["visits"],
            "entrances": max(1, int(row["visits"] * 0.7)),
            "bounceRate": "%d%%" % (35 + int(rng("ebr%s:%s" % (site_id, lab)) * 25)),
        })
        exit_pages.append({
            "label": lab, "url": url, "visits": row["visits"],
            "exits": max(1, int(row["visits"] * 0.5)),
            "exitRate": "%d%%" % (25 + int(rng("exr%s:%s" % (site_id, lab)) * 30)),
        })
    prior_start = start - timedelta(days=days)
    prior_end = start - timedelta(days=1)
    return {
        "siteId": site_id,
        "summaryDate": range_key,
        "trendDate": range_key,
        "compare": "prev",
        "priorRange": f"{prior_start.isoformat()},{prior_end.isoformat()}",
        "totals": {
            "visits": visits, "uniqueVisitors": uniq, "pageviews": pv,
            "avgTimeOnSite": avg_time, "bounceRate": f"{bounce}%",
            "pagesPerVisit": round(pv / visits, 1) if visits else 0,
        },
        "deltas": {
            "visits": delta(visits, pvisits),
            "uniqueVisitors": delta(uniq, puniq),
            "pageviews": delta(pv, ppv),
            "avgTimeOnSite": delta(avg_time, pavg_time),
            "bounceRate": delta(bounce, pbounce),
        },
        "trend": trend,
        "newReturning": [
            {"label": "New visitors", "visits": int(visits * 0.62)},
            {"label": "Returning visitors", "visits": visits - int(visits * 0.62)},
        ],
        "topPages": top_pages,
        "entryPages": entry_pages[:4],
        "exitPages": exit_pages[1:5],
        "referrers": {
            "types": ranked(["Direct entry", "Search engines", "Websites", "Social networks"],
                            visits, f"reftypes{site_id}:{range_key}"),
            "topWebsites": ranked(["yelp.com", "tripadvisor.com", "localguide.example"],
                                  int(visits * 0.2), f"refsites{site_id}:{range_key}"),
            "searchEngines": ranked(["Google", "Bing", "DuckDuckGo"],
                                    int(visits * 0.35), f"refse{site_id}:{range_key}"),
            "socials": ranked(["Instagram", "Facebook", "TikTok"],
                              int(visits * 0.12), f"refsoc{site_id}:{range_key}"),
        },
        "devices": ranked(["Smartphone", "Desktop", "Tablet"], visits, f"dev{site_id}:{range_key}"),
        "browsers": ranked(["Chrome", "Safari", "Firefox", "Edge"], visits, f"br{site_id}:{range_key}"),
        "osFamilies": ranked(["iOS", "macOS", "Windows", "Android"], visits, f"os{site_id}:{range_key}"),
        "countries": ranked(["United States", "Canada", "United Kingdom"], visits,
                            f"cty{site_id}:{range_key}"),
    }


now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
snap_created = snap_refreshed = 0
for site_id in sorted(SITE_PAGES):
    for range_key, days in RANGES.items():
        payload = build_payload(site_id, range_key, days)
        flt = (f"filter[matomo_site_id][_eq]={site_id}"
               f"&filter[range_key][_eq]={range_key}&fields=id&limit=1")
        st, data = req(f"/items/analytics_snapshots?{flt}")
        die_on(st, data, "search snapshot")
        body = {
            "matomo_site_id": site_id, "organization": site_id,
            "range_key": range_key, "collected_at": now_iso,
            "payload": payload, "is_test_data": False,
        }
        if data["data"]:
            # Refresh collected_at + payload so the 26h freshness gate passes.
            st, d2 = req(f"/items/analytics_snapshots/{data['data'][0]['id']}", "PATCH", body)
            die_on(st, d2, "refresh snapshot")
            snap_refreshed += 1
        else:
            st, d2 = req("/items/analytics_snapshots", "POST", body)
            die_on(st, d2, "create snapshot")
            snap_created += 1
print(f"analytics_snapshots: created {snap_created} / refreshed {snap_refreshed}")

# =====================================================================
# B. Completed org-2 projects with due dates inside the past 90 days
# =====================================================================
print("== B. org-2 completed projects (timeline chart) ==")
COMPLETED_PROJECTS = [
    ("Cedar & Co - Spring Menu Launch",
     "Seasonal menu microsite and launch campaign for the spring roast lineup.",
     "marketing", "2026-02-16T00:00:00Z", "2026-05-15T00:00:00Z"),
    ("Cedar & Co - Loyalty Card Microsite",
     "Digital punch card signup page wired into the POS loyalty program.",
     "code", "2026-03-09T00:00:00Z", "2026-04-30T00:00:00Z"),
]
cp_created = cp_skipped = 0
for name, desc, ptype, start, due in COMPLETED_PROJECTS:
    _, was_created = upsert("os_projects", {"name": name}, {
        "name": name, "description": desc, "organization": ORG_CEDAR,
        "status": "completed", "project_type": ptype, "kind": "deliverable",
        "start_date": start, "due_date": due, "archived": False,
        "is_test_data": False})
    if was_created:
        cp_created += 1
    else:
        cp_skipped += 1
print(f"os_projects (completed, org2): created {cp_created} / skipped {cp_skipped}")

# =====================================================================
# C. Recent org-2 activity_log events (feed head)
# =====================================================================
print("== C. org-2 recent activity ==")

# Resolve actors + client-visible org-2 tasks by name.
st, users = req("/users?filter[email][_icontains]=team.musterr.dev&fields=id,email&limit=-1")
die_on(st, users, "list team users")
team = [u["id"] for u in users["data"]]
if not team:
    raise SystemExit("FATAL: no team users found for actor field")

def task_by_name(name):
    st, data = req("/items/os_tasks?filter[name][_eq]=" + urllib.parse.quote(name) +
                   "&fields=id,project,is_visible_to_client&limit=1")
    die_on(st, data, f"find task {name}")
    return data["data"][0] if data["data"] else None

EVENTS = [
    # (verb, target_collection, task name or None, project, ts, metadata name)
    ("created", "os_tasks", "Review the pricing page", None,
     "2026-07-15T16:05:00Z", None),
    ("completed", "os_tasks", "Redesign the menu detail template", None,
     "2026-07-15T18:10:00Z", None),
    ("status_changed", "os_tasks", "Build order tracking page", None,
     "2026-07-16T09:40:00Z", None),
    ("update_posted", "os_projects", None, PROJ_CEDAR_WHOLESALE,
     "2026-07-16T10:15:00Z", "Status update for Cedar & Co - Wholesale Portal"),
    ("completed", "os_tasks", "Build the locations map page", None,
     "2026-07-16T13:20:00Z", None),
    ("update_posted", "os_projects", None, PROJ_CEDAR_WEB,
     "2026-07-16T15:05:00Z", "Status update for Cedar & Co - Website Redesign"),
]
ev_created = ev_skipped = 0
for i, (verb, coll, task_name, project, ts, meta_name) in enumerate(EVENTS):
    if task_name:
        task = task_by_name(task_name)
        if not task or task.get("is_visible_to_client") is False:
            print(f"  skip event for {task_name}: missing or not client-visible")
            continue
        target_id = task["id"]
        project = task["project"]
        meta_name = task_name
    else:
        target_id = project
    _, was_created = upsert("os_activity_log",
                            {"verb": verb, "target_id": target_id, "timestamp": ts}, {
        "verb": verb, "target_collection": coll, "target_id": target_id,
        "project": project, "timestamp": ts,
        "actor": team[i % len(team)],
        "metadata": {"name": meta_name}})
    if was_created:
        ev_created += 1
    else:
        ev_skipped += 1
print(f"os_activity_log (org2 recent): created {ev_created} / skipped {ev_skipped}")

# =====================================================================
# VERIFY
# =====================================================================
print("== verify ==")
ok = True

st, data = req("/items/analytics_snapshots?aggregate[count]=*")
n_snaps = int(data["data"][0]["count"]) if st == 200 else 0
print(f"  analytics_snapshots rows: {n_snaps}")
ok = ok and n_snaps >= 21

st, data = req("/items/analytics_snapshots?filter[matomo_site_id][_eq]=2"
               "&filter[range_key][_eq]=last30&fields=collected_at,payload&limit=1")
row = (data or {}).get("data", [{}])[0] if st == 200 else {}
payload = row.get("payload")
if isinstance(payload, str):
    payload = json.loads(payload)
t30 = (payload or {}).get("totals", {})
print(f"  site2 last30 snapshot: collected_at={row.get('collected_at')} visits={t30.get('visits')}"
      f" trend_days={len((payload or {}).get('trend', []))}")
ok = ok and bool(t30.get("visits")) and len((payload or {}).get("trend", [])) == 30

st, data = req("/items/os_projects?filter[organization][_eq]=2&fields=id,name,status,due_date&limit=-1")
projs = data["data"] if st == 200 else []
in_window = [p for p in projs if p.get("due_date") and
             "2026-04-18" <= p["due_date"][:10] <= "2026-07-16"]
print(f"  org2 projects: {len(projs)} total, {len(in_window)} with due_date in past-90d window")
ok = ok and len(in_window) >= 2

# Feed head simulation: the client feed fetches the 12 most recent global
# events, then keeps org-2 rows (dashboard component asks limit=8).
st, data = req("/items/os_activity_log?sort=-timestamp&limit=8"
               "&fields=id,verb,project.organization,metadata")
rows = data["data"] if st == 200 else []
org2_head = sum(1 for r in rows
                if ((r.get("project") or {}).get("organization")) == 2)
print(f"  global 8 newest activity rows: {len(rows)}, org2 among them: {org2_head}")
ok = ok and org2_head >= 4

print(f"VERIFY RESULT: {'PASS' if ok else 'FAIL'}")
raise SystemExit(0 if ok else 1)
