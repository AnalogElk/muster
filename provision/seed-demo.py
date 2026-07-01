#!/usr/bin/env python3
"""
Seed the Muster demo box with real + coherent content so the portal is full.

PRIORITY A — replace the synthetic starter board with the REAL Muster build:
  creates a "Muster" project and seeds the actual os_tasks that built the demo
  (exported from prod, provision/seed/muster-tasks.json — an epic + phases
  P0-P7 + follow-ups, hierarchy + statuses preserved, is_test_data=false), then
  removes the synthetic starter tasks/projects/sprints so the board shows only
  the real build.

PRIORITY B — fill the bare portal sections with a modest, tasteful, all-synthetic
  set: a deal pipeline (stages + deals), a proposal, CRM activities, two invoices
  (one paid with a payment, one open) + line items, two products, project updates,
  and Muster releases. Everything is is_test_data=false so it renders for the
  read-only demo user (who is NOT a test viewer).

Idempotent: re-running upserts by natural key and never duplicates.

Usage:
    DIRECTUS_ADMIN_TOKEN=... DIRECTUS_URL=https://cms.<box>.sslip.io \\
        python3 provision/seed-demo.py
"""
import os, sys, json, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.environ.get("DIRECTUS_URL", "https://cms.34.220.64.149.sslip.io").rstrip("/")
TOKEN = os.environ["DIRECTUS_ADMIN_TOKEN"]

MUSTER_PROJECT_ID = "0ef5827c-924d-4c2a-a769-d9d7c84097e1"  # reuse prod id for traceability
ORG_ID = 1  # "Demo Co"
DEMO_USER = "257a4b75-deff-476d-953d-1898c57f6684"


def req(method, path, body=None):
    url = B + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def get_all(coll, fields="*"):
    s, r = req("GET", "/items/%s?limit=-1&fields=%s" % (coll, fields))
    return r.get("data", []) if s == 200 else []


def find_one(coll, field, value, extra=""):
    from urllib.parse import quote
    s, r = req("GET", "/items/%s?filter[%s][_eq]=%s&limit=1&fields=id%s" %
               (coll, field, quote(str(value)), extra))
    d = r.get("data", []) if s == 200 else []
    return d[0] if d else None


def create(coll, row):
    s, r = req("POST", "/items/" + coll, row)
    if s >= 300:
        print("  CREATE FAIL", coll, s, json.dumps(r)[:300]); return None
    return r["data"]


def upsert(coll, key_field, key_value, row):
    existing = find_one(coll, key_field, key_value)
    if existing:
        req("PATCH", "/items/%s/%s" % (coll, existing["id"]), row)
        return existing["id"], False
    d = create(coll, row)
    return (d["id"] if d else None), True


# --------------------------------------------------------------------------
# PRIORITY A: the real Muster board
# --------------------------------------------------------------------------
def seed_board():
    print("== PRIORITY A: real Muster board ==")
    tasks = json.load(open(os.path.join(HERE, "seed", "muster-tasks.json")))
    muster_ids = {t["id"] for t in tasks}

    # 1. Muster project (fixed id, upsert)
    proj = {
        "id": MUSTER_PROJECT_ID,
        "name": "Muster",
        "status": "in_progress",
        "kind": "deliverable",
        "project_type": "code",
        "organization": ORG_ID,
        "is_test_data": False,
        "description": ("Elk OS / Muster — the whole Analog Elk agency operating "
                        "system repackaged as a one-command self-host product, built "
                        "as the system's own final test case (the system shipping the "
                        "system). Epic + phases P0-P7 + follow-ups."),
    }
    if find_one("os_projects", "id", MUSTER_PROJECT_ID):
        req("PATCH", "/items/os_projects/%s" % MUSTER_PROJECT_ID, proj)
        print("  project upserted (exists): Muster")
    else:
        create("os_projects", proj)
        print("  project created: Muster")

    # 2. delete synthetic sprints (prod has none) so board isn't cluttered
    for sp in get_all("os_sprints", "id,name"):
        req("DELETE", "/items/os_sprints/%s" % sp["id"])
        print("  deleted synthetic sprint:", sp.get("name"))

    # 3. delete synthetic tasks (anything not part of the real Muster set)
    for t in get_all("os_tasks", "id,name"):
        if t["id"] not in muster_ids:
            req("DELETE", "/items/os_tasks/%s" % t["id"])
            print("  deleted synthetic task:", (t.get("name") or "")[:40])

    # 4. insert the real tasks (root first so parent FK is satisfied)
    roots = [t for t in tasks if not t.get("parent_task")]
    children = [t for t in tasks if t.get("parent_task")]
    for t in roots + children:
        row = dict(t)
        row["project"] = MUSTER_PROJECT_ID
        row["is_test_data"] = False
        if find_one("os_tasks", "id", t["id"]):
            req("PATCH", "/items/os_tasks/%s" % t["id"], row)
        else:
            create("os_tasks", row)
    print("  seeded %d real tasks (%d roots, %d children)" %
          (len(tasks), len(roots), len(children)))

    # 5. delete now-empty synthetic projects
    for p in get_all("os_projects", "id,name"):
        if p["id"] != MUSTER_PROJECT_ID:
            req("DELETE", "/items/os_projects/%s" % p["id"])
            print("  deleted synthetic project:", p.get("name"))


# --------------------------------------------------------------------------
# PRIORITY B: fill bare portal sections (all synthetic)
# --------------------------------------------------------------------------
def seed_crm_and_billing():
    print("== PRIORITY B: fill portal sections ==")

    # org tidy-up
    req("PATCH", "/items/organizations/%s" % ORG_ID, {
        "status": "active", "tier": "premium", "is_test_data": False,
        "website": "https://democo.example", "email": "hello@democo.example",
    })

    # ---- deal stages ----
    STAGES = [("Lead", "#94A3B8"), ("Qualified", "#38BDF8"), ("Proposal", "#A855F7"),
              ("Negotiation", "#F59E0B"), ("Won", "#22C55E")]
    stage_ids = {}
    for i, (name, color) in enumerate(STAGES):
        sid, _ = upsert("os_deal_stages", "name", name, {
            "name": name, "color": color, "sort": i + 1, "status": "published"})
        stage_ids[name] = sid
    print("  deal stages:", list(stage_ids))

    # ---- deals ----
    DEALS = [
        ("Demo Co — Muster Self-Host License", "Won", 12000, "2026-06-20"),
        ("Acme Retail — Portal Rebuild", "Proposal", 24000, "2026-07-30"),
        ("Bluebird Media — CRM Migration", "Qualified", 8000, "2026-08-15"),
        ("Cedar & Co — Discovery Engagement", "Lead", 3000, "2026-09-01"),
    ]
    deal_ids = {}
    for name, stage, value, close in DEALS:
        did, _ = upsert("os_deals", "name", name, {
            "name": name, "deal_stage": stage_ids[stage], "deal_value": value,
            "close_date": close, "organization": ORG_ID, "is_test_data": False,
            "deal_notes": "Synthetic demo pipeline record.",
        })
        deal_ids[name] = did
    print("  deals:", len(deal_ids))

    # ---- proposal ----
    prop_line_items = [
        {"description": "Discovery & architecture", "quantity": 1, "unit_price": 3000, "amount": 3000},
        {"description": "Portal + CMS implementation", "quantity": 1, "unit_price": 7000, "amount": 7000},
        {"description": "Deployment & handoff", "quantity": 1, "unit_price": 2000, "amount": 2000},
    ]
    upsert("os_proposals", "name", "Muster Self-Host — Statement of Work", {
        "name": "Muster Self-Host — Statement of Work",
        "deal": deal_ids["Demo Co — Muster Self-Host License"],
        "organization": ORG_ID, "status": "submitted", "total": 12000,
        "line_items": prop_line_items, "is_test_data": False,
        "proposal_notes": "One-time self-host build: discovery, implementation, deploy.",
        "expiration_date": "2026-07-15T00:00:00Z",
    })
    print("  proposal: 1")

    # ---- activities ----
    ACTS = [
        ("Kickoff call with Demo Co", "call", "completed", "2026-06-10T16:00:00Z"),
        ("Portal walkthrough demo", "meeting", "open", "2026-07-05T17:00:00Z"),
        ("Send SOW follow-up email", "email", "open", "2026-07-02T15:00:00Z"),
    ]
    for name, atype, status, due in ACTS:
        upsert("os_activities", "name", name, {
            "name": name, "activity_type": atype, "status": status,
            "organization": ORG_ID, "due_date": due, "is_test_data": False,
            "deal": deal_ids["Demo Co — Muster Self-Host License"],
            "assigned_to": DEMO_USER,
            "activity_notes": "Synthetic demo CRM activity.",
        })
    print("  activities:", len(ACTS))

    # ---- invoices + line items + payment ----
    def seed_invoice(number, status, billing_type, items, issue, due,
                     paid_amount, billing_interval=None):
        subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
        row = {
            "invoice_number": number, "status": status, "billing_type": billing_type,
            "organization": ORG_ID, "project": MUSTER_PROJECT_ID,
            "issue_date": issue, "due_date": due, "is_test_data": False,
            "subtotal": subtotal, "total_tax": 0, "total": subtotal,
            "amount_paid": paid_amount, "amount_due": subtotal - paid_amount,
        }
        if billing_interval:
            row["billing_interval"] = billing_interval
        inv_id, created = upsert("os_invoices", "invoice_number", number, row)
        if created:  # only add line items on first creation
            for n, it in enumerate(items):
                create("os_invoice_items", {
                    "invoice": inv_id, "type": "custom", "item_name": it["name"],
                    "description": it["name"], "quantity": it["quantity"],
                    "unit_price": it["unit_price"], "override_unit_price": True,
                    "line_amount": it["quantity"] * it["unit_price"],
                    "line_item_number": n + 1, "tax_rate": 0, "tax_amount": 0,
                    "is_test_data": False,
                })
        return inv_id

    inv1_items = [
        {"name": "Discovery & architecture", "quantity": 1, "unit_price": 3000},
        {"name": "Portal + CMS implementation", "quantity": 1, "unit_price": 7000},
        {"name": "Deployment & handoff", "quantity": 1, "unit_price": 2000},
    ]
    inv1 = seed_invoice("INV-2026-001", "paid", "one_time", inv1_items,
                        "2026-06-01T00:00:00Z", "2026-06-15T00:00:00Z", 12000)
    inv2_items = [{"name": "Muster hosting & support (monthly)", "quantity": 1, "unit_price": 500}]
    seed_invoice("INV-2026-002", "submitted", "recurring", inv2_items,
                 "2026-06-28T00:00:00Z", "2026-07-12T00:00:00Z", 0,
                 billing_interval="month")
    print("  invoices: 2 (+ line items)")

    # payment for the paid invoice
    if inv1 and not find_one("os_payments", "stripe_payment_id", "demo_pi_001"):
        create("os_payments", {
            "invoice": inv1, "organization": ORG_ID, "amount": 12000,
            "status": "paid", "payment_date": "2026-06-12T14:30:00Z",
            "payment_method_type": "card", "stripe_payment_id": "demo_pi_001",
            "is_test_data": False,
        })
        print("  payment: 1 (INV-2026-001 paid)")

    # ---- products ----
    PRODUCTS = [
        ("Muster Self-Host License", "The Analog Elk agency OS, self-hosted from one command."),
        ("Portal — Hosted Instance", "Managed hosting + support for the Muster portal + CMS."),
    ]
    for name, desc in PRODUCTS:
        upsert("os_products", "name", name, {
            "name": name, "description": desc, "status": "active",
            "organization": ORG_ID, "source_project": MUSTER_PROJECT_ID,
            "is_test_data": False,
        })
    print("  products:", len(PRODUCTS))

    # ---- project updates ----
    existing_updates = get_all("os_project_updates", "id")
    if len(existing_updates) == 0:
        for msg in [
            "All 8 phases green — the live, read-only Muster demo is up. The system shipped the system.",
            "Knowledge Base restored and seeded with the build's own architecture, loop, and gotchas docs.",
        ]:
            create("os_project_updates", {
                "project": MUSTER_PROJECT_ID, "message": msg,
                "is_client_visible": True, "is_test_data": False,
            })
        print("  project updates: 2")
    else:
        print("  project updates exist, skipped")

    # ---- releases (rename repo to muster, flip test flag, add one) ----
    repos = get_all("repositories", "id,name")
    repo_id = repos[0]["id"] if repos else None
    if repo_id:
        req("PATCH", "/items/repositories/%s" % repo_id, {"name": "muster"})
    # flip existing seeded release to visible + Muster narrative
    for rel in get_all("releases", "id,version"):
        req("PATCH", "/items/releases/%s" % rel["id"], {
            "is_test_data": False, "is_client_visible": True, "status": "published",
        })
    # add a v1.0.0 Muster release if absent
    if repo_id and not find_one("releases", "version", "v1.0.0-muster"):
        upsert("releases", "version", "v1.0.0-muster", {
            "version": "v1.0.0-muster", "title": "Muster v1.0.0 — live read-only demo",
            "repository_id": repo_id, "release_type": "major", "status": "published",
            "is_client_visible": True, "is_test_data": False,
            "release_date": "2026-06-30T00:00:00Z",
            "summary": "All eight phases green; public read-only self-host demo online.",
            "changelog": ("## Added\n- One-command self-host of the whole agency OS "
                          "(Postgres + Directus + portal + bundled RAG).\n- Public read-only "
                          "demo with a non-admin Employee role.\n- Portal Knowledge Base "
                          "seeded with the build's own docs.\n\n## Fixed\n- RAG port collision "
                          "that fooled the health check.\n- `releases` seed missing required "
                          "`repository_id`.\n- Bare-named seed files hitting the wrong "
                          "collection."),
        })
    print("  releases: reconciled + Muster v1.0.0")


def main():
    seed_board()
    seed_crm_and_billing()
    print("DONE")


if __name__ == "__main__":
    main()
