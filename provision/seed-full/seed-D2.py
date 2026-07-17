#!/usr/bin/env python3
"""seed-D2.py - Muster demo finance domain (domain-finance work package).

Seeds on cms.musterr.dev (admin token from ~/elk-os/.env, read inside this
script, never printed):

  1. os_invoice_items for the 17 zero-item existing invoices INV-2026-300..316
     (INV-2026-001/002 are skip-only: sums verified, nothing added).
  2. 14 NEW os_invoices INV-2026-317..330, all project + contact + org linked.
  3. os_invoice_items for the new invoices (incl. 3 billable-expense lines).
  4. 21 os_payments (8 existing paid, 6 new paid full, 2 new partial,
     5 pending on existing non-paid invoices). Upsert by stripe_payment_id.
  5. 18 os_expenses (8 receipt-bearing per assets-manifest canon), plus
     os_expense_items summing exactly to each cost.
  6. Billed-to-invoice linkage (expense.invoice_item -> new invoice line).
  7. GATED null-fill of project/contact on INV-2026-300..316
     (runs ONLY with NULLFILL_APPROVED=1 in env; otherwise skip + report).
  8. 16 os_subscriptions (orgs 2-8, 2-3 each) + 17 os_project_subscriptions.

Ledger rules honored: existing invoices are never modified (except the gated
step 7 null-fill of ONLY project/contact); line items sum EXACTLY to stored
subtotal/total; paid payments only where amount_paid matches; payments on
existing non-paid invoices are status=pending. Everything is_test_data:false,
idempotent (upsert by natural key), deterministic (fixed dates), add-only.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

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


def req(method, path, body=None, token=TOKEN, params=None):
    url = BASE + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()[:500]
        return e.code, {"error": raw}


def get_items(collection, filt=None, limit=200, fields=None):
    params = {"limit": limit}
    if filt:
        params["filter"] = json.dumps(filt)
    if fields:
        params["fields"] = fields
    st, body = req("GET", f"/items/{collection}", params=params)
    if st != 200:
        print(f"FATAL read {collection}: {st} {body}")
        sys.exit(1)
    return body["data"]


def norm(v):
    if isinstance(v, bool) or v is None:
        return v
    s = str(v)
    try:
        return str(Decimal(s).normalize())
    except Exception:
        pass
    if "T" in s and s[:4].isdigit():
        return s.replace(".000Z", "Z").replace("+00:00", "Z")[:19]
    return s


def upsert(collection, filt, payload, counts, match=None):
    """Search by natural key; create if absent; patch if planned fields differ.
    Returns the row id."""
    rows = get_items(collection, filt, limit=2)
    if not rows:
        st, body = req("POST", f"/items/{collection}", payload)
        if st not in (200, 201):
            print(f"FATAL create {collection}: {st} {body} payload={payload.get('name') or payload.get('item_name') or payload.get('invoice_number') or payload.get('stripe_payment_id')}")
            sys.exit(1)
        counts["created"] += 1
        return body["data"]["id"]
    row = rows[0]
    check = match if match is not None else [k for k in payload if k not in ("id",)]
    diff = {k: payload[k] for k in check if k in payload and norm(row.get(k)) != norm(payload[k])}
    if diff:
        st, body = req("PATCH", f"/items/{collection}/{row['id']}", diff)
        if st != 200:
            print(f"FATAL patch {collection}/{row['id']}: {st} {body}")
            sys.exit(1)
        counts["updated"] += 1
    else:
        counts["skipped"] += 1
    return row["id"]


def report(name, c):
    print(f"{name}: created {c['created']} / updated {c['updated']} / skipped {c['skipped']}")


D = Decimal
FLAG = {"is_test_data": False}
PRIMARY_CONTACT = {1: 1, 2: 7, 3: 8, 4: 4, 5: 5, 6: 6, 7: 9, 8: 10}

PROJ = {
    "cedar_web": "430df3e9-7f6d-4369-81cf-d9e5dc0fab00",
    "cedar_whole": "a42f4921-7747-4319-b09e-644f639e89c5",
    "north_brand": "91528c06-daee-41eb-b614-363afb1eb531",
    "north_seo": "193e5bd8-e9b2-471e-91e9-7c19aa2a2c7a",
    "vellum_port": "4ae1d3fa-92fb-443d-86c8-4636df95e41c",
    "harbor_app": "d16e4ef5-a11c-4165-8f5b-2a79fa1a1e51",
    "bloom_shop": "3d5677cf-af08-4df2-a29a-6a4925ab9268",
    "sterling": "cd1eae58-ec99-4444-bbe4-ae6ab9370cea",
    "meridian": "c6581803-8fe8-43e7-bb56-4f1e758e2a25",
    "vellum_motion": "b9a8afa7-7138-4b3d-84cc-407e6d28f0dc",
}

RECEIPTS = {
    "Figma": "20957fe3-228a-4321-97b9-f7e86ae3bfcd",
    "AWS": "145b4826-42e4-4606-a888-d55177ec261c",
    "Linear": "88a0cc37-3f44-4cc4-83d2-5cbf909ca2e2",
    "Amtrak": "741e4d99-c094-41c6-8304-f8554d3a3aec",
    "Moo Print": "ff17219c-ed64-4418-a7a0-21d4cae524e6",
    "Adobe Creative Cloud": "35049b7c-d6be-4482-a14a-27ea6b0ec38d",
    "Notion": "b65fb252-a34d-4f1a-be54-a6fb59540f29",
    "Uline": "092d753c-3cea-4a6f-9a20-a1361f2ef0e1",
}

# --------------------------------------------------------------------------
# Step 1: line items for existing invoices INV-2026-300..316.
# (type, item_name, description, qty, unit_price); sums assert to stored total.
# type 'item' rows link to F4 os_items rate card by exact name.
# --------------------------------------------------------------------------

EXISTING_ITEMS = {
    "INV-2026-300": ("3800.00", [
        ("item", "SEO Audit", "Technical and content audit with prioritized fix list.", "1", "1400.00"),
        ("item", "Analytics Setup", "Matomo property, goals, and dashboard views.", "1", "950.00"),
        ("custom", "Technical remediation sprint", "Fixes for crawl health and Core Web Vitals findings.", "1", "1450.00"),
    ]),
    "INV-2026-301": ("3800.00", [
        ("item", "Discovery Workshop", "Half-day goals and scope session.", "1", "1500.00"),
        ("item", "Content Migration", "Structured migration of pages and media.", "2", "850.00"),
        ("custom", "Product photography retouching", "Color correction and cropping for 40 product images.", "1", "600.00"),
    ]),
    "INV-2026-302": ("950.00", [
        ("item", "Hosting Care Plan Monthly", "Monthly hosting, backups, and monitoring.", "1", "450.00"),
        ("custom", "Priority support block", "Reserved support hours for the month.", "1", "500.00"),
    ]),
    "INV-2026-303": ("12000.00", [
        ("item", "Design Sprint", "One-week concept sprint with clickable prototype.", "1", "4500.00"),
        ("item", "Next.js Development Day", "Senior developer days on the storefront build.", "6", "1100.00"),
        ("custom", "Project management", "Sprint planning, standups, and status reporting.", "1", "900.00"),
    ]),
    "INV-2026-304": ("3800.00", [
        ("item", "Discovery Workshop", "Reservations flow discovery session.", "1", "1500.00"),
        ("item", "CMS Setup", "Directus provisioning and content model.", "1", "1800.00"),
        ("custom", "Reservations data model workshop", "Working session on table, seating, and shift data.", "1", "500.00"),
    ]),
    "INV-2026-305": ("1200.00", [
        ("item", "Hosting Care Plan Monthly", "Monthly hosting, backups, and monitoring.", "1", "450.00"),
        ("custom", "Managed content updates", "Content edits and page updates, hourly block.", "5", "150.00"),
    ]),
    "INV-2026-306": ("1500.00", [
        ("item", "Hosting Care Plan Monthly", "Monthly hosting, backups, and monitoring.", "1", "450.00"),
        ("item", "Analytics Setup", "Goal tracking and event taxonomy refresh.", "1", "950.00"),
        ("custom", "Plugin license pass-through", "Third-party plugin renewal billed at cost.", "1", "100.00"),
    ]),
    "INV-2026-307": ("4500.00", [
        ("item", "Discovery Workshop", "Campaign landing page discovery.", "1", "1500.00"),
        ("item", "Next.js Development Day", "Landing page build and integrations.", "2", "1100.00"),
        ("custom", "QA and launch checklist", "Cross-browser QA and go-live checklist.", "1", "800.00"),
    ]),
    "INV-2026-308": ("2500.00", [
        ("item", "SEO Audit", "Local search and menu page audit.", "1", "1400.00"),
        ("custom", "Menu and events content build", "Structured menu and private events pages.", "1", "1100.00"),
    ]),
    "INV-2026-309": ("2500.00", [
        ("item", "Analytics Setup", "Matomo property setup and handoff.", "1", "950.00"),
        ("item", "Content Migration", "Catalog copy and imagery migration.", "1", "850.00"),
        ("custom", "Training session", "Editor training for the in-house team.", "1", "700.00"),
    ]),
    "INV-2026-310": ("6000.00", [
        ("item", "CMS Setup", "Directus provisioning and roles.", "1", "1800.00"),
        ("item", "Next.js Development Day", "Feature work on the storefront.", "3", "1100.00"),
        ("custom", "Launch support week", "On-call support through launch week.", "1", "900.00"),
    ]),
    "INV-2026-311": ("2500.00", [
        ("item", "Hosting Care Plan Monthly", "Monthly hosting, backups, and monitoring.", "1", "450.00"),
        ("item", "Next.js Development Day", "Booking flow improvements.", "1", "1100.00"),
        ("item", "Analytics Setup", "Class booking funnel events.", "1", "950.00"),
    ]),
    "INV-2026-312": ("1200.00", [
        ("item", "Hosting Care Plan Monthly", "Monthly hosting, backups, and monitoring.", "1", "450.00"),
        ("custom", "Managed content updates", "Content edits and page updates, hourly block.", "5", "150.00"),
    ]),
    "INV-2026-313": ("12000.00", [
        ("item", "Next.js Development Day", "Senior developer days on the booking app.", "8", "1100.00"),
        ("item", "CMS Setup", "Class schedule content model and roles.", "1", "1800.00"),
        ("custom", "Sprint planning and PM", "Planning, coordination, and reporting.", "1", "1400.00"),
    ]),
    "INV-2026-314": ("6000.00", [
        ("item", "Discovery Workshop", "Brand positioning workshop.", "1", "1500.00"),
        ("item", "Design Sprint", "Identity concepts and direction review.", "1", "4500.00"),
    ]),
    "INV-2026-315": ("12000.00", [
        ("item", "Design Sprint", "Wholesale portal concept sprint.", "1", "4500.00"),
        ("item", "Next.js Development Day", "Portal feature development.", "5", "1100.00"),
        ("custom", "Accessibility review", "WCAG 2.1 AA review and remediation notes.", "1", "2000.00"),
    ]),
    "INV-2026-316": ("2500.00", [
        ("item", "SEO Audit", "Quarterly technical audit.", "1", "1400.00"),
        ("custom", "Structured data implementation", "Schema.org markup for practice areas.", "1", "1100.00"),
    ]),
}

# Skip-only invoices: verify sums, never add items.
SKIP_ONLY = {"INV-2026-001": ("12000.00", 3), "INV-2026-002": ("500.00", 1)}

# --------------------------------------------------------------------------
# Step 2: NEW invoices INV-2026-317..330.
# --------------------------------------------------------------------------

NEW_INVOICES = [
    # number, project key, org, status, billing_type, interval, issue, due,
    # allow_partial, amount_paid, items[(type, name, desc, qty, unit_price[, expense_key])]
    ("INV-2026-317", "cedar_web", 2, "paid", "one_time", None, "2026-02-10", "2026-02-24", False, "9762.50", [
        ("item", "Design Sprint", "Homepage and menu concept sprint.", "1", "4500.00"),
        ("item", "Next.js Development Day", "Site build developer days.", "4", "1100.00"),
        ("custom", "Responsive QA pass", "Device lab QA and fixes before launch.", "1", "862.50"),
    ]),
    ("INV-2026-318", "cedar_web", 2, "submitted", "one_time", None, "2026-06-26", "2026-07-24", False, "0.00", [
        ("item", "Next.js Development Day", "Post-launch feature work.", "3", "1100.00"),
        ("item", "Analytics Setup", "Campaign goal tracking additions.", "1", "950.00"),
        ("custom", "Content entry support", "Seasonal menu content entry, hourly.", "6.5", "90.00"),
    ]),
    ("INV-2026-319", "cedar_whole", 2, "draft", "one_time", None, "2026-07-10", "2026-08-09", False, "0.00", [
        ("item", "Discovery Workshop", "Wholesale ordering discovery session.", "1", "1500.00"),
        ("item", "CMS Setup", "Wholesale catalog content model.", "1", "1800.00"),
        ("custom", "Wholesale pricing rules spec", "Tier pricing and minimums specification.", "1", "975.25"),
    ]),
    ("INV-2026-320", "north_brand", 3, "paid", "one_time", None, "2026-04-03", "2026-04-17", False, "7218.75", [
        ("item", "Brand System", "Full identity system and guidelines.", "1", "6500.00"),
        ("custom", "Stationery print coordination", "Print vendor coordination and proof review.", "1", "450.00"),
        ("expense", "Billable expense: Brand collateral printing", "Pass-through print cost, Moo Print order.", "1", "268.75", "Brand collateral printing"),
    ]),
    ("INV-2026-321", "north_seo", 3, "paid", "recurring", "month", "2026-06-01", "2026-06-15", False, "1800.00", [
        ("custom", "Monthly SEO retainer", "Ongoing optimization, monitoring, and reporting.", "1", "1450.00"),
        ("custom", "Content briefs", "Keyword-mapped article briefs.", "4", "87.50"),
    ]),
    ("INV-2026-322", "north_seo", 3, "overdue", "recurring", "month", "2026-07-01", "2026-07-08", False, "0.00", [
        ("custom", "Monthly SEO retainer", "Ongoing optimization, monitoring, and reporting.", "1", "1450.00"),
        ("custom", "Content briefs", "Keyword-mapped article briefs.", "4", "87.50"),
    ]),
    ("INV-2026-323", "vellum_port", 4, "paid", "one_time", None, "2026-03-06", "2026-03-20", False, "10237.40", [
        ("item", "CMS Setup", "Portfolio content model and roles.", "1", "1800.00"),
        ("item", "Next.js Development Day", "Platform build developer days.", "5", "1100.00"),
        ("item", "Content Migration", "Case study and media migration.", "2", "850.00"),
        ("custom", "Launch week support", "On-call support and fixes at launch.", "1", "1237.40"),
    ]),
    ("INV-2026-324", "vellum_port", 4, "submitted", "one_time", None, "2026-06-20", "2026-07-20", True, "2000.00", [
        ("item", "Next.js Development Day", "Gallery filtering and CDN image work.", "3", "1100.00"),
        ("custom", "Design retainer hours", "Ongoing design support, hourly.", "10", "95.00"),
        ("expense", "Billable expense: Contract frontend developer", "Pass-through contractor cost, Upwork.", "1", "1250.00", "Contract frontend developer"),
    ]),
    ("INV-2026-325", "harbor_app", 5, "paid", "one_time", None, "2026-02-25", "2026-03-11", False, "13587.50", [
        ("item", "Design Sprint", "Booking flow concept sprint.", "1", "4500.00"),
        ("item", "Next.js Development Day", "App build developer days.", "6", "1100.00"),
        ("item", "CMS Setup", "Class schedule content model.", "1", "1800.00"),
        ("custom", "App store submission support", "Store listing assets and submission.", "1", "687.50"),
    ]),
    ("INV-2026-326", "harbor_app", 5, "submitted", "one_time", None, "2026-07-03", "2026-07-31", False, "0.00", [
        ("item", "Next.js Development Day", "Waitlist and reminders feature work.", "2", "1100.00"),
        ("custom", "Booking flow analytics events", "Funnel event instrumentation.", "1", "730.00"),
        ("expense", "Billable expense: Client onsite airfare", "Pass-through travel for onsite workshop.", "1", "428.60", "Client onsite airfare"),
    ]),
    ("INV-2026-327", "bloom_shop", 6, "paid", "one_time", None, "2026-01-28", "2026-02-11", False, "8191.30", [
        ("item", "Discovery Workshop", "Storefront discovery session.", "1", "1500.00"),
        ("custom", "Shopify theme build", "Custom theme development and setup.", "1", "5200.00"),
        ("item", "Content Migration", "Product catalog migration.", "1", "850.00"),
        ("custom", "Product data import", "Variant and inventory data import.", "1", "641.30"),
    ]),
    ("INV-2026-328", "sterling", 7, "overdue", "one_time", None, "2026-05-15", "2026-06-14", True, "2500.00", [
        ("item", "CMS Setup", "Reservations content model and roles.", "1", "1800.00"),
        ("item", "Next.js Development Day", "Reservations feature development.", "3", "1100.00"),
        ("custom", "Reservations integration spec", "Floor plan and POS integration spec.", "1", "1150.75"),
    ]),
    ("INV-2026-329", "meridian", 8, "approved", "one_time", None, "2026-07-08", "2026-08-07", False, "0.00", [
        ("item", "Discovery Workshop", "Grant portal discovery session.", "1", "1500.00"),
        ("item", "Design Sprint", "Application flow concept sprint.", "1", "4500.00"),
        ("custom", "Grant application data model", "Application, review, and award data model.", "1", "2350.00"),
    ]),
    ("INV-2026-330", "vellum_motion", 4, "draft", "one_time", None, "2026-07-12", "2026-08-11", False, "0.00", [
        ("custom", "Motion reel production deposit", "50 percent production deposit.", "1", "1600.00"),
        ("custom", "Storyboard workshop", "Reel structure and shot list session.", "1", "400.00"),
    ]),
]

# --------------------------------------------------------------------------
# Step 3: payments. Upsert by stripe_payment_id.
# --------------------------------------------------------------------------

EXISTING_INVOICE_IDS = {
    "INV-2026-300": "33ca4bf9-0ecc-49d1-9556-ed2cd56aaa1f",
    "INV-2026-301": "ee49e001-d7e1-480c-974c-e53be2ec1ee6",
    "INV-2026-302": "1a8f5fb7-9891-41a5-8c9f-abb75d30413f",
    "INV-2026-303": "64f0314b-877f-4480-93b5-ad3dad4e801d",
    "INV-2026-304": "dd5fd270-c95b-492e-9571-3dc351584a0a",
    "INV-2026-305": "587b2914-caba-4987-9df6-54890c032d94",
    "INV-2026-306": "adfd63c9-7fe1-4271-89b9-5e46442a03a0",
    "INV-2026-307": "1947e095-58a9-48f8-887c-82f3342303de",
    "INV-2026-308": "013b415d-685f-4029-87d2-76731a41562b",
    "INV-2026-309": "5dce46a1-73e4-47ee-b7ab-646d893baa70",
    "INV-2026-310": "c2ff3f98-519b-40d2-9352-f3d41de59c9c",
    "INV-2026-311": "6fe6e720-1744-47e3-a82d-1ff249d18ca6",
    "INV-2026-312": "a97c8cfd-3b45-497f-8f77-c62de1cdbba0",
    "INV-2026-313": "1ce8bab8-e91b-4c88-9c8e-be99383137c8",
    "INV-2026-314": "b790c73d-0b35-48b2-936c-a1dc05bda639",
    "INV-2026-315": "2a788896-b2b4-4dc0-8c85-8362f5df64de",
    "INV-2026-316": "366a00ec-9857-4e93-b595-17aa074f241b",
}

INVOICE_ORG = {"INV-2026-300": 3, "INV-2026-301": 6, "INV-2026-302": 2,
               "INV-2026-303": 2, "INV-2026-304": 7, "INV-2026-305": 2,
               "INV-2026-306": 2, "INV-2026-307": 6, "INV-2026-308": 7,
               "INV-2026-309": 6, "INV-2026-310": 6, "INV-2026-311": 5,
               "INV-2026-312": 2, "INV-2026-313": 5, "INV-2026-314": 3,
               "INV-2026-315": 2, "INV-2026-316": 3}

PAYMENTS = [
    # (pi id, invoice_number, amount, status, method, payment_date)
    ("pi_demo_0001", "INV-2026-301", "3800.00", "paid", "card", "2026-06-27T15:00:00Z"),
    ("pi_demo_0002", "INV-2026-305", "1200.00", "paid", "card", "2026-07-03T14:30:00Z"),
    ("pi_demo_0003", "INV-2026-306", "1500.00", "paid", "bank_transfer", "2026-06-12T16:00:00Z"),
    ("pi_demo_0004", "INV-2026-310", "6000.00", "paid", "bank_transfer", "2026-06-15T15:45:00Z"),
    ("pi_demo_0005", "INV-2026-312", "1200.00", "paid", "card", "2026-07-11T13:20:00Z"),
    ("pi_demo_0006", "INV-2026-313", "12000.00", "paid", "bank_transfer", "2026-06-20T17:00:00Z"),
    ("pi_demo_0007", "INV-2026-314", "6000.00", "paid", "card", "2026-06-30T14:10:00Z"),
    ("pi_demo_0008", "INV-2026-316", "2500.00", "paid", "other", "2026-06-24T15:30:00Z"),
    ("pi_demo_0009", "INV-2026-317", "9762.50", "paid", "card", "2026-02-20T15:30:00Z"),
    ("pi_demo_0010", "INV-2026-320", "7218.75", "paid", "bank_transfer", "2026-04-14T16:00:00Z"),
    ("pi_demo_0011", "INV-2026-321", "1800.00", "paid", "card", "2026-06-10T14:15:00Z"),
    ("pi_demo_0012", "INV-2026-323", "10237.40", "paid", "bank_transfer", "2026-03-18T17:45:00Z"),
    ("pi_demo_0013", "INV-2026-325", "13587.50", "paid", "card", "2026-03-09T15:00:00Z"),
    ("pi_demo_0014", "INV-2026-327", "8191.30", "paid", "card", "2026-02-09T18:20:00Z"),
    ("pi_demo_0015", "INV-2026-324", "2000.00", "paid", "bank_transfer", "2026-07-02T16:40:00Z"),
    ("pi_demo_0016", "INV-2026-328", "2500.00", "paid", "other", "2026-06-01T15:10:00Z"),
    ("pi_demo_0017", "INV-2026-300", "3800.00", "pending", "bank_transfer", "2026-07-12T15:00:00Z"),
    ("pi_demo_0018", "INV-2026-304", "3800.00", "pending", "card", "2026-07-10T14:00:00Z"),
    ("pi_demo_0019", "INV-2026-307", "4500.00", "pending", "bank_transfer", "2026-07-13T16:30:00Z"),
    ("pi_demo_0020", "INV-2026-308", "2500.00", "pending", "card", "2026-07-14T15:20:00Z"),
    ("pi_demo_0021", "INV-2026-311", "2500.00", "pending", "other", "2026-07-11T17:10:00Z"),
]

# --------------------------------------------------------------------------
# Step 4: expenses. Upsert by (name, date). Deterministic dates.
# --------------------------------------------------------------------------

EXPENSES = [
    # name, vendor, date, category, status, cost, billing_term, recur, next_bill,
    # billable project key or None, receipt vendor key or None, description,
    # items[(name, qty, amount, notes)]
    ("Figma Organization seats", "Figma", "2026-06-10", "software", "paid", "675.00",
     "recurring", "monthly", "2026-07-20", None, "Figma",
     "Design tool seats for the whole studio.",
     [("Organization seat", "15", "45.00", None)]),
    ("AWS hosting June", "AWS", "2026-06-30", "utilities", "paid", "214.37",
     "recurring", "monthly", "2026-07-31", None, "AWS",
     "Monthly AWS bill for client staging and internal tools.",
     [("EC2 and RDS usage", "1", "168.12", None), ("S3 and data transfer", "1", "46.25", None)]),
    ("Linear workspace", "Linear", "2026-05-12", "software", "paid", "93.50",
     "recurring", "monthly", "2026-08-01", None, "Linear",
     "Issue tracking for delivery teams.",
     [("Standard seat", "11", "8.50", None)]),
    ("Client onsite rail travel", "Amtrak", "2026-04-22", "travel", "paid", "187.50",
     "one_time", None, None, "north_brand", "Amtrak",
     "Round trip for the Northlight brand workshop.",
     [("Acela round trip", "1", "152.00", None), ("Seat upgrade", "1", "35.50", None)]),
    ("Brand collateral printing", "Moo Print", "2026-03-18", "marketing", "approved", "268.75",
     "one_time", None, None, "north_brand", "Moo Print",
     "Business cards and letterhead for the Northlight identity rollout.",
     [("Business cards pack", "5", "32.75", None), ("Letterhead", "1", "105.00", None)]),
    ("Adobe Creative Cloud teams", "Adobe Creative Cloud", "2026-05-28", "software", "paid", "359.88",
     "recurring", "monthly", "2026-07-28", None, "Adobe Creative Cloud",
     "All-apps licenses for the design team.",
     [("All apps license", "3", "119.96", None)]),
    ("Notion team plan", "Notion", "2026-07-08", "software", "paid", "144.00",
     "recurring", "monthly", "2026-08-04", None, "Notion",
     "Internal docs and client-facing wikis.",
     [("Business seat", "8", "18.00", None)]),
    ("Shipping and packing supplies", "Uline", "2026-02-11", "office_supplies", "paid", "224.60",
     "one_time", None, None, None, "Uline",
     "Mailers and packing supplies for client deliverable shipments.",
     [("Mailer boxes", "2", "58.30", None), ("Packing tape case", "1", "43.00", None),
      ("Label rolls", "1", "65.00", None)]),
    ("Google Workspace seats top-up", "Google Workspace", "2026-07-01", "software", "paid", "86.40",
     "one_time", None, None, None, None,
     "Two additional Business Standard seats, prorated.",
     [("Business Standard seat", "6", "14.40", None)]),
    ("Zoom webinar add-on", "Zoom", "2026-06-16", "software", "approved", "79.00",
     "one_time", None, None, None, None,
     "Webinar add-on for the client training series.",
     [("Webinar 500 add-on", "1", "79.00", None)]),
    ("Mailchimp campaign credits", "Mailchimp", "2026-05-06", "marketing", "paid", "120.50",
     "one_time", None, None, None, None,
     "Send credits for the agency newsletter.",
     [("Campaign credits", "1", "120.50", None)]),
    ("Office paper and toner", "Office Depot", "2026-06-24", "office_supplies", "approved", "143.22",
     "one_time", None, None, None, None,
     "Printer consumables for the studio.",
     [("Copy paper cases", "2", "45.99", None), ("Toner cartridge", "1", "51.24", None)]),
    ("Client onsite airfare", "Delta", "2026-05-20", "travel", "approved", "428.60",
     "one_time", None, None, "harbor_app", None,
     "Flight for the Harbor Fitness onsite booking workshop.",
     [("Round trip airfare", "1", "398.60", None), ("Seat selection", "1", "30.00", None)]),
    ("Contract frontend developer", "Upwork", "2026-06-05", "outsourced", "approved", "1250.00",
     "one_time", None, None, "vellum_port", None,
     "Contract sprint on the Vellum portfolio gallery.",
     [("Frontend sprint hours", "25", "50.00", None)]),
    ("Client tasting lunch", "Blue Bottle", "2026-07-09", "meals", "submitted", "96.40",
     "one_time", None, None, "sterling", None,
     "Working lunch with the Sterling and Vine team.",
     [("Team lunch", "4", "24.10", None)]),
    ("Dual monitor for design desk", "CDW", "2026-04-15", "hardware", "paid", "389.99",
     "one_time", None, None, None, None,
     "27 inch 4K monitor for the design workstation.",
     [("27in 4K monitor", "1", "389.99", None)]),
    ("Contract review retainer", "LegalZoom", "2026-03-25", "professional_services", "paid", "350.00",
     "one_time", None, None, None, None,
     "MSA template review and updates.",
     [("MSA template review", "1", "350.00", None)]),
    ("Office internet and phone", "Verizon", "2026-07-14", "utilities", "draft", "210.15",
     "one_time", None, None, None, None,
     "Studio fiber internet and business line, July.",
     [("Fiber internet", "1", "149.00", None), ("Business line", "1", "61.15", None)]),
]

# Step 6: billed-to-invoice: expense name -> new invoice number.
BILLED_EXPENSES = {
    "Brand collateral printing": "INV-2026-320",
    "Contract frontend developer": "INV-2026-324",
    "Client onsite airfare": "INV-2026-326",
}

# --------------------------------------------------------------------------
# Step 8: subscriptions. Upsert by (organization, name).
# --------------------------------------------------------------------------

ORG_EMAIL = {2: "billing@cedarandco.com", 3: "billing@northlightlaw.com",
             4: "billing@vellum.studio", 5: "billing@harborfitness.co",
             6: "billing@bloombotanicals.com", 7: "billing@sterlingandvine.com",
             8: "billing@meridianfund.org"}

SUBSCRIPTIONS = [
    # org, name, vendor, website, category, cycle, cost, start, renewal, status, auto_renew, notes, projects[]
    (2, "Netlify Pro hosting", "Netlify", "https://netlify.com", "INFRASTRUCTURE", "MONTHLY",
     "19.00", "2025-09-01", "2026-08-01", "active", True,
     "Production hosting for the marketing site.", ["cedar_web"]),
    (2, "cedarandco.com domain", "Namecheap", "https://namecheap.com", "OTHER", "YEARLY",
     "15.98", "2023-08-10", "2026-08-10", "active", True,
     "Primary domain renewal.", ["cedar_web"]),
    (2, "Klaviyo email marketing", "Klaviyo", "https://klaviyo.com", "MARKETING", "MONTHLY",
     "145.00", "2026-01-05", "2026-08-05", "active", True,
     "Email flows for retail and wholesale lists.", ["cedar_whole"]),
    (3, "Northlight site hosting", "Netlify", "https://netlify.com", "INFRASTRUCTURE", "MONTHLY",
     "19.00", "2025-11-15", "2026-08-09", "active", True,
     "Hosting for the firm site.", ["north_brand", "north_seo"]),
    (3, "Semrush SEO toolkit", "Semrush", "https://semrush.com", "ANALYTICS", "MONTHLY",
     "129.95", "2026-02-12", "2026-08-12", "active", True,
     "Rank tracking and audits for the SEO retainer.", ["north_seo"]),
    (4, "Vellum portfolio hosting", "Vercel", "https://vercel.com", "INFRASTRUCTURE", "MONTHLY",
     "25.00", "2026-03-03", "2026-08-03", "active", True,
     "Hosting for the portfolio platform.", ["vellum_port"]),
    (4, "Vimeo Pro", "Vimeo", "https://vimeo.com", "DESIGN", "MONTHLY",
     "20.00", "2025-07-29", "2026-07-29", "expiring", False,
     "Video hosting for motion work. Client is deciding on renewal.", ["vellum_motion"]),
    (5, "Harbor booking app hosting", "AWS", "https://aws.amazon.com", "INFRASTRUCTURE", "MONTHLY",
     "45.00", "2026-01-06", "2026-08-06", "active", True,
     "App servers and database for the booking app.", ["harbor_app"]),
    (5, "Twilio SMS notifications", "Twilio", "https://twilio.com", "COMMUNICATION", "MONTHLY",
     "62.30", "2026-02-08", "2026-08-08", "active", True,
     "Class reminder texts.", ["harbor_app"]),
    (5, "harborfitness.co domain", "Namecheap", "https://namecheap.com", "OTHER", "YEARLY",
     "32.98", "2024-11-12", "2026-11-12", "active", True,
     "Primary domain renewal.", ["harbor_app"]),
    (6, "Shopify plan", "Shopify", "https://shopify.com", "INFRASTRUCTURE", "MONTHLY",
     "79.00", "2025-08-02", "2026-08-02", "active", True,
     "Storefront platform plan.", ["bloom_shop"]),
    (6, "Judge.me product reviews", "Judge.me", "https://judge.me", "MARKETING", "MONTHLY",
     "15.00", "2025-10-11", "2026-08-11", "active", True,
     "Product review widget.", ["bloom_shop"]),
    (7, "Reservations platform hosting", "DigitalOcean", "https://digitalocean.com", "INFRASTRUCTURE", "MONTHLY",
     "39.00", "2025-12-07", "2026-08-07", "active", True,
     "Droplets for the reservations system.", ["sterling"]),
    (7, "OpenTable connector", "OpenTable", "https://opentable.com", "PRODUCTIVITY", "QUARTERLY",
     "149.00", "2026-02-01", "2026-08-01", "expiring", False,
     "Availability sync connector. Renewal under review.", ["sterling"]),
    (8, "Grant portal hosting", "AWS", "https://aws.amazon.com", "INFRASTRUCTURE", "MONTHLY",
     "49.00", "2026-02-05", "2026-08-05", "active", True,
     "Portal application servers.", ["meridian"]),
    (8, "Matomo Cloud analytics", "Matomo", "https://matomo.org", "ANALYTICS", "YEARLY",
     "228.00", "2025-08-20", "2026-08-20", "active", True,
     "Privacy-friendly analytics for the portal.", ["meridian"]),
]

# Gated step 7 mapping (org-consistent project per existing invoice).
NULLFILL_MAP = {
    "INV-2026-300": "north_brand", "INV-2026-301": "bloom_shop",
    "INV-2026-302": "cedar_web", "INV-2026-303": "cedar_whole",
    "INV-2026-304": "sterling", "INV-2026-305": "cedar_web",
    "INV-2026-306": "cedar_web", "INV-2026-307": "bloom_shop",
    "INV-2026-308": "sterling", "INV-2026-309": "bloom_shop",
    "INV-2026-310": "bloom_shop", "INV-2026-311": "harbor_app",
    "INV-2026-312": "cedar_web", "INV-2026-313": "harbor_app",
    "INV-2026-314": "north_brand", "INV-2026-315": "cedar_web",
    "INV-2026-316": "north_seo",
}


def plan_total(items):
    return sum(D(q) * D(p) for (_t, _n, _d, q, p, *_rest) in items)


def sanity_check_plan():
    ok = True
    for num, (total, items) in EXISTING_ITEMS.items():
        if plan_total(items) != D(total):
            print(f"PLAN FAIL {num}: items sum {plan_total(items)} != {total}")
            ok = False
    for inv in NEW_INVOICES:
        num, items = inv[0], inv[10]
        # amount_paid must equal sum of that invoice's paid payments
        paid = sum(D(p[2]) for p in PAYMENTS if p[1] == num and p[3] == "paid")
        if D(inv[9]) != paid:
            print(f"PLAN FAIL {num}: amount_paid {inv[9]} != paid payments {paid}")
            ok = False
    for exp in EXPENSES:
        name, cost, items = exp[0], exp[5], exp[12]
        s = sum(D(q) * D(a) for (_n, q, a, _notes) in items)
        if s != D(cost):
            print(f"PLAN FAIL expense {name}: items {s} != cost {cost}")
            ok = False
    if not ok:
        sys.exit(1)


def money(d):
    return f"{D(d):.2f}"


def seed_existing_invoice_items(os_items_by_name):
    c = {"created": 0, "updated": 0, "skipped": 0}
    ledger_fail = []
    # Skip-only invoices: verify and never touch.
    for num, (total, n_items) in SKIP_ONLY.items():
        inv = get_items("os_invoices", {"invoice_number": {"_eq": num}})[0]
        rows = get_items("os_invoice_items", {"invoice": {"_eq": inv["id"]}})
        s = sum(D(r["line_amount"]) for r in rows)
        status = "OK" if (s == D(total) and len(rows) == n_items) else "MISMATCH"
        print(f"skip-only {num}: {len(rows)} items sum {s} vs total {total} -> {status}")
        if status == "MISMATCH":
            ledger_fail.append(num)
    for num, (total, items) in EXISTING_ITEMS.items():
        inv = get_items("os_invoices", {"invoice_number": {"_eq": num}})[0]
        stored_total = D(inv["total"])
        stored_sub = D(inv["subtotal"])
        if stored_total != D(total) or stored_sub != D(total):
            print(f"LEDGER SKIP {num}: stored subtotal/total {stored_sub}/{stored_total} != planned {total}; not writing")
            ledger_fail.append(num)
            continue
        for n, (typ, name, desc, qty, price) in enumerate(items, start=1):
            la = money(D(qty) * D(price))
            payload = {
                "invoice": inv["id"], "item_name": name, "description": desc,
                "line_item_number": n, "quantity": money(qty),
                "unit_price": money(price), "line_amount": la,
                "tax_amount": "0.00", "tax_rate": "0.00", "type": typ,
                "override_unit_price": typ != "item",
                "item": os_items_by_name.get(name) if typ == "item" else None,
                **FLAG,
            }
            upsert("os_invoice_items",
                   {"invoice": {"_eq": inv["id"]}, "item_name": {"_eq": name}},
                   payload, c)
        # post-check: all items on this invoice must sum to stored total
        rows = get_items("os_invoice_items", {"invoice": {"_eq": inv["id"]}})
        s = sum(D(r["line_amount"]) for r in rows)
        if s != stored_total:
            print(f"LEDGER FAIL {num}: items now sum {s} != stored total {stored_total}")
            ledger_fail.append(num)
    report("os_invoice_items(existing invoices)", c)
    return ledger_fail


def seed_expenses(expense_ids):
    c = {"created": 0, "updated": 0, "skipped": 0}
    ci = {"created": 0, "updated": 0, "skipped": 0}
    for exp in EXPENSES:
        (name, vendor, date, cat, status, cost, term, recur, next_bill,
         proj_key, receipt_key, desc, items) = exp
        payload = {
            "name": name, "vendor": vendor, "date": date + "T12:00:00Z",
            "category": cat, "status": status, "cost": money(cost),
            "billing_term": term, "description": desc,
            "is_billable": proj_key is not None,
            "is_reimbursable": name == "Client tasting lunch",
            "project": PROJ[proj_key] if proj_key else None,
            "file": RECEIPTS[receipt_key] if receipt_key else None,
            **FLAG,
        }
        if term == "recurring":
            payload.update({"recurrence_interval": recur,
                            "next_billing_date": next_bill,
                            "notify_on_renewal": True,
                            "notify_days_before": 7})
        # upsert by (name, date): filter by name, match date prefix client-side
        rows = [r for r in get_items("os_expenses", {"name": {"_eq": name}})
                if str(r.get("date", ""))[:10] == date]
        if not rows:
            st, body = req("POST", "/items/os_expenses", payload)
            if st not in (200, 201):
                print(f"FATAL create os_expenses {name}: {st} {body}")
                sys.exit(1)
            eid = body["data"]["id"]
            c["created"] += 1
        else:
            eid = rows[0]["id"]
            diff = {k: payload[k] for k in payload
                    if k != "date" and norm(rows[0].get(k)) != norm(payload[k])}
            if diff:
                req("PATCH", f"/items/os_expenses/{eid}", diff)
                c["updated"] += 1
            else:
                c["skipped"] += 1
        expense_ids[name] = eid
        for (iname, qty, amount, notes) in items:
            ipayload = {"expense": eid, "name": iname, "quantity": money(qty),
                        "amount": money(amount), "notes": notes, **FLAG}
            upsert("os_expense_items",
                   {"expense": {"_eq": eid}, "name": {"_eq": iname}},
                   ipayload, ci)
    report("os_expenses", c)
    report("os_expense_items", ci)


def seed_new_invoices(expense_ids, os_items_by_name, invoice_ids):
    c = {"created": 0, "updated": 0, "skipped": 0}
    ci = {"created": 0, "updated": 0, "skipped": 0}
    for inv in NEW_INVOICES:
        (num, proj_key, org, status, btype, interval, issue, due,
         partial, amount_paid, items) = inv
        total = plan_total(items)
        payload = {
            "invoice_number": num, "status": status,
            "organization": org, "project": PROJ[proj_key],
            "contact": PRIMARY_CONTACT[org],
            "billing_type": btype, "billing_interval": interval,
            "issue_date": issue + "T00:00:00Z", "due_date": due + "T00:00:00Z",
            "subtotal": money(total), "total": money(total), "total_tax": "0.00",
            "amount_paid": money(amount_paid),
            "amount_due": money(total - D(amount_paid)),
            "allow_partial_payments": partial,
            **FLAG,
        }
        iid = upsert("os_invoices", {"invoice_number": {"_eq": num}}, payload, c)
        invoice_ids[num] = iid
        for n, it in enumerate(items, start=1):
            typ, name, desc, qty, price = it[0], it[1], it[2], it[3], it[4]
            la = money(D(qty) * D(price))
            ipayload = {
                "invoice": iid, "item_name": name, "description": desc,
                "line_item_number": n, "quantity": money(qty),
                "unit_price": money(price), "line_amount": la,
                "tax_amount": "0.00", "tax_rate": "0.00", "type": typ,
                "override_unit_price": typ != "item",
                "item": os_items_by_name.get(name) if typ == "item" else None,
                **FLAG,
            }
            if typ == "expense":
                ipayload["billable_expense"] = expense_ids[it[5]]
            item_id = upsert("os_invoice_items",
                             {"invoice": {"_eq": iid}, "item_name": {"_eq": name}},
                             ipayload, ci)
            if typ == "expense":
                # step 6: point the expense back at its invoice line
                exp_id = expense_ids[it[5]]
                row = get_items("os_expenses", {"id": {"_eq": exp_id}})[0]
                if row.get("invoice_item") != item_id:
                    req("PATCH", f"/items/os_expenses/{exp_id}",
                        {"invoice_item": item_id})
                    print(f"linked expense '{it[5]}' -> invoice item on {num}")
    report("os_invoices(new)", c)
    report("os_invoice_items(new invoices)", ci)


def seed_payments(invoice_ids):
    c = {"created": 0, "updated": 0, "skipped": 0}
    all_ids = dict(EXISTING_INVOICE_IDS)
    all_ids.update(invoice_ids)
    new_orgs = {inv[0]: inv[2] for inv in NEW_INVOICES}
    for (pi, num, amount, status, method, pdate) in PAYMENTS:
        org = INVOICE_ORG.get(num) or new_orgs[num]
        payload = {
            "stripe_payment_id": pi, "invoice": all_ids[num],
            "amount": money(amount), "status": status,
            "payment_method_type": method, "payment_date": pdate,
            "organization": org, "contact": PRIMARY_CONTACT[org],
            **FLAG,
        }
        upsert("os_payments", {"stripe_payment_id": {"_eq": pi}}, payload, c)
    report("os_payments", c)


def seed_subscriptions():
    c = {"created": 0, "updated": 0, "skipped": 0}
    cj = {"created": 0, "updated": 0, "skipped": 0}
    for sub in SUBSCRIPTIONS:
        (org, name, vendor, website, cat, cycle, cost, start, renewal,
         status, auto, notes, projects) = sub
        payload = {
            "organization": org, "name": name, "vendor": vendor,
            "website": website, "category": cat, "billing_cycle": cycle,
            "cost": money(cost), "start_date": start, "renewal_date": renewal,
            "status": status, "auto_renew": auto, "notes": notes,
            "account_email": ORG_EMAIL[org], **FLAG,
        }
        sid = upsert("os_subscriptions",
                     {"organization": {"_eq": org}, "name": {"_eq": name}},
                     payload, c)
        for pk in projects:
            jpayload = {"subscription_id": sid, "project_id": PROJ[pk]}
            upsert("os_project_subscriptions",
                   {"subscription_id": {"_eq": sid}, "project_id": {"_eq": PROJ[pk]}},
                   jpayload, cj)
    report("os_subscriptions", c)
    report("os_project_subscriptions", cj)


def gated_nullfill():
    if os.environ.get("NULLFILL_APPROVED") != "1":
        print("GATED step 7 (null-fill project/contact on INV-2026-300..316): "
              "SKIPPED, NULLFILL_APPROVED token not present. The 17 existing "
              "invoice detail pages keep blank Contact/Project rows; the 14 "
              "new invoices carry full linkage.")
        return
    c = {"created": 0, "updated": 0, "skipped": 0}
    for num, proj_key in NULLFILL_MAP.items():
        inv = get_items("os_invoices", {"invoice_number": {"_eq": num}})[0]
        org = INVOICE_ORG[num]
        diff = {}
        if inv.get("project") is None:
            diff["project"] = PROJ[proj_key]
        if inv.get("contact") is None:
            diff["contact"] = PRIMARY_CONTACT[org]
        if diff:
            req("PATCH", f"/items/os_invoices/{inv['id']}", diff)
            c["updated"] += 1
        else:
            c["skipped"] += 1
    report("os_invoices(null-fill project/contact ONLY)", c)


# --------------------------------------------------------------------------
# Verify
# --------------------------------------------------------------------------

def gql(query, token=TOKEN):
    st, body = req("POST", "/graphql", {"query": query}, token=token)
    return st, body


def verify():
    print("\n===== VERIFY =====")
    failures = []

    # Arithmetic check per NEW invoice
    for inv in NEW_INVOICES:
        num = inv[0]
        row = get_items("os_invoices", {"invoice_number": {"_eq": num}})[0]
        items = get_items("os_invoice_items", {"invoice": {"_eq": row["id"]}})
        pays = get_items("os_payments", {"invoice": {"_eq": row["id"]}})
        s_items = sum(D(r["line_amount"]) for r in items)
        s_paid = sum(D(r["amount"]) for r in pays if r["status"] == "paid")
        sub, tot = D(row["subtotal"]), D(row["total"])
        ap, ad = D(row["amount_paid"]), D(row["amount_due"])
        ok = (s_items == sub == tot) and (s_paid == ap) and (ad == tot - ap)
        print(f"ARITH {num}: items={s_items} subtotal={sub} total={tot} "
              f"paid_payments={s_paid} amount_paid={ap} amount_due={ad} "
              f"-> {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(num)

    # GraphQL probe 1: invoices with line items, payments, org, project, contact
    q1 = """query { os_invoices(limit:3, sort:["-issue_date"]) { id invoice_number status total amount_due amount_paid
      line_items { id item_name type quantity unit_price line_amount }
      payments { id amount payment_date status }
      organization { id name } project { id name }
      contact { id first_name last_name } } }"""
    st, body = gql(q1)
    errs = (body or {}).get("errors")
    rows = ((body or {}).get("data") or {}).get("os_invoices") or []
    print(f"GQL invoices probe: HTTP {st}, errors={errs}, rows={len(rows)}")
    for r in rows:
        li = r.get("line_items") or []
        print(f"  {r['invoice_number']}: {len(li)} line items, "
              f"project={'set' if r.get('project') else 'NULL'}, "
              f"contact={'set' if r.get('contact') else 'NULL'}")
        if not li:
            failures.append(f"{r['invoice_number']}-no-items")
        if r["invoice_number"] >= "INV-2026-317" and (not r.get("project") or not r.get("contact")):
            failures.append(f"{r['invoice_number']}-missing-linkage")
    if errs or st != 200:
        failures.append("gql-invoices")

    # REST count: invoices with project set >= 16
    st, body = req("GET", "/items/os_invoices",
                   params={"filter": json.dumps({"project": {"_nnull": True}}),
                           "aggregate[count]": "id"})
    cnt = None
    if st == 200:
        agg = body["data"][0]["count"]
        cnt = int(agg["id"] if isinstance(agg, dict) else agg)
    print(f"invoices with project set: {cnt} (need >= 16)")
    if not cnt or cnt < 16:
        failures.append("project-count")

    # GraphQL probe 2: payments
    q2 = """query { os_payments(limit:5, sort:["-payment_date"]) { id amount payment_date status
      payment_method_type stripe_payment_id invoice { id invoice_number status }
      organization { id name service_status } } }"""
    st, body = gql(q2)
    errs = (body or {}).get("errors")
    rows = ((body or {}).get("data") or {}).get("os_payments") or []
    print(f"GQL payments probe: HTTP {st}, errors={errs}, rows={len(rows)}")
    if errs or st != 200 or not rows:
        failures.append("gql-payments")

    # GraphQL probe 3: expenses (fail-loud route)
    q3 = """query { os_expenses(limit:5, sort:["-date"]) { id name cost date category status vendor
      billing_term recurrence_interval next_billing_date is_billable
      project { id name } items { id name quantity amount }
      invoice_item { id invoice { id invoice_number } }
      file { id filename_download } } }"""
    st, body = gql(q3)
    errs = (body or {}).get("errors")
    rows = ((body or {}).get("data") or {}).get("os_expenses") or []
    print(f"GQL expenses probe: HTTP {st}, errors={errs}, rows={len(rows)}")
    if errs or st != 200 or not rows:
        failures.append("gql-expenses")

    # Demo session probe: os_expense_items must return 200
    st, body = req("POST", "/auth/login",
                   {"email": "demo@muster.dev", "password": "muster-demo"},
                   token=None)
    if st != 200:
        print(f"demo login FAILED: {st}")
        failures.append("demo-login")
    else:
        demo_token = body["data"]["access_token"]
        for coll in ["os_expense_items", "os_expenses", "os_payments",
                     "os_invoice_items", "os_subscriptions",
                     "os_project_subscriptions"]:
            st2, _ = req("GET", f"/items/{coll}", params={"limit": 1},
                         token=demo_token)
            print(f"demo-session GET /items/{coll}?limit=1 -> {st2}")
            if coll == "os_expense_items" and st2 != 200:
                failures.append("demo-expense-items")

    print(f"HIGHEST_INVOICE_NUMBER=INV-2026-330")
    print(f"VERIFY RESULT: {'PASS' if not failures else 'FAIL ' + str(failures)}")
    return failures


def main():
    sanity_check_plan()
    os_items_by_name = {r["name"]: r["id"] for r in get_items("os_items", limit=100)}
    print(f"os_items rate card loaded: {len(os_items_by_name)} rows")

    ledger_fail = seed_existing_invoice_items(os_items_by_name)
    expense_ids = {}
    seed_expenses(expense_ids)
    invoice_ids = {}
    seed_new_invoices(expense_ids, os_items_by_name, invoice_ids)
    seed_payments(invoice_ids)
    seed_subscriptions()
    gated_nullfill()
    if ledger_fail:
        print(f"LEDGER WARNINGS on: {ledger_fail}")

    if "--verify" in sys.argv or True:
        failures = verify()
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
