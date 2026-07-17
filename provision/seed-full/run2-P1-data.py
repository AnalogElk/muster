#!/usr/bin/env python3
"""run2-P1-data: run 2 authorized data patches + nullfill backlog + polish (Muster demo).

Authorized by the RUN 2 ADDENDUM (Mike, 2026-07-16, FULL AUTO):
  1. repositories aba3e9b9 (bloom-shopify) project_id -> 3d5677cf (flagged data bug).
  2. Null-fill descriptions on the 5 legacy synthetic repos (seed-D3 gated backlog;
     bloom-shopify gets NEUTRAL text only). Only-when-null.
  3. Null-fill budget_cap on 5 synthetic projects, 25000-80000 (seed-D3 gated backlog).
     Only-when-null.
  4. Polish: 6 new os_proposals covering orgs 3, 4, 5 (Northlight, Vellum, Harbor)
     with mixed statuses + os_proposal_contacts junctions; 1 voided os_expense.
  5. infra_snapshots (this run family's own rows): set payload.stripe.mrrUsd and
     activeSubscriptionCount to match the live CMS revenue KPI (computed with the
     same monthly normalization as portal-src lib/portal/analytics/revenue.ts).
  6. os_settings singleton: next_invoice_number = live max invoice suffix + 1,
     next_proposal_number = live proposal count + 1. Only-when-null.

Rules: add-only outside the authorized patches above, idempotent upserts by natural
key, is_test_data:false on content rows, no em dashes, obviously fake refs only,
token never printed. Safe to re-run (second run reports all skips).

Usage: python3 run2-P1-data.py
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cms.musterr.dev"


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


def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def get(col, params):
    q = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
    )
    st, out = req("GET", "/items/%s?%s" % (col, q))
    if st != 200:
        raise RuntimeError("GET %s failed: %s %s" % (col, st, out))
    return out.get("data", [])


counts = {}


def bump(col, key):
    counts.setdefault(col, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
    counts[col][key] += 1


# ---------------------------------------------------------------- 1. bloom repo pointer
BLOOM_REPO = "aba3e9b9-6d24-4c01-a35b-27a475fb22c9"
BLOOM_PROJECT = "3d5677cf-a15c-4b0c-89c5-f34a3b3d31e6"
rows = get("repositories", {"fields": "id,name,project_id", "filter": {"name": {"_eq": "bloom-shopify"}}, "limit": 1})
if not rows:
    print("repositories(bloom pointer): FAILED, bloom-shopify not found")
    bump("repositories(bloom pointer)", "failed")
else:
    row = rows[0]
    BLOOM_REPO = row["id"]
    # resolve the Bloom project id live rather than trusting a hardcoded uuid
    projs = get("os_projects", {"fields": "id,name,organization", "filter": {"name": {"_contains": "Shopify Build"}}, "limit": 1})
    if projs:
        BLOOM_PROJECT = projs[0]["id"]
    if row.get("project_id") == BLOOM_PROJECT:
        bump("repositories(bloom pointer)", "skipped")
    else:
        st, out = req("PATCH", "/items/repositories/%s" % BLOOM_REPO, {"project_id": BLOOM_PROJECT})
        bump("repositories(bloom pointer)", "updated" if st == 200 else "failed")
        if st != 200:
            print("PATCH bloom pointer failed:", st, out)

# ---------------------------------------------------------------- 2. repo descriptions (null-fill)
REPO_DESCRIPTIONS = {
    "harbor-app": "React Native class booking and member app for Harbor Fitness.",
    "cedar-web": "Marketing site and menu pages for Cedar and Co Coffee. Next.js, deployed on Netlify.",
    "sterling-reservations": "Reservations and private dining request platform for Sterling and Vine.",
    "northlight-brand": "Brand identity assets and guideline templates for Northlight Law.",
    "bloom-shopify": "Legacy storefront build repository; history retained for reference.",
}
for name, desc in REPO_DESCRIPTIONS.items():
    rows = get("repositories", {"fields": "id,description", "filter": {"name": {"_eq": name}}, "limit": 1})
    if not rows:
        bump("repositories(description null-fill)", "failed")
        print("repo not found:", name)
        continue
    if rows[0].get("description"):
        bump("repositories(description null-fill)", "skipped")
        continue
    st, out = req("PATCH", "/items/repositories/%s" % rows[0]["id"], {"description": desc})
    bump("repositories(description null-fill)", "updated" if st == 200 else "failed")
    if st != 200:
        print("PATCH repo description failed:", name, st, out)

# ---------------------------------------------------------------- 3. budget_cap (null-fill)
BUDGET_CAPS = {
    "Harbor — Class Booking App": 64000,
    "Sterling & Vine — Reservations": 42000,
    "Northlight — Brand Identity": 28000,
    "Meridian — Grant Portal": 55000,
    "Vellum — Portfolio Platform": 36000,
}
for pname, cap in BUDGET_CAPS.items():
    rows = get("os_projects", {"fields": "id,budget_cap", "filter": {"name": {"_eq": pname}}, "limit": 1})
    if not rows:
        bump("os_projects(budget_cap null-fill)", "failed")
        print("project not found:", pname)
        continue
    if rows[0].get("budget_cap") is not None:
        bump("os_projects(budget_cap null-fill)", "skipped")
        continue
    st, out = req("PATCH", "/items/os_projects/%s" % rows[0]["id"], {"budget_cap": cap})
    bump("os_projects(budget_cap null-fill)", "updated" if st == 200 else "failed")
    if st != 200:
        print("PATCH budget_cap failed:", pname, st, out)

# ---------------------------------------------------------------- 4. proposals (orgs 3, 4, 5)
def deal_id(org, name_contains):
    rows = get("os_deals", {"fields": "id", "filter": {"organization": {"_eq": org}, "name": {"_contains": name_contains}}, "limit": 1})
    return rows[0]["id"] if rows else None


PROPOSALS = [
    {
        "name": "Northlight Law Client Intake Automation SOW",
        "organization": 3,
        "deal": deal_id(3, "Client Intake Automation"),
        "status": "submitted",
        "total": 42000.00,
        "expiration_date": "2026-08-14T00:00:00Z",
        "date_created": "2026-07-01T15:30:00Z",
        "proposal_notes": "Scoped with the Northlight operations team in late June. Covers the client intake automation pilot for the Portland office with a phased rollout.",
        "line_items": [
            {"description": "Discovery and process mapping", "quantity": 1, "unit_price": 6000, "amount": 6000},
            {"description": "Intake form and routing build", "quantity": 1, "unit_price": 28000, "amount": 28000},
            {"description": "Staff training and rollout", "quantity": 1, "unit_price": 8000, "amount": 8000},
        ],
        "contacts": [8, 14],
    },
    {
        "name": "Northlight Law Website Content Refresh Proposal",
        "organization": 3,
        "deal": None,
        "status": "draft",
        "total": 9500.00,
        "expiration_date": "2026-09-01T00:00:00Z",
        "date_created": "2026-07-10T18:05:00Z",
        "proposal_notes": "Draft pending partner review. Refreshes practice area copy ahead of the fall recruiting season.",
        "line_items": [
            {"description": "Content audit and gap analysis", "quantity": 1, "unit_price": 2500, "amount": 2500},
            {"description": "Practice area page rewrites", "quantity": 1, "unit_price": 5000, "amount": 5000},
            {"description": "Publishing and QA pass", "quantity": 1, "unit_price": 2000, "amount": 2000},
        ],
        "contacts": [15],
    },
    {
        "name": "Vellum Studio Portfolio Refresh Proposal",
        "organization": 4,
        "deal": deal_id(4, "Portfolio Refresh"),
        "status": "approved",
        "total": 12500.00,
        "expiration_date": "2026-05-30T00:00:00Z",
        "date_created": "2026-04-18T16:45:00Z",
        "proposal_notes": "Approved by Avery in early May. Work is tracked on the Vellum Portfolio Platform project.",
        "line_items": [
            {"description": "Portfolio IA and design refresh", "quantity": 1, "unit_price": 7500, "amount": 7500},
            {"description": "Case study template build", "quantity": 1, "unit_price": 3500, "amount": 3500},
            {"description": "Launch support", "quantity": 1, "unit_price": 1500, "amount": 1500},
        ],
        "contacts": [4, 16],
    },
    {
        "name": "Vellum Studio Motion Reel Production SOW",
        "organization": 4,
        "deal": None,
        "status": "voided",
        "total": 18000.00,
        "expiration_date": "2026-06-20T00:00:00Z",
        "date_created": "2026-05-22T14:20:00Z",
        "proposal_notes": "Voided in June; the studio postponed the motion reel budget to Q4. Revisit after the portfolio relaunch ships.",
        "line_items": [
            {"description": "Concept and storyboard", "quantity": 1, "unit_price": 4000, "amount": 4000},
            {"description": "Production and edit", "quantity": 1, "unit_price": 11000, "amount": 11000},
            {"description": "Sound design and color pass", "quantity": 1, "unit_price": 3000, "amount": 3000},
        ],
        "contacts": [17],
    },
    {
        "name": "Harbor Fitness Member App Phase 2 SOW",
        "organization": 5,
        "deal": deal_id(5, "Member App"),
        "status": "approved",
        "total": 64000.00,
        "expiration_date": "2026-04-30T00:00:00Z",
        "date_created": "2026-03-25T17:10:00Z",
        "proposal_notes": "Signed in April. Phase 2 covers wearables, waitlists, and member messaging on the Class Booking App project.",
        "line_items": [
            {"description": "Wearables integration", "quantity": 1, "unit_price": 22000, "amount": 22000},
            {"description": "Class booking waitlists", "quantity": 1, "unit_price": 18000, "amount": 18000},
            {"description": "Member messaging", "quantity": 1, "unit_price": 15000, "amount": 15000},
            {"description": "QA and release management", "quantity": 1, "unit_price": 9000, "amount": 9000},
        ],
        "contacts": [5, 18],
    },
    {
        "name": "Harbor Fitness Class Schedule Integration Proposal",
        "organization": 5,
        "deal": deal_id(5, "Class Schedule Integration"),
        "status": "submitted",
        "total": 9000.00,
        "expiration_date": "2026-07-10T00:00:00Z",
        "date_created": "2026-06-12T19:40:00Z",
        "proposal_notes": "Submitted mid June; validity lapsed on July 10 while the front desk team evaluated Mindbody licensing. Awaiting a re-issue decision.",
        "line_items": [
            {"description": "Mindbody schedule sync", "quantity": 1, "unit_price": 6000, "amount": 6000},
            {"description": "Front desk dashboard", "quantity": 1, "unit_price": 3000, "amount": 3000},
        ],
        "contacts": [19],
    },
]

for p in PROPOSALS:
    existing = get("os_proposals", {"fields": "id", "filter": {"name": {"_eq": p["name"]}}, "limit": 1})
    if existing:
        bump("os_proposals", "skipped")
        pid = existing[0]["id"]
    else:
        body = {
            "name": p["name"],
            "organization": p["organization"],
            "deal": p["deal"],
            "status": p["status"],
            "total": p["total"],
            "expiration_date": p["expiration_date"],
            "proposal_notes": p["proposal_notes"],
            "line_items": p["line_items"],
            "is_test_data": False,
        }
        st, out = req("POST", "/items/os_proposals", body)
        if st not in (200, 201, 204):
            bump("os_proposals", "failed")
            print("POST proposal failed:", p["name"], st, out)
            continue
        pid = out["data"]["id"]
        # backdate date_created (Directus ignores it on POST, honors it on PATCH)
        req("PATCH", "/items/os_proposals/%s" % pid, {"date_created": p["date_created"]})
        bump("os_proposals", "created")
    for cid in p["contacts"]:
        j = get("os_proposal_contacts", {"fields": "id", "filter": {"os_proposals_id": {"_eq": pid}, "contacts_id": {"_eq": cid}}, "limit": 1})
        if j:
            bump("os_proposal_contacts", "skipped")
        else:
            st, out = req("POST", "/items/os_proposal_contacts", {"os_proposals_id": pid, "contacts_id": cid})
            bump("os_proposal_contacts", "created" if st in (200, 201, 204) else "failed")
            if st not in (200, 201, 204):
                print("POST proposal contact failed:", p["name"], cid, st, out)

# ---------------------------------------------------------------- 5. voided expense
VOID_EXPENSE = {
    "name": "Figma seat duplicate charge",
    "vendor": "Figma",
    "cost": 45.00,
    "category": "software",
    "status": "voided",
    "billing_term": "one_time",
    "date": "2026-06-18T12:00:00Z",
    "is_billable": False,
    "is_reimbursable": False,
    "description": "Duplicate seat charge entered twice during June card reconciliation. This entry was voided; the correct charge remains on the Figma Organization seats record.",
    "is_test_data": False,
}
rows = get("os_expenses", {"fields": "id", "filter": {"name": {"_eq": VOID_EXPENSE["name"]}, "vendor": {"_eq": "Figma"}}, "limit": 1})
if rows:
    bump("os_expenses(voided)", "skipped")
else:
    st, out = req("POST", "/items/os_expenses", VOID_EXPENSE)
    bump("os_expenses(voided)", "created" if st in (200, 201, 204) else "failed")
    if st not in (200, 201, 204):
        print("POST voided expense failed:", st, out)

# ---------------------------------------------------------------- 6. infra_snapshots stripe MRR
# Mirror portal-src lib/portal/analytics/revenue.ts: MRR = sum of monthly-normalized
# totals over active recurring invoices (week x52/12, year /12, else pass-through).
invs = get("os_invoices", {"fields": "billing_type,subscription_status,billing_interval,total", "limit": -1})
mrr = 0.0
active_count = 0
for inv in invs:
    if inv.get("billing_type") != "recurring" or inv.get("subscription_status") != "active":
        continue
    active_count += 1
    total = float(inv.get("total") or 0)
    interval = inv.get("billing_interval")
    if interval == "week":
        mrr += total * 52 / 12
    elif interval == "year":
        mrr += total / 12
    else:
        mrr += total
mrr = round(mrr, 2)
print("live revenue KPI: MRR=%.2f active_recurring=%d" % (mrr, active_count))

snaps = get("infra_snapshots", {"fields": "id,payload", "limit": -1})
for s in snaps:
    p = s.get("payload")
    was_string = isinstance(p, str)
    if was_string:
        try:
            p = json.loads(p)
        except ValueError:
            bump("infra_snapshots(stripe patch)", "failed")
            print("unparseable payload on", s["id"])
            continue
    if not isinstance(p, dict):
        bump("infra_snapshots(stripe patch)", "failed")
        continue
    stripe = p.get("stripe") or {}
    if stripe.get("mrrUsd") == mrr and stripe.get("activeSubscriptionCount") == active_count:
        bump("infra_snapshots(stripe patch)", "skipped")
        continue
    stripe["mrrUsd"] = mrr
    stripe["activeSubscriptionCount"] = active_count
    p["stripe"] = stripe
    body = {"payload": json.dumps(p) if was_string else p}
    st, out = req("PATCH", "/items/infra_snapshots/%s" % s["id"], body)
    bump("infra_snapshots(stripe patch)", "updated" if st == 200 else "failed")
    if st != 200:
        print("PATCH infra snapshot failed:", s["id"], st, out)

# ---------------------------------------------------------------- 7. os_settings counters
invoice_max = 0
for inv in get("os_invoices", {"fields": "invoice_number", "limit": -1}):
    n = inv.get("invoice_number") or ""
    if n.startswith("INV-"):
        try:
            invoice_max = max(invoice_max, int(n.rsplit("-", 1)[1]))
        except ValueError:
            pass
proposal_count = len(get("os_proposals", {"fields": "id", "limit": -1}))

st, out = req("GET", "/items/os_settings")
settings = out.get("data", {}) if st == 200 else {}
patch = {}
if settings.get("next_invoice_number") is None:
    patch["next_invoice_number"] = invoice_max + 1
if settings.get("next_proposal_number") is None:
    patch["next_proposal_number"] = proposal_count + 1
if patch:
    st, out = req("PATCH", "/items/os_settings", patch)
    bump("os_settings(counters)", "updated" if st == 200 else "failed")
    if st != 200:
        print("PATCH os_settings failed:", st, out)
    else:
        print("os_settings set:", json.dumps(patch))
else:
    bump("os_settings(counters)", "skipped")

# ---------------------------------------------------------------- report
for col in sorted(counts):
    c = counts[col]
    print("%s: created %d / updated %d / skipped %d / failed %d" % (col, c["created"], c["updated"], c["skipped"], c["failed"]))

# ---------------------------------------------------------------- verify (live probes)
print("\n== VERIFY ==")
fails = []

rows = get("repositories", {"fields": "name,project_id,description", "filter": {"name": {"_eq": "bloom-shopify"}}, "limit": 1})
ok = rows and rows[0].get("project_id") == BLOOM_PROJECT and rows[0].get("description")
print("bloom-shopify pointer+description:", "OK" if ok else "FAIL", rows)
if not ok:
    fails.append("bloom pointer")

nulldesc = get("repositories", {"fields": "name", "filter": {"description": {"_null": True}}, "limit": -1})
print("repos with null description:", [r["name"] for r in nulldesc], "(expect only repos outside the 5-name backlog)")
leftover = [r["name"] for r in nulldesc if r["name"] in REPO_DESCRIPTIONS]
if leftover:
    fails.append("repo descriptions: %s" % leftover)

caps = get("os_projects", {"fields": "name,budget_cap", "filter": {"name": {"_in": list(BUDGET_CAPS.keys())}}, "limit": -1})
capfail = [c["name"] for c in caps if c.get("budget_cap") is None]
print("budget caps:", {c["name"]: c.get("budget_cap") for c in caps})
if capfail:
    fails.append("budget_cap: %s" % capfail)

# GraphQL probe with the portal's PROPOSAL_FIELDS shape
gql = {
    "query": """
    query { os_proposals(filter: {organization: {id: {_in: [3,4,5]}}}, limit: 10, sort: ["name"]) {
      id name status expiration_date total proposal_notes line_items date_created sort
      deal { id name }
      organization { id name service_status }
      contacts { id contacts_id { id first_name last_name } }
    } }"""
}
st, out = req("POST", "/graphql", gql)
props = (out.get("data") or {}).get("os_proposals") if st == 200 and isinstance(out, dict) else None
if props is None:
    fails.append("graphql proposals probe: %s %s" % (st, str(out)[:200]))
    print("graphql proposals probe FAILED:", st, str(out)[:300])
else:
    print("graphql proposals (orgs 3/4/5): %d rows" % len(props))
    for pr in props:
        cn = ["%s %s" % ((c.get("contacts_id") or {}).get("first_name"), (c.get("contacts_id") or {}).get("last_name")) for c in pr.get("contacts") or []]
        print("  %s | %s | org=%s | deal=%s | contacts=%s" % (pr["name"][:48], pr["status"], (pr.get("organization") or {}).get("name"), (pr.get("deal") or {}).get("name"), cn))
    if len(props) < 6:
        fails.append("expected >=6 proposals for orgs 3/4/5, got %d" % len(props))

st, out = req("POST", "/graphql", {"query": "query { os_expenses(filter: {status: {_eq: \"voided\"}}) { id name vendor cost status } }"})
vexp = (out.get("data") or {}).get("os_expenses") if st == 200 and isinstance(out, dict) else None
print("graphql voided expenses:", json.dumps(vexp)[:200] if vexp is not None else "FAILED %s" % st)
if not vexp:
    fails.append("voided expense probe")

snaps = get("infra_snapshots", {"fields": "id,payload", "limit": -1})
bad = []
for s in snaps:
    p = s.get("payload")
    if isinstance(p, str):
        p = json.loads(p)
    stripe = (p or {}).get("stripe") or {}
    if stripe.get("mrrUsd") != mrr or stripe.get("activeSubscriptionCount") != active_count:
        bad.append(s["id"][:8])
print("infra_snapshots stripe: %d rows, all mrrUsd=%.2f subs=%d: %s" % (len(snaps), mrr, active_count, "OK" if not bad else "FAIL %s" % bad))
if bad:
    fails.append("infra stripe: %s" % bad)

st, out = req("GET", "/items/os_settings")
s = out.get("data", {})
print("os_settings: next_invoice_number=%s next_proposal_number=%s (live invoice max %d, proposals %d)" % (
    s.get("next_invoice_number"), s.get("next_proposal_number"), invoice_max, proposal_count))
if not s.get("next_invoice_number") or not s.get("next_proposal_number"):
    fails.append("os_settings counters unset")

print("\nVERIFY RESULT:", "PASS" if not fails else "FAIL: %s" % "; ".join(fails))
