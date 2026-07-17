#!/usr/bin/env python3
"""Gap-fix seed: dashboard / organizations / projects / deals failures (2026-07-16).

Fixes (diagnosed against frozen portal-src):
  A. Dashboard MRR $0 / Active Recurring 0: predicate is billing_type=recurring
     AND subscription_status=active (lib/portal/analytics/revenue.ts:120). All
     recurring os_invoices rows had subscription_status NULL. Fill-only-when-null
     (a sibling gapfix script also backfills these; both skip non-null).
  B. 'Someone' bylines: os_project_updates.user_created IS set (28/28 rows) but
     the demo policy's directus_users read is filtered to $CURRENT_USER, so every
     author resolves null for the demo viewer (lib/portal/services/project-updates.ts:45).
     ADD a second read permission row (no filter, name fields only).
  C. Org/project logos broken: <img> hits cms.musterr.dev/assets/<id> with NO
     auth (organizations/page.tsx:158, projects/project-card.tsx:46); the PUBLIC
     policy has zero directus_files read -> 403. ADD public read on image/* files.
  D. Deals Closed Won $0: KPI matches stage name 'closed won'/'closed-won'
     (lib/portal/services/deals.ts:69) but the stage row is named 'Won'.
     Rename that one stage row to 'Closed Won' (3 deals, $96,000, past close dates).
  E. Client Site Analytics empty state: set matomo_site_id on client orgs 2..8
     (fill-only-when-null). Matomo DATA stays env-gated (MATOMO_URL/TOKEN empty).
  F. Infrastructure Operations dashes: getLatestSnapshot() prefers a persisted
     infra_snapshots CMS row over live env-gated APIs (lib/infra/storage.ts:132).
     Collection did not exist. Create it additively + seed 14 daily snapshots.

Idempotent. No deletes. No non-null value is ever overwritten. Admin token is
read from ~/elk-os/.env inside this script and never printed.
"""
import json, os, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

BASE = "https://cms.musterr.dev"
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
PUBLIC_POLICY = "abf8a154-5b1c-4a46-ac9c-7300570f4f17"
WON_STAGE = "01668fb5-ecbb-4ad6-8518-bfc06fd25887"


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
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(r, timeout=60)
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode()[:400]}


report = {}

# ── A. Invoices: fill subscription_status / billing_interval when null ───────
SUB_PLAN = {
    "INV-2026-002": ("active", None),
    "INV-2026-302": ("active", "month"),
    "INV-2026-303": ("incomplete", "month"),  # draft
    "INV-2026-305": ("active", "month"),
    "INV-2026-306": ("active", "month"),
    "INV-2026-311": ("past_due", "month"),    # overdue
    "INV-2026-312": ("active", "month"),
    "INV-2026-313": ("active", "year"),       # 12000/yr -> 1000/mo
    "INV-2026-315": ("past_due", "year"),     # overdue
    "INV-2026-321": ("active", None),
    "INV-2026-322": ("past_due", None),       # overdue
}
r = req("GET", "/items/os_invoices?filter[billing_type][_eq]=recurring"
        "&fields=id,invoice_number,subscription_status,billing_interval&limit=100")
inv_updated = inv_skipped = 0
for inv in r.get("data", []):
    plan = SUB_PLAN.get(inv["invoice_number"])
    if not plan:
        continue
    status, interval = plan
    patch = {}
    if inv.get("subscription_status") in (None, ""):
        patch["subscription_status"] = status
    if interval and inv.get("billing_interval") in (None, ""):
        patch["billing_interval"] = interval
    if patch:
        pr = req("PATCH", f"/items/os_invoices/{inv['id']}", patch)
        if "_http" in pr:
            print("os_invoices PATCH FAILED", inv["invoice_number"], pr)
        else:
            inv_updated += 1
    else:
        inv_skipped += 1
print(f"os_invoices: created 0 / updated {inv_updated} / skipped {inv_skipped}")
report["invoices"] = {"updated": inv_updated, "skipped": inv_skipped}

# ── B. Demo policy: additive unfiltered read on directus_users ───────────────
r = req("GET", f"/permissions?filter[policy][_eq]={DEMO_POLICY}"
        "&filter[collection][_eq]=directus_users&filter[action][_eq]=read"
        "&fields=id,permissions,fields&limit=20")
rows = r.get("data", [])
has_open = any(not row.get("permissions") for row in rows)
if has_open:
    print("permissions(directus_users demo): skipped (open read exists)")
    report["perm_users"] = "already-present"
else:
    pr = req("POST", "/permissions", {
        "policy": DEMO_POLICY,
        "collection": "directus_users",
        "action": "read",
        "permissions": {},
        "fields": ["id", "first_name", "last_name", "avatar", "title"],
    })
    ok = "_http" not in pr
    print("permissions(directus_users demo): created", 1 if ok else 0, "" if ok else pr)
    report["perm_users"] = "created" if ok else pr

# ── C. Public policy: additive read on directus_files (images only) ──────────
r = req("GET", f"/permissions?filter[policy][_eq]={PUBLIC_POLICY}"
        "&filter[collection][_eq]=directus_files&filter[action][_eq]=read"
        "&fields=id,permissions&limit=20")
if r.get("data"):
    print("permissions(directus_files public): skipped (exists)")
    report["perm_files_public"] = "already-present"
else:
    pr = req("POST", "/permissions", {
        "policy": PUBLIC_POLICY,
        "collection": "directus_files",
        "action": "read",
        "permissions": {"type": {"_starts_with": "image/"}},
        "fields": ["*"],
    })
    ok = "_http" not in pr
    print("permissions(directus_files public): created", 1 if ok else 0, "" if ok else pr)
    report["perm_files_public"] = "created" if ok else pr

# ── D. Deal stage rename: Won -> Closed Won ──────────────────────────────────
r = req("GET", f"/items/os_deal_stages/{WON_STAGE}?fields=id,name")
name = (r.get("data") or {}).get("name")
if name == "Won":
    pr = req("PATCH", f"/items/os_deal_stages/{WON_STAGE}", {"name": "Closed Won"})
    ok = "_http" not in pr
    print("os_deal_stages: updated", 1 if ok else 0, "" if ok else pr)
    report["deal_stage"] = "renamed" if ok else pr
else:
    print(f"os_deal_stages: skipped (name is {name!r})")
    report["deal_stage"] = f"skipped ({name})"

# ── E. Orgs: matomo_site_id on client orgs (fill only when null) ─────────────
r = req("GET", "/items/organizations?fields=id,name,matomo_site_id&limit=20")
org_updated = org_skipped = 0
for org in r.get("data", []):
    if org["id"] == 1:
        continue  # Demo Co is the agency itself, not a client site
    if org.get("matomo_site_id") is None:
        pr = req("PATCH", f"/items/organizations/{org['id']}",
                 {"matomo_site_id": int(org["id"])})
        if "_http" in pr:
            print("organizations PATCH FAILED", org["id"], pr)
        else:
            org_updated += 1
    else:
        org_skipped += 1
print(f"organizations(matomo_site_id): created 0 / updated {org_updated} / skipped {org_skipped}")
report["orgs_matomo"] = {"updated": org_updated, "skipped": org_skipped}

# ── F. infra_snapshots: create collection + seed 14 daily rows ────────────────
exists = "_http" not in req("GET", "/collections/infra_snapshots")
if not exists:
    fields = [
        {"field": "id", "type": "uuid",
         "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
         "schema": {"is_primary_key": True, "length": 36, "has_auto_increment": False}},
        {"field": "collected_at", "type": "timestamp",
         "meta": {"interface": "datetime"}, "schema": {}},
        {"field": "payload", "type": "json",
         "meta": {"interface": "input-code", "special": ["cast-json"]}, "schema": {}},
        {"field": "hc_total", "type": "integer", "meta": {"interface": "input"}, "schema": {}},
        {"field": "hc_up", "type": "integer", "meta": {"interface": "input"}, "schema": {}},
        {"field": "hc_down", "type": "integer", "meta": {"interface": "input"}, "schema": {}},
        {"field": "hc_grace", "type": "integer", "meta": {"interface": "input"}, "schema": {}},
        {"field": "down_slugs", "type": "json",
         "meta": {"interface": "input-code", "special": ["cast-json"]}, "schema": {}},
        {"field": "aws_mtd_cost_usd", "type": "float", "meta": {"interface": "input"}, "schema": {}},
        {"field": "netlify_bw_used_gib", "type": "float", "meta": {"interface": "input"}, "schema": {}},
        {"field": "netlify_bw_included_gib", "type": "float", "meta": {"interface": "input"}, "schema": {}},
        {"field": "neon_cost_usd", "type": "float", "meta": {"interface": "input"}, "schema": {}},
        {"field": "neon_cu_hours", "type": "float", "meta": {"interface": "input"}, "schema": {}},
        {"field": "is_test_data", "type": "boolean",
         "meta": {"interface": "boolean"}, "schema": {"default_value": False}},
    ]
    cr = req("POST", "/collections", {
        "collection": "infra_snapshots",
        "meta": {"icon": "monitoring",
                 "note": "Infra Ops dashboard snapshots (seeded demo data; cron may append)"},
        "schema": {},
        "fields": fields,
    })
    if "_http" in cr:
        print("infra_snapshots collection CREATE FAILED", cr)
        report["infra_collection"] = cr
    else:
        print("infra_snapshots: collection created")
        report["infra_collection"] = "created"
else:
    print("infra_snapshots: collection exists / skipped")
    report["infra_collection"] = "already-present"


def build_snapshot(day):
    """Full InfraSnapshot payload (lib/infra/types.ts) for one day. Stripe MRR
    kept coherent with the CMS revenue KPI (7 active recurring, ~$8,150/mo)."""
    iso = day.strftime("%Y-%m-%dT06:00:00Z")
    dom = day.day
    scale = dom / 16.0
    aws_mtd = round(6.09 * dom, 2)
    ping = day.strftime("%Y-%m-%dT05:54:00Z")
    checks = [
        ("app.musterr.dev", "app-musterr-dev"),
        ("cms.musterr.dev", "cms-musterr-dev"),
        ("cedarandco.example", "cedarandco-example"),
        ("harborfitness.example", "harborfitness-example"),
        ("bloombotanicals.example", "bloombotanicals-example"),
        ("sterlingvine.example", "sterlingvine-example"),
        ("analytics (Matomo)", "matomo-analytics"),
        ("nightly backups", "nightly-backups"),
    ]
    grace = 1 if dom in (5, 9) else 0
    hc = {
        "total": len(checks),
        "upCount": len(checks) - grace,
        "downCount": 0,
        "graceCount": grace,
        "checks": [
            {"name": n, "slug": s,
             "status": "grace" if (grace and s == "nightly-backups") else "up",
             "lastPing": ping}
            for n, s in checks
        ],
    }

    def deploys(prefix, base_sec, fail=False):
        out = []
        for i in range(3):
            d = day - timedelta(days=i * 2 + 1)
            state = "error" if (fail and i == 2) else "ready"
            out.append({
                "id": f"dpl_demo_{prefix}_{d.strftime('%m%d')}",
                "state": state,
                "createdAt": d.strftime("%Y-%m-%dT18:22:00Z"),
                "deployTime": base_sec + i * 13,
                "errorMessage": "Build exceeded time limit" if state == "error" else None,
            })
        return out

    netlify = {
        "sites": [
            {"id": "site_demo_cedar", "name": "cedar-and-co-coffee",
             "customDomain": "cedarandco.example", "publishedDeployState": "ready",
             "recentDeploys": deploys("cedar", 48)},
            {"id": "site_demo_harbor", "name": "harbor-fitness",
             "customDomain": "harborfitness.example", "publishedDeployState": "ready",
             "recentDeploys": deploys("harbor", 61)},
            {"id": "site_demo_bloom", "name": "bloom-botanicals",
             "customDomain": "bloombotanicals.example", "publishedDeployState": "ready",
             "recentDeploys": deploys("bloom", 39, fail=True)},
            {"id": "site_demo_sterling", "name": "sterling-and-vine",
             "customDomain": "sterlingvine.example", "publishedDeployState": "ready",
             "recentDeploys": deploys("sterling", 55)},
        ],
        "bandwidth": {
            "usedGib": round(1.72 * dom, 2),
            "includedGib": 100.0,
            "periodStart": "2026-07-01T00:00:00Z",
            "periodEnd": "2026-08-01T00:00:00Z",
        },
    }
    runs = []
    run_specs = [
        ("elk-os-portal", "quality", "success", "main", 2),
        ("elk-os-portal", "deploy-production", "success", "main", 5),
        ("cedar-storefront", "quality", "failure", "feat/loyalty-tiers", 9),
        ("cedar-storefront", "quality", "success", "main", 14),
        ("harbor-member-app", "quality", "success", "feat/class-schedule", 20),
        ("sterling-reservations", "nightly-backup", "success", "main", 26),
    ]
    for i, (repo, wf, concl, branch, hours_ago) in enumerate(run_specs):
        t = day.replace(hour=6) - timedelta(hours=hours_ago)
        rid = 90210000 + dom * 10 + i
        runs.append({
            "id": rid, "repo": f"demo-agency/{repo}", "workflowName": wf,
            "status": "completed", "conclusion": concl, "headBranch": branch,
            "createdAt": t.strftime("%Y-%m-%dT%H:00:00Z"),
            "htmlUrl": f"https://github.com/demo-agency/{repo}/actions/runs/{rid}",
        })
    neon_projects = [
        {"id": "proj_demo_muster", "name": "muster-demo-db", "region": "aws-us-west-2",
         "cuHoursMtd": round(12.7 * dom, 1), "estCostUsd": round(12.7 * dom * 0.16, 2),
         "storageGb": 1.9, "minCu": 1, "maxCu": 2, "overProvisioned": True},
        {"id": "proj_demo_cedar", "name": "cedar-loyalty-db", "region": "aws-us-west-2",
         "cuHoursMtd": round(7.4 * dom, 1), "estCostUsd": round(7.4 * dom * 0.16, 2),
         "storageGb": 3.2, "minCu": 0.25, "maxCu": 2, "overProvisioned": False},
        {"id": "proj_demo_harbor", "name": "harbor-member-db", "region": "aws-us-west-2",
         "cuHoursMtd": round(5.4 * dom, 1), "estCostUsd": round(5.4 * dom * 0.16, 2),
         "storageGb": 5.7, "minCu": 0.25, "maxCu": 2, "overProvisioned": False},
    ]
    total_cu = round(sum(p["cuHoursMtd"] for p in neon_projects), 1)
    compute = round(total_cu * 0.16, 2)
    storage_gb = round(sum(p["storageGb"] for p in neon_projects), 1)
    storage_cost = round(storage_gb * 0.15, 2)
    neon = {
        "projectCount": 3, "totalCuHoursMtd": total_cu, "usdPerCuHour": 0.16,
        "computeCostUsd": compute, "totalStorageGb": storage_gb,
        "storageCostUsd": storage_cost, "totalCostUsd": round(compute + storage_cost, 2),
        "periodResetAt": "2026-08-01T00:00:00Z",
        "projects": sorted(neon_projects, key=lambda p: -p["estCostUsd"]),
    }
    return {
        "collectedAt": iso,
        "aws": {
            "accountId": "123456789012", "region": "us-west-2",
            "instances": [
                {"instanceId": "i-0demo1a2b3c4d5e6", "instanceType": "t3.medium",
                 "name": "muster-demo", "state": "running",
                 "launchTime": "2026-06-28T04:11:00Z",
                 "cpuUtilizationAvg": round(11.0 + (dom % 5) * 1.7, 1),
                 "networkInSum": int(2.1e9 * scale) + 40000000,
                 "networkOutSum": int(5.6e9 * scale) + 90000000,
                 "statusCheckFailed": 0},
                {"instanceId": "i-0demo7f8091a2b3c", "instanceType": "t3.small",
                 "name": "elk-staging", "state": "running",
                 "launchTime": "2026-07-02T16:40:00Z",
                 "cpuUtilizationAvg": round(4.2 + (dom % 3) * 0.9, 1),
                 "networkInSum": int(4.1e8 * scale) + 9000000,
                 "networkOutSum": int(7.7e8 * scale) + 12000000,
                 "statusCheckFailed": 0},
                {"instanceId": "i-0demod4e5f60718a", "instanceType": "t3.micro",
                 "name": "ci-runner-01", "state": "stopped",
                 "launchTime": "2026-05-19T09:03:00Z",
                 "cpuUtilizationAvg": None, "networkInSum": None,
                 "networkOutSum": None, "statusCheckFailed": None},
            ],
            "mtdCostUsd": aws_mtd,
            "mtdCostPeriod": f"2026-07-01 to {day.strftime('%Y-%m-%d')}",
        },
        "netlify": netlify,
        "healthchecks": hc,
        "stripe": {"mrrUsd": 8150, "activeSubscriptionCount": 7},
        "github": {
            "runs": runs,
            "repos": ["demo-agency/elk-os-portal", "demo-agency/cedar-storefront",
                      "demo-agency/harbor-member-app", "demo-agency/sterling-reservations"],
        },
        "neon": neon,
        "errors": [],
    }


snap_created = snap_skipped = 0
today = datetime(2026, 7, 16, tzinfo=timezone.utc)
for back in range(13, -1, -1):
    day = today - timedelta(days=back)
    iso = day.strftime("%Y-%m-%dT06:00:00Z")
    ex = req("GET", f"/items/infra_snapshots?filter[collected_at][_eq]={iso}&fields=id&limit=1")
    if ex.get("data"):
        snap_skipped += 1
        continue
    snap = build_snapshot(day)
    hc = snap["healthchecks"]
    row = {
        "collected_at": iso,
        "payload": snap,
        "hc_total": hc["total"], "hc_up": hc["upCount"],
        "hc_down": hc["downCount"], "hc_grace": hc["graceCount"],
        "down_slugs": [c["slug"] for c in hc["checks"] if c["status"] == "down"],
        "aws_mtd_cost_usd": snap["aws"]["mtdCostUsd"],
        "netlify_bw_used_gib": snap["netlify"]["bandwidth"]["usedGib"],
        "netlify_bw_included_gib": 100.0,
        "neon_cost_usd": snap["neon"]["totalCostUsd"],
        "neon_cu_hours": snap["neon"]["totalCuHoursMtd"],
        "is_test_data": False,
    }
    pr = req("POST", "/items/infra_snapshots", row)
    if "_http" in pr:
        print("infra_snapshots POST FAILED", iso, pr)
    else:
        snap_created += 1
print(f"infra_snapshots: created {snap_created} / updated 0 / skipped {snap_skipped}")
report["infra_rows"] = {"created": snap_created, "skipped": snap_skipped}

print("REPORT " + json.dumps(report, default=str))
