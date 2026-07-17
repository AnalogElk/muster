#!/usr/bin/env python3
"""Run 2 / P2: create + seed os_ai_commits, os_web_vitals, os_interactions.

Creates the three telemetry/ledger collections the frozen portal reads
(lib/token-usage/queries.ts, lib/portal/analytics/vitals-storage.ts,
lib/portal/analytics/interactions-storage.ts), grants the demo policy
read-only access (additive permission rows only), and seeds:

  - os_ai_commits: ~52 AI commit ledger rows over 60 days across live repos
  - os_web_vitals: ~30 days of RUM Core Web Vitals rows across portal routes
  - os_interactions: ~30 days of click/scroll heatmap beacon rows

Type decisions (deviation from blocked-sections.json, deliberate):
  token counts -> integer (not bigInteger) and est_cost_usd/value -> float
  (not decimal), because Directus returns bigInteger/decimal as JSON STRINGS
  and the portal aggregators require numbers (vitals-storage.ts:190 skips
  rows where typeof value !== 'number'; interactions-storage.ts isValidPct
  requires typeof number; ai-ledger fmtUsd/fmtInt expect numbers).

Idempotent: collections/fields/permissions checked before create; rows are
upserted by natural key (os_ai_commits.commit_sha, os_web_vitals.metric_id
'sr2v-<n>', os_interactions.app_version '1.4.2+sr2i-<n>'). Deterministic
RNG seed, so re-runs create 0 rows. All content fictional, no em dashes,
obviously fake data only. Never prints the admin token.
"""
import hashlib
import json
import math
import os
import random
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://cms.musterr.dev"
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"


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


def req(path, method="GET", body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
    }
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def die_on(st, data, what):
    if st not in (200, 204):
        raise SystemExit(f"FATAL: {what} -> HTTP {st}: {json.dumps(data)[:400]}")


# ---------------------------------------------------------------------------
# 1. Collections (additive; skip when they already exist)
# ---------------------------------------------------------------------------

def fld(field, ftype, note=None, special=None, hidden=False, readonly=False):
    meta = {"interface": "input"}
    if note:
        meta["note"] = note
    if special:
        meta["special"] = special
    if hidden:
        meta["hidden"] = True
    if readonly:
        meta["readonly"] = True
    if ftype == "timestamp":
        meta["interface"] = "datetime"
    if ftype == "json":
        meta["interface"] = "input-code"
    return {"field": field, "type": ftype, "meta": meta, "schema": {}}


def pk_uuid():
    return {
        "field": "id",
        "type": "uuid",
        "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
        "schema": {"is_primary_key": True, "length": 36, "has_auto_increment": False},
    }


def ensure_collection(name, icon, note, fields):
    st, _ = req(f"/collections/{name}")
    if st == 200:
        print(f"collection {name}: exists, skipped")
        return False
    st, data = req("/collections", "POST", {
        "collection": name,
        "meta": {"icon": icon, "note": note, "hidden": False},
        "schema": {},
        "fields": fields,
    })
    die_on(st, data, f"create collection {name}")
    print(f"collection {name}: CREATED")
    return True


ensure_collection(
    "os_ai_commits", "receipt_long",
    "Per-commit AI token attribution ledger (portal analytics AI Ledger tab)",
    [
        pk_uuid(),
        fld("commit_sha", "string", "40-char sha, natural key"),
        fld("repo_slug", "string", "matches repositories.name"),
        fld("project_label", "string"),
        fld("committed_at", "timestamp"),
        fld("subject", "string", "conventional commit subject"),
        fld("commit_type", "string", "feat|fix|chore|docs|refactor|perf|test"),
        fld("loc_added", "integer"),
        fld("loc_removed", "integer"),
        fld("loc_net_code", "integer"),
        fld("files_changed", "integer"),
        fld("input_tokens", "integer", "integer not bigInteger: JSON must be number for the portal"),
        fld("output_tokens", "integer"),
        fld("cache_write_tokens", "integer"),
        fld("cache_read_tokens", "integer"),
        fld("total_tokens", "integer"),
        fld("est_cost_usd", "float", "float not decimal: Directus returns decimal as string"),
        fld("models", "json", "[{model, tokens, cost}]"),
        fld("token_attribution", "string"),
        fld("outcome", "string", "shipped|reverted"),
        fld("host", "string"),
        fld("last_synced", "timestamp"),
    ],
)

ensure_collection(
    "os_web_vitals", "speed",
    "Real-user Core Web Vitals beacons (portal analytics Web Vitals surface)",
    [
        pk_uuid(),
        fld("metric", "string", "LCP|INP|CLS|FCP|TTFB"),
        fld("value", "float", "float: aggregator requires typeof number"),
        fld("rating", "string", "good|needs-improvement|poor"),
        fld("route", "string"),
        fld("portal", "string", "employee|client"),
        fld("nav_type", "string"),
        fld("user_id", "string"),
        fld("org_id", "string"),
        fld("device", "string"),
        fld("connection", "string"),
        fld("app_version", "string"),
        fld("metric_id", "string", "beacon metric id; seed rows use sr2v-<n>"),
        fld("date_created", "timestamp", None, special=["date-created"], hidden=True, readonly=True),
    ],
)

ensure_collection(
    "os_interactions", "touch_app",
    "Click + scroll-depth beacons (portal analytics Interaction Heatmap)",
    [
        pk_uuid(),
        fld("event_type", "string", "click|scroll"),
        fld("route", "string"),
        fld("portal", "string", "employee|client"),
        fld("x_pct", "float", "click X as % of viewport width; null for scroll"),
        fld("y_pct", "float", "click Y as % of document height; null for scroll"),
        fld("scroll_pct", "float", "max scroll depth %; null for clicks"),
        fld("viewport_w", "integer"),
        fld("viewport_h", "integer"),
        fld("user_id", "string"),
        fld("org_id", "string"),
        fld("device", "string"),
        fld("app_version", "string", "seed rows carry 1.4.2+sr2i-<n> as idempotency key"),
        fld("date_created", "timestamp", None, special=["date-created"], hidden=True, readonly=True),
    ],
)

# ---------------------------------------------------------------------------
# 2. Demo policy read grants (additive only; never edit existing rows)
# ---------------------------------------------------------------------------

def ensure_read_permission(collection):
    st, data = req(
        f"/permissions?filter[policy][_eq]={DEMO_POLICY}"
        f"&filter[collection][_eq]={collection}&filter[action][_eq]=read&fields=id"
    )
    die_on(st, data, f"list permissions for {collection}")
    if data.get("data"):
        print(f"permission read {collection}: exists (id {data['data'][0]['id']}), skipped")
        return
    st, data = req("/permissions", "POST", {
        "policy": DEMO_POLICY,
        "collection": collection,
        "action": "read",
        "fields": ["*"],
        "permissions": {},
        "validation": {},
    })
    die_on(st, data, f"grant read on {collection}")
    print(f"permission read {collection}: GRANTED (id {data['data']['id']})")


for c in ("os_ai_commits", "os_web_vitals", "os_interactions"):
    ensure_read_permission(c)

# ---------------------------------------------------------------------------
# 3. Data generation (deterministic)
# ---------------------------------------------------------------------------

rng = random.Random(20260716)
NOW = datetime.now(timezone.utc)
ANCHOR = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- os_ai_commits ---------------------------------------------------------
# repo_slug values match live repositories rows; labels follow the existing
# os_token_usage project_label style (no em dashes).
REPOS = [
    ("muster",                "Muster Platform",             10),
    ("harbor-app",            "Harbor Class Booking App",     8),
    ("cedar-web",             "Cedar & Co Website",           7),
    ("sterling-reservations", "Sterling & Vine Reservations", 6),
    ("cedar-wholesale",       "Cedar & Co Wholesale Portal",  5),
    ("meridian-grant-portal", "Meridian Grant Portal",        5),
    ("vellum-portfolio",      "Vellum Portfolio Platform",    4),
    ("northlight-brand",      "Northlight Brand Identity",    3),
    ("northlight-seo",        "Northlight SEO Retainer",      2),
]
SUBJECTS = {
    "feat": [
        "add saved-view filters to the task board",
        "wire recurring invoice generation into billing",
        "add class waitlist notifications",
        "implement wholesale tier pricing rules",
        "add grant application status timeline",
        "add reservation deposit capture flow",
        "add portfolio case-study gallery blocks",
        "add sitemap-driven content audit report",
        "add brand asset download bundles",
        "add org-scoped analytics range picker",
        "add CSV export for the payments ledger",
        "add sprint burndown snapshot endpoint",
    ],
    "fix": [
        "correct timezone drift on due-date badges",
        "handle empty states on the deals board",
        "fix double-submit on the checkout form",
        "fix pagination cursor on activity feed",
        "guard null org on contact detail page",
        "fix overlapping labels on revenue chart",
        "fix stale cache on dashboard KPI cards",
        "repair webhook retry backoff jitter",
        "fix mobile nav focus trap",
    ],
    "chore": [
        "bump dependencies and prune lockfile",
        "rotate demo fixtures and reseed data",
        "tighten eslint config and fix warnings",
        "update CI cache keys for pnpm 9",
        "normalize env var names across services",
    ],
    "refactor": [
        "extract invoice totals into shared lib",
        "split analytics loaders per section",
        "consolidate GraphQL fragments",
        "move beacon enrichment into middleware",
    ],
    "docs": [
        "document the release checklist",
        "add runbook for failed webhook replays",
        "update onboarding guide screenshots",
    ],
    "perf": [
        "memoize task board column derivation",
        "batch Directus reads on dashboard",
        "lazy-load heatmap grid rendering",
    ],
    "test": [
        "add coverage for proration edge cases",
        "add e2e for client portal login flow",
        "add unit tests for vitals p75 math",
    ],
}
TYPE_WEIGHTS = [("feat", 35), ("fix", 25), ("chore", 12), ("refactor", 10),
                ("docs", 6), ("perf", 6), ("test", 6)]
MODELS_SONNET = "claude-sonnet-4"
MODELS_OPUS = "claude-opus-4"
HOSTS = ["studio-mbp.local", "studio-mbp.local", "devbox-usw2", "studio-mini.local"]


def pick_weighted(pairs):
    total = sum(w for _, w in pairs)
    x = rng.uniform(0, total)
    acc = 0
    for v, w in pairs:
        acc += w
        if x <= acc:
            return v
    return pairs[-1][0]


ai_rows = []
N_COMMITS = 52
for i in range(N_COMMITS):
    slug, label = pick_weighted([((r[0], r[1]), r[2]) for r in REPOS])
    ctype = pick_weighted(TYPE_WEIGHTS)
    subject = f"{ctype}: {rng.choice(SUBJECTS[ctype])}"
    # organic recency-biased date spread over 60 days, avoid Sundays mostly
    day_off = int(60 * (rng.random() ** 1.35))
    d = ANCHOR - timedelta(days=day_off)
    if d.weekday() == 6 and rng.random() < 0.8:
        d -= timedelta(days=1)
    committed = d + timedelta(hours=rng.randint(9, 19), minutes=rng.randint(0, 59),
                              seconds=rng.randint(0, 59))
    # cost-first lognormal, then derive a consistent token mix
    cost = min(320.0, max(1.5, math.exp(rng.gauss(math.log(25), 1.0))))
    total_tokens = int(cost * 640000 * rng.uniform(0.8, 1.2))
    cr = int(total_tokens * rng.uniform(0.62, 0.78))
    cw = int(total_tokens * rng.uniform(0.08, 0.15))
    inp = int(total_tokens * rng.uniform(0.08, 0.16))
    out = max(1000, total_tokens - cr - cw - inp)
    cost = round(cost, 2)
    if rng.random() < 0.22:
        opus_share = rng.uniform(0.2, 0.4)
        opus_tokens = int(total_tokens * opus_share)
        opus_cost = round(cost * min(0.75, opus_share * 2.1), 2)
        models = [
            {"model": MODELS_SONNET, "tokens": total_tokens - opus_tokens,
             "cost": round(cost - opus_cost, 2)},
            {"model": MODELS_OPUS, "tokens": opus_tokens, "cost": opus_cost},
        ]
    else:
        models = [{"model": MODELS_SONNET, "tokens": total_tokens, "cost": cost}]
    loc_added = max(2, int(math.exp(rng.gauss(math.log(120), 1.1))))
    loc_removed = int(loc_added * rng.uniform(0.1, 0.6))
    sha = hashlib.sha1(f"muster-demo-ai-commit-{i}".encode()).hexdigest()
    ai_rows.append({
        "commit_sha": sha,
        "repo_slug": slug,
        "project_label": label,
        "committed_at": iso(committed),
        "subject": subject,
        "commit_type": ctype,
        "loc_added": loc_added,
        "loc_removed": loc_removed,
        "loc_net_code": loc_added - loc_removed,
        "files_changed": max(1, int(loc_added / rng.uniform(40, 120)) + rng.randint(0, 3)),
        "input_tokens": inp,
        "output_tokens": out,
        "cache_write_tokens": cw,
        "cache_read_tokens": cr,
        "total_tokens": total_tokens,
        "est_cost_usd": cost,
        "models": models,
        "token_attribution": "time-window",
        "outcome": "reverted" if rng.random() < 0.055 else "shipped",
        "host": rng.choice(HOSTS),
        "last_synced": iso(NOW.replace(microsecond=0)),
    })

# --- os_web_vitals ---------------------------------------------------------
EMP = "employee"
CLI = "client"
ROUTES = [
    # (route, portal, weight, lcp_base_ms, ttfb_base_ms)
    ("/employee-portal/dashboard",     EMP, 20, 2350, 520),
    ("/employee-portal/tasks",         EMP, 16, 1900, 380),
    ("/employee-portal/projects",      EMP, 10, 1750, 360),
    ("/employee-portal/invoices",      EMP, 8,  1800, 400),
    ("/employee-portal/analytics",     EMP, 9,  2950, 640),
    ("/employee-portal/organizations", EMP, 6,  1650, 340),
    ("/employee-portal/messages",      EMP, 5,  1600, 330),
    ("/employee-portal/contacts",      EMP, 5,  1700, 350),
    ("/client-portal/dashboard",       CLI, 9,  2100, 460),
    ("/client-portal/projects",        CLI, 5,  1800, 380),
    ("/client-portal/invoices",        CLI, 4,  1850, 400),
    ("/client-portal/support",         CLI, 3,  1700, 360),
]
TEAM_USERS = [
    "257a4b75-deff-476d-953d-1898c57f6684",  # demo@muster.dev
    "3f3b7c79-4c79-4865-8592-5a303db8b995",
    "86f5c9cd-b6fb-4d43-bb5c-2050e66c7f40",
    "a043509e-00b1-4d4c-b613-fd0d30b878db",
    "78cf2976-e1da-4b8b-b238-822bcbe1b8fb",
    "1e7ce5df-3dea-4fd4-bd35-cfd9c32f8852",
    "06fb5978-93dd-4a13-b02e-48f7271d7301",
]
CLIENT_USER = "91fb50ea-5ead-4713-9c48-a32bb945932f"  # client@muster.dev
CLIENT_ORGS = ["2", "5", "6", "7"]

RATE = {
    "LCP": (2500, 4000), "INP": (200, 500), "CLS": (0.1, 0.25),
    "FCP": (1800, 3000), "TTFB": (800, 1800),
}


def rate(metric, value):
    good, poor = RATE[metric]
    if value <= good:
        return "good"
    if value <= poor:
        return "needs-improvement"
    return "poor"


vitals_rows = []
seq_v = 0
for day in range(30):
    d = ANCHOR - timedelta(days=day)
    is_weekend = d.weekday() >= 5
    n_views = rng.randint(3, 6) if is_weekend else rng.randint(9, 14)
    for _ in range(n_views):
        rt = pick_weighted([(r, r[2]) for r in ROUTES])
        route, portal, lcp_base, ttfb_base = rt[0], rt[1], rt[3], rt[4]
        device = pick_weighted([("desktop", 70), ("mobile", 25), ("tablet", 5)])
        conn = pick_weighted([("wifi", 60), ("4g", 35), ("3g", 5)])
        mult = (1.35 if device == "mobile" else 1.0) * (1.25 if conn == "4g" else 1.7 if conn == "3g" else 1.0)
        nav = pick_weighted([("navigate", 80), ("reload", 12), ("back-forward", 8)])
        if portal == CLI:
            user_id, org_id = CLIENT_USER, rng.choice(CLIENT_ORGS)
        else:
            user_id, org_id = rng.choice(TEAM_USERS), None
        ts = d + timedelta(hours=rng.randint(8, 21), minutes=rng.randint(0, 59),
                           seconds=rng.randint(0, 59))
        ttfb = max(80.0, rng.gauss(ttfb_base * mult, 130))
        fcp = ttfb + max(200.0, rng.gauss(650 * mult, 220))
        lcp = max(fcp + 100, lcp_base * mult * math.exp(rng.gauss(0, 0.28)))
        cls = round(min(0.55, abs(rng.gauss(0.045, 0.05)) + (0.22 if rng.random() < 0.04 else 0)), 3)
        metrics = [("TTFB", round(ttfb, 1)), ("FCP", round(fcp, 1)),
                   ("LCP", round(lcp, 1)), ("CLS", cls)]
        if rng.random() < 0.6:
            inp = max(40.0, math.exp(rng.gauss(math.log(140), 0.55)))
            metrics.append(("INP", round(inp, 1)))
        for metric, value in metrics:
            seq_v += 1
            vitals_rows.append({
                "metric": metric,
                "value": value,
                "rating": rate(metric, value),
                "route": route,
                "portal": portal,
                "nav_type": nav,
                "user_id": user_id,
                "org_id": org_id,
                "device": device,
                "connection": conn,
                "app_version": "1.4.2",
                "metric_id": f"sr2v-{seq_v}",
                "date_created": iso(ts),
            })

# --- os_interactions -------------------------------------------------------
# click hotspot cluster centers (x_pct, y_pct, spread) per route
CLUSTERS = {
    "default": [(6, 30, 4), (92, 4, 2.5), (35, 25, 9), (55, 55, 12)],
    "/employee-portal/dashboard": [(6, 28, 4), (92, 4, 2.5), (28, 22, 7), (68, 38, 9), (48, 72, 10)],
    "/employee-portal/tasks": [(6, 32, 4), (93, 5, 2), (25, 40, 8), (50, 45, 10), (75, 40, 8)],
    "/employee-portal/analytics": [(6, 30, 4), (90, 6, 3), (50, 30, 12), (50, 65, 12)],
}
inter_rows = []
seq_i = 0
for day in range(30):
    d = ANCHOR - timedelta(days=day)
    is_weekend = d.weekday() >= 5
    n_events = rng.randint(8, 18) if is_weekend else rng.randint(38, 58)
    for _ in range(n_events):
        rt = pick_weighted([(r, r[2]) for r in ROUTES])
        route, portal = rt[0], rt[1]
        device = pick_weighted([("desktop", 75), ("mobile", 20), ("tablet", 5)])
        vw, vh = (390, 844) if device == "mobile" else rng.choice([(1440, 900), (1728, 1080), (1512, 982)])
        if portal == CLI:
            user_id, org_id = CLIENT_USER, rng.choice(CLIENT_ORGS)
        else:
            user_id, org_id = rng.choice(TEAM_USERS), None
        ts = d + timedelta(hours=rng.randint(8, 21), minutes=rng.randint(0, 59),
                           seconds=rng.randint(0, 59))
        seq_i += 1
        common = {
            "route": route,
            "portal": portal,
            "viewport_w": vw,
            "viewport_h": vh,
            "user_id": user_id,
            "org_id": org_id,
            "device": device,
            "app_version": f"1.4.2+sr2i-{seq_i}",
            "date_created": iso(ts),
        }
        if rng.random() < 0.62:
            cx, cy, spread = rng.choice(CLUSTERS.get(route, CLUSTERS["default"]))
            x = min(99.5, max(0.5, rng.gauss(cx, spread)))
            y = min(99.5, max(0.5, rng.gauss(cy, spread * 1.4)))
            inter_rows.append({"event_type": "click", "x_pct": round(x, 2),
                               "y_pct": round(y, 2), "scroll_pct": None, **common})
        else:
            depth = min(100.0, max(3.0, abs(rng.gauss(55, 28))))
            inter_rows.append({"event_type": "scroll", "x_pct": None, "y_pct": None,
                               "scroll_pct": round(depth, 1), **common})

# ---------------------------------------------------------------------------
# 4. Idempotent seeding (batch upsert by natural key)
# ---------------------------------------------------------------------------

def existing_keys(collection, key_field):
    keys = set()
    page = 1
    while True:
        st, data = req(f"/items/{collection}?fields={key_field}&limit=500&page={page}")
        die_on(st, data, f"list {collection} keys")
        rows = data.get("data", [])
        for r in rows:
            if r.get(key_field):
                keys.add(r[key_field])
        if len(rows) < 500:
            return keys
        page += 1


def batch_create(collection, rows):
    created = 0
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        st, data = req(f"/items/{collection}", "POST", chunk)
        die_on(st, data, f"batch create {collection}")
        created += len(data.get("data", []))
    return created


def seed(collection, rows, key_field):
    have = existing_keys(collection, key_field)
    missing = [r for r in rows if r[key_field] not in have]
    skipped = len(rows) - len(missing)
    created = batch_create(collection, missing) if missing else 0
    print(f"{collection}: created {created} / updated 0 / skipped {skipped}")
    return created


seed("os_ai_commits", ai_rows, "commit_sha")
seed("os_web_vitals", vitals_rows, "metric_id")
seed("os_interactions", inter_rows, "app_version")

# date_created backfill (SEED-PLAN 14b): the date-created special OVERRIDES
# the POST payload and stamps run-time (proven run 1, seed-D4), so every
# seeded row gets its deterministic historical timestamp via PATCH. The
# update path does NOT re-stamp date_created (unlike date_updated). Rows not
# in the seed key map (real live beacons) are never touched. Idempotent:
# rows already matching their intended date are skipped.
def fix_dates(collection, rows, key_field):
    want_by_key = {r[key_field]: r["date_created"] for r in rows}
    page = 1
    patched = 0
    matched = 0
    while True:
        st, data = req(f"/items/{collection}?fields=id,{key_field},date_created&limit=500&page={page}")
        die_on(st, data, f"page {collection}")
        got_rows = data.get("data", [])
        for r in got_rows:
            k = r.get(key_field)
            if k not in want_by_key:
                continue  # live beacon row or foreign row: never touch
            matched += 1
            if (r.get("date_created") or "")[:10] != want_by_key[k][:10]:
                st2, d2 = req(f"/items/{collection}/{r['id']}", "PATCH",
                              {"date_created": want_by_key[k]})
                die_on(st2, d2, f"patch date {collection}/{r['id']}")
                patched += 1
        if len(got_rows) < 500:
            break
        page += 1
    print(f"{collection}: date_created backfill: matched {matched} seeded rows, patched {patched}")


fix_dates("os_web_vitals", vitals_rows, "metric_id")
fix_dates("os_interactions", inter_rows, "app_version")

# ---------------------------------------------------------------------------
# 5. Probes: REST reader shapes + GraphQL fragment shapes
# ---------------------------------------------------------------------------

print("== REST probes (exact portal reader shapes) ==")
st, data = req("/items/os_ai_commits?sort=-committed_at&limit=500")
n = len(data.get("data", []))
sample = data["data"][0] if n else {}
print(f"  os_ai_commits reader: HTTP {st} rows={n} "
      f"est_cost_usd type={type(sample.get('est_cost_usd')).__name__} "
      f"input_tokens type={type(sample.get('input_tokens')).__name__}")

since7 = (NOW - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
qs = (f"filter[date_created][_gte]={since7}&sort[]=-date_created&limit=10000"
      "&fields[]=metric&fields[]=value&fields[]=rating&fields[]=route"
      "&fields[]=portal&fields[]=device&fields[]=date_created")
st, data = req(f"/items/os_web_vitals?{qs}")
n = len(data.get("data", []))
sample = data["data"][0] if n else {}
print(f"  os_web_vitals reader (7d): HTTP {st} rows={n} "
      f"value type={type(sample.get('value')).__name__}")

qs = (f"filter[date_created][_gte]={since7}&sort[]=-date_created&limit=20000"
      "&fields[]=event_type&fields[]=route&fields[]=portal&fields[]=x_pct"
      "&fields[]=y_pct&fields[]=scroll_pct&fields[]=date_created")
st, data = req(f"/items/os_interactions?{qs}")
n = len(data.get("data", []))
sample = data["data"][0] if n else {}
xt = type(sample.get("x_pct")).__name__ if sample else "?"
print(f"  os_interactions reader (7d): HTTP {st} rows={n} x_pct type={xt}")

print("== GraphQL probes (portal fragment shapes) ==")
GQL = """
query {
  os_ai_commits(limit: 3, sort: ["-committed_at"]) {
    id commit_sha repo_slug project_label committed_at subject commit_type
    loc_added loc_removed loc_net_code files_changed input_tokens output_tokens
    cache_write_tokens cache_read_tokens total_tokens est_cost_usd models
    token_attribution outcome host last_synced
  }
  os_web_vitals(limit: 3, sort: ["-date_created"]) {
    metric value rating route portal device date_created
  }
  os_interactions(limit: 3, sort: ["-date_created"]) {
    event_type route portal x_pct y_pct scroll_pct date_created
  }
}
"""
st, data = req("/graphql", "POST", {"query": GQL})
errs = data.get("errors")
if errs:
    print(f"  GraphQL: HTTP {st} ERRORS: {json.dumps(errs)[:400]}")
else:
    d = data.get("data", {})
    for k in ("os_ai_commits", "os_web_vitals", "os_interactions"):
        print(f"  {k}: {len(d.get(k, []))} rows, first={json.dumps(d.get(k, [{}])[0])[:180]}")

# demo-policy read check via user-scoped GraphQL is covered by the portal
# end-to-end probe in the runner (demo session hits the API routes).
print("== summary totals ==")
for c in ("os_ai_commits", "os_web_vitals", "os_interactions"):
    st, data = req(f"/items/{c}?aggregate[count]=id")
    cnt = data.get("data", [{}])[0].get("count", {})
    print(f"  {c}: total {cnt if not isinstance(cnt, dict) else cnt.get('id')}")
st, data = req("/items/os_ai_commits?aggregate[min]=committed_at&aggregate[max]=committed_at")
agg = data.get("data", [{}])[0]
print(f"  os_ai_commits committed_at: min {agg.get('min', {}).get('committed_at')} "
      f"max {agg.get('max', {}).get('committed_at')}")
for c in ("os_web_vitals", "os_interactions"):
    st, data = req(f"/items/{c}?aggregate[min]=date_created&aggregate[max]=date_created")
    agg = data.get("data", [{}])[0]
    print(f"  {c} date_created: min {agg.get('min', {}).get('date_created')} "
          f"max {agg.get('max', {}).get('date_created')}")
print("done")
