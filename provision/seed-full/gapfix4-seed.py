#!/usr/bin/env python3
"""Gap-fix seed for the four failed client-portal sections: tasks, invoices,
products, analytics. Add-only, idempotent (upsert by natural key), every row
is_test_data false. Fill-null-only PATCHes on existing synthetic rows; org 1
(the real Muster history) is never touched.

Sections covered:
  A. permissions  - read-only grant on directus_comments for the demo policy
  B. os_tasks     - top up org-2 client-visible tasks to ~30, fill null
                    due_date/assigned_to on existing synthetic org-2 tasks
  C. task extras  - directus_comments, os_task_files, os_activity_log
  D. os_invoices  - items for zero-item invoices, contact/project fill-null
                    (orgs 2..8 only), os_payments for paid invoices missing one
  E. os_products  - retainer project + 2 new org-2 products, maintained_by fill
Analytics needs no new rows (analytics_snapshots + os_seo_snapshots already
seeded fresh by an earlier wave; verified separately).
"""
import json, os, urllib.request, urllib.parse

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

def req(path, method="GET", body=None):
    r = urllib.request.Request(
        BASE + path, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

def die_on(st, data, ctx):
    if st >= 300:
        raise SystemExit(f"FATAL {ctx}: HTTP {st} {json.dumps(data)[:300]}")

def upsert(collection, natural_filter, payload):
    """Search by natural key; create if absent. Returns (id, created_bool)."""
    q = "&".join(f"filter[{k}][_eq]={urllib.parse.quote(str(v))}" for k, v in natural_filter.items())
    st, d = req(f"/items/{collection}?{q}&fields=id&limit=1")
    die_on(st, d, f"lookup {collection}")
    if d.get("data"):
        return d["data"][0]["id"], False
    st, d = req(f"/items/{collection}", "POST", payload)
    die_on(st, d, f"create {collection}")
    return d["data"]["id"], True

DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
ORG = 2
EMP_USER = "257a4b75-deff-476d-953d-1898c57f6684"  # demo@muster.dev (Employee)

# ── A. directus_comments read grant ─────────────────────────────────────────
st, d = req(f"/permissions?filter[policy][_eq]={DEMO_POLICY}"
            "&filter[collection][_eq]=directus_comments&filter[action][_eq]=read&fields=id")
die_on(st, d, "list comment perms")
if d.get("data"):
    print("permissions: directus_comments read exists")
else:
    st, d = req("/permissions", "POST", {
        "policy": DEMO_POLICY, "collection": "directus_comments",
        "action": "read", "fields": ["*"], "permissions": {}, "validation": {}})
    die_on(st, d, "grant directus_comments read")
    print("permissions: directus_comments read GRANTED")

# ── live context ─────────────────────────────────────────────────────────────
st, d = req(f"/items/os_projects?filter[organization][_eq]={ORG}&fields=id,name,kind,status&limit=-1")
die_on(st, d, "org2 projects")
projs = {p["name"]: p["id"] for p in d["data"]}
P_WEB = projs.get("Cedar & Co — Website Redesign")
P_WHOLESALE = projs.get("Cedar & Co — Wholesale Portal")
P_MENU = projs.get("Cedar & Co - Spring Menu Launch")
P_LOYALTY = projs.get("Cedar & Co - Loyalty Card Microsite")
if not all([P_WEB, P_WHOLESALE, P_MENU, P_LOYALTY]):
    raise SystemExit(f"FATAL missing org2 projects: {sorted(projs)}")

# ── B. os_tasks top-up ───────────────────────────────────────────────────────
# fill-null due_date/assigned_to on existing synthetic org-2 client tasks
st, d = req(f"/items/os_tasks?filter[project][organization][_eq]={ORG}"
            "&filter[is_visible_to_client][_eq]=true"
            "&fields=id,name,status,due_date,date_completed,assigned_to,project&limit=-1")
die_on(st, d, "org2 tasks")
existing = d["data"]
fill_due = {"completed": None}
filled_due = filled_asg = 0
DUE_FILLS = ["2026-07-23", "2026-07-31", "2026-08-07", "2026-07-19"]
for t in existing:
    patch = {}
    if not t.get("due_date") and t.get("status") != "completed":
        patch["due_date"] = DUE_FILLS[filled_due % len(DUE_FILLS)]
    if not t.get("assigned_to"):
        patch["assigned_to"] = EMP_USER
    if patch:
        st, d2 = req(f"/items/os_tasks/{t['id']}", "PATCH", patch)
        die_on(st, d2, f"fill task {t['name']}")
        filled_due += 1 if "due_date" in patch else 0
        filled_asg += 1 if "assigned_to" in patch else 0
print(f"os_tasks fill-null: due_date {filled_due} / assigned_to {filled_asg}")

NEW_TASKS = [
    # (project, name, status, prio, type, due, completed, points, hours, resp, desc)
    (P_WEB, "Migrate blog content to the new CMS", "in_progress", "P2", "task",
     "2026-07-24", None, 5, 10, "team",
     "Move the 38 legacy blog posts into the new CMS.\n\n- Preserve slugs and publish dates\n- Re-crop cover images to the new 3:2 ratio"),
    (P_WEB, "Set up recipe collection landing page", "pending", "P2", "deliverable",
     "2026-08-06", None, 3, 6, "team",
     "New landing page grouping brew guides and recipes by roast. Uses the collection template from the redesign."),
    (P_WEB, "Accessibility pass on checkout flow", "in_review", "P1", "task",
     "2026-07-18", None, 3, 5, "team",
     "WCAG 2.1 AA sweep of cart and checkout: focus order, labels, error announcements, contrast on the summary panel."),
    (P_WEB, "Compress hero imagery for mobile", "completed", "P2", "task",
     "2026-07-06", "2026-07-08", 2, 3, "team",
     "Hero images now ship as AVIF with JPEG fallback. Largest Contentful Paint on 4G dropped from 4.1s to 2.3s."),
    (P_WEB, "Configure store hours schema markup", "completed", "P3", "task",
     "2026-06-26", "2026-06-27", 1, 2, "team",
     "Added OpeningHoursSpecification JSON-LD for both cafe locations. Validated in the Rich Results test."),
    (P_WEB, "QA subscription signup form", "active", "P1", "task",
     "2026-07-21", None, 2, 4, "both",
     "Full pass on the coffee subscription signup: plan switching, gift flow, failed-card retry, confirmation emails."),
    (P_WEB, "Draft FAQ page copy", "pending", "P3", "task",
     "2026-08-12", None, 2, 4, "client",
     "Cedar team to supply first-draft answers for shipping, returns, and wholesale questions. We edit and publish."),
    (P_WHOLESALE, "Wholesale price list import", "in_progress", "P1", "task",
     "2026-07-22", None, 5, 8, "team",
     "Import the current wholesale price book (214 SKUs) and wire the tier columns to the account pricing rules."),
    (P_WHOLESALE, "Net-30 terms application form", "in_review", "P2", "deliverable",
     "2026-07-19", None, 3, 6, "team",
     "Credit application with references, resale certificate upload, and an approval queue for the Cedar finance inbox."),
    (P_WHOLESALE, "Bulk order CSV upload validation", "active", "P0", "task",
     "2026-07-17", None, 5, 9, "team",
     "Server-side validation for the bulk order upload: SKU existence, case-pack multiples, clear row-level error report."),
    (P_WHOLESALE, "Wholesale onboarding email sequence", "pending", "P2", "task",
     "2026-08-03", None, 3, 5, "both",
     "Four-email onboarding sequence for approved wholesale accounts: welcome, ordering guide, freshness calendar, rep intro."),
    (P_WHOLESALE, "Roaster availability calendar", "completed", "P2", "deliverable",
     "2026-07-01", "2026-07-02", 3, 6, "team",
     "Public roast-schedule calendar so wholesale buyers can time orders to roast days. Syncs from the production sheet."),
    (P_WHOLESALE, "Tiered discount rules engine", "in_progress", "P1", "task",
     "2026-07-30", None, 8, 14, "team",
     "Volume discount tiers (5/10/15 percent) applied at cart level with account-specific overrides."),
    (P_MENU, "Spring menu photography retouching", "completed", "P2", "task",
     "2026-04-12", "2026-04-14", 2, 4, "team",
     "Color-corrected the 22 selects from the spring shoot and exported web and print masters."),
    (P_MENU, "Menu PDF export for print vendor", "completed", "P3", "deliverable",
     "2026-04-20", "2026-04-21", 1, 2, "team",
     "Print-ready PDF/X-1a export of the spring menu with bleed and crop marks for the vendor."),
    (P_LOYALTY, "Loyalty points balance widget", "in_review", "P1", "task",
     "2026-07-20", None, 3, 6, "team",
     "Signed-in members see their points balance and next reward threshold on the microsite header."),
    (P_LOYALTY, "Apple Wallet pass integration", "pending", "P1", "task",
     "2026-08-14", None, 8, 16, "team",
     "Generate a Wallet pass per member with the loyalty QR code. Push updates when the balance changes."),
    (P_LOYALTY, "Referral bonus tracking", "active", "P2", "task",
     "2026-07-28", None, 5, 8, "team",
     "Unique referral links per member; both sides earn 200 points on the referred member's first order."),
]
created = skipped = 0
task_ids = {}
for (proj, name, status, prio, ttype, due, comp, pts, hrs, resp, desc) in NEW_TASKS:
    payload = {
        "name": name, "status": status, "priority": prio, "type": ttype,
        "project": proj, "due_date": due, "date_completed": comp,
        "assigned_to": EMP_USER, "is_visible_to_client": True,
        "is_test_data": False, "responsibility": resp,
        "points": pts, "hours_estimate": hrs, "description": desc,
    }
    tid, was = upsert("os_tasks", {"name": name, "project": proj}, payload)
    task_ids[name] = tid
    created += was
    skipped += (not was)
print(f"os_tasks: created {created} / skipped {skipped}")

# map ALL org-2 client tasks by name for extras
st, d = req(f"/items/os_tasks?filter[project][organization][_eq]={ORG}"
            "&filter[is_visible_to_client][_eq]=true&fields=id,name,project,status&limit=-1")
die_on(st, d, "org2 tasks reload")
by_name = {t["name"]: t for t in d["data"]}
print(f"os_tasks org2 client-visible now: {len(by_name)}")

# ── C1. comments ─────────────────────────────────────────────────────────────
COMMENTS = [
    ("Migrate blog content to the new CMS", "24 of 38 posts migrated. Two posts reference a retired promo page, flagging for a redirect."),
    ("Migrate blog content to the new CMS", "Cover image re-crops are done through 2025. The 2024 archive is next."),
    ("Accessibility pass on checkout flow", "Focus order fixed in the cart drawer. One contrast issue left on the order summary muted text."),
    ("QA subscription signup form", "Gift flow works end to end. Failed-card retry loops back to the payment step correctly."),
    ("Wholesale price list import", "Price book received from Maya. 6 SKUs have no case-pack value, waiting on the roastery."),
    ("Net-30 terms application form", "Legal copy for the credit terms approved by Cedar finance on Tuesday."),
    ("Bulk order CSV upload validation", "Row-level error report now downloads as CSV. Adding case-pack multiple checks today."),
    ("Tiered discount rules engine", "Cart-level tiers pass tests. Account overrides land tomorrow."),
    ("Loyalty points balance widget", "Balance endpoint is cached for 60 seconds, header widget reads from it."),
    ("Referral bonus tracking", "Referral links generate. Bonus crediting waits on the points service webhook."),
    ("Compress hero imagery for mobile", "Shipped. LCP on 4G went from 4.1s to 2.3s on the home page."),
    ("Roaster availability calendar", "Live at /wholesale/roast-schedule and synced to the production sheet."),
    ("Build order tracking page", "Shippo webhook is wired, tracking states render. Polishing the empty state."),
    ("Review the pricing page", "New tier table drafted. Waiting on Cedar sign-off for the wholesale column."),
    ("Write launch announcement copy", "Final copy delivered and scheduled for the newsletter."),
    ("Redesign the menu detail template", "Shipped with the seasonal badge variant. Cedar happy with the tasting-notes layout."),
    ("Spring menu photography retouching", "All 22 selects delivered to the shared drive, print masters included."),
]
c_created = c_skipped = 0
for name, text in COMMENTS:
    t = by_name.get(name)
    if not t:
        continue
    key = text[:38]
    st, d = req(f"/comments?filter[collection][_eq]=os_tasks&filter[item][_eq]={t['id']}"
                f"&filter[comment][_starts_with]={urllib.parse.quote(key)}&fields=id&limit=1")
    if st == 200 and d.get("data"):
        c_skipped += 1
        continue
    st, d = req("/comments", "POST", {"collection": "os_tasks", "item": t["id"], "comment": text})
    die_on(st, d, f"comment on {name}")
    c_created += 1
print(f"directus_comments: created {c_created} / skipped {c_skipped}")

# ── C2. task file attachments ────────────────────────────────────────────────
st, d = req("/files?fields=id,title&limit=-1")
die_on(st, d, "files")
files = {f["title"]: f["id"] for f in d["data"]}
ATTACH = [
    ("Compress hero imagery for mobile", "Cafe interior"),
    ("Spring menu photography retouching", "Coffee roasting"),
    ("Redesign the menu detail template", "Project photo 03"),
    ("Set up recipe collection landing page", "Botanical detail"),
    ("Wholesale price list import", "Project photo 05"),
    ("Loyalty points balance widget", "Dashboard mockup"),
    ("Build the locations map page", "Site photography 01"),
    ("Net-30 terms application form", "Project photo 08"),
]
a_created = a_skipped = 0
for tname, ftitle in ATTACH:
    t = by_name.get(tname)
    fid = files.get(ftitle)
    if not t or not fid:
        continue
    _, was = upsert("os_task_files",
                    {"os_tasks_id": t["id"], "directus_files_id": fid},
                    {"os_tasks_id": t["id"], "directus_files_id": fid})
    a_created += was
    a_skipped += (not was)
print(f"os_task_files: created {a_created} / skipped {a_skipped}")

# ── C3. activity log ─────────────────────────────────────────────────────────
EVENTS = []
STAMPS = ["2026-07-15T17:20:00Z", "2026-07-14T21:05:00Z", "2026-07-13T16:40:00Z",
          "2026-07-12T19:10:00Z", "2026-07-10T15:30:00Z", "2026-07-09T22:15:00Z",
          "2026-07-08T18:45:00Z", "2026-07-07T16:05:00Z", "2026-07-03T20:30:00Z",
          "2026-07-02T17:55:00Z", "2026-06-30T15:10:00Z", "2026-06-27T19:25:00Z"]
i = 0
for (proj, name, status, *_rest) in [(t[0], t[1], t[2]) for t in NEW_TASKS]:
    t = by_name.get(name)
    if not t:
        continue
    EVENTS.append((name, "created", STAMPS[i % len(STAMPS)]))
    i += 1
    if status == "completed":
        EVENTS.append((name, "completed", STAMPS[i % len(STAMPS)]))
        i += 1
    elif status in ("in_review", "in_progress"):
        EVENTS.append((name, "status_changed", STAMPS[i % len(STAMPS)]))
        i += 1
e_created = e_skipped = 0
for name, verb, stamp in EVENTS:
    t = by_name[name]
    st, d = req(f"/items/os_activity_log?filter[target_id][_eq]={t['id']}"
                f"&filter[verb][_eq]={verb}&fields=id&limit=1")
    if st == 200 and d.get("data"):
        e_skipped += 1
        continue
    st, d = req("/items/os_activity_log", "POST", {
        "actor": EMP_USER, "verb": verb, "target_collection": "os_tasks",
        "target_id": t["id"], "project": t["project"], "timestamp": stamp,
        "metadata": {"task": name, "status": verb if verb != "created" else None}})
    die_on(st, d, f"activity {verb} {name}")
    e_created += 1
print(f"os_activity_log: created {e_created} / skipped {e_skipped}")

# ── D. invoices ──────────────────────────────────────────────────────────────
# org -> contacts (via junction), org -> projects
st, d = req("/items/organizations_contacts?fields=organizations_id,contacts_id&limit=-1")
die_on(st, d, "org contacts")
org_contacts = {}
for r in d["data"]:
    org_contacts.setdefault(str(r["organizations_id"]), []).append(r["contacts_id"])
st, d = req("/items/contacts?fields=id,email&limit=-1")
die_on(st, d, "contacts")
contact_email = {c["id"]: (c.get("email") or "") for c in d["data"]}
def best_contact(org):
    cands = org_contacts.get(str(org), [])
    cands = [c for c in cands if "muster.dev" not in contact_email.get(c, "")]
    biz = [c for c in cands if "example.com" not in contact_email.get(c, "")]
    return (biz or cands or [None])[0]

st, d = req("/items/os_projects?fields=id,name,organization,status,kind&limit=-1")
die_on(st, d, "projects all")
org_projects = {}
for p in d["data"]:
    org_projects.setdefault(str(p.get("organization")), []).append(p)
def best_project(org):
    cands = org_projects.get(str(org), [])
    active = [p for p in cands if p.get("status") == "active" and p.get("kind") != "retainer"]
    return ((active or cands) or [{}])[0].get("id")

st, d = req("/items/os_invoices?fields=id,invoice_number,status,subtotal,total,total_tax,"
            "amount_paid,contact,project,organization,issue_date,due_date&limit=-1")
die_on(st, d, "invoices")
invoices = d["data"]

# existing item type convention
st, d = req("/items/os_invoice_items?fields=id,invoice,type&limit=-1")
die_on(st, d, "items")
items_by_invoice = {}
item_type = "custom"
for it in d["data"]:
    items_by_invoice.setdefault(str(it["invoice"]), []).append(it)
    if it.get("type"):
        item_type = it["type"]

LINES = [
    ("Discovery and planning workshop", 0.18),
    ("Design and prototyping", 0.32),
    ("Development and integration", 0.38),
    ("QA, launch and handover support", 0.12),
]
it_created = filled_contact = filled_project = 0
for inv in invoices:
    if str(inv.get("organization")) == "1":
        continue  # real Muster history stays untouched
    iid = str(inv["id"])
    # 1) items for zero-item invoices, summing exactly to subtotal (or total)
    if iid not in items_by_invoice:
        target = float(inv.get("subtotal") or inv.get("total") or 0)
        if target > 0:
            n = 4 if target >= 3000 else (3 if target >= 1500 else 2)
            weights = LINES[:n]
            wsum = sum(w for _, w in weights)
            amounts = [round(target * w / wsum, 2) for _, w in weights]
            amounts[-1] = round(target - sum(amounts[:-1]), 2)
            for idx, ((label, _w), amt) in enumerate(zip(weights, amounts), start=1):
                _, was = upsert("os_invoice_items",
                                {"invoice": iid, "item_name": label},
                                {"invoice": iid, "item_name": label,
                                 "description": f"{label} for {inv.get('invoice_number')}",
                                 "quantity": 1, "unit_price": amt, "line_amount": amt,
                                 "line_item_number": idx, "type": item_type,
                                 "tax_rate": 0, "tax_amount": 0, "is_test_data": False})
                it_created += was
    # 2) contact / project fill-null
    patch = {}
    if not inv.get("contact"):
        c = best_contact(inv.get("organization"))
        if c:
            patch["contact"] = c
    if not inv.get("project"):
        p = best_project(inv.get("organization"))
        if p:
            patch["project"] = p
    if patch:
        st, d2 = req(f"/items/os_invoices/{inv['id']}", "PATCH", patch)
        die_on(st, d2, f"fill invoice {inv.get('invoice_number')}")
        filled_contact += 1 if "contact" in patch else 0
        filled_project += 1 if "project" in patch else 0
print(f"os_invoice_items: created {it_created}")
print(f"os_invoices fill-null: contact {filled_contact} / project {filled_project}")

# 3) payments for paid invoices that have none
st, d = req("/items/os_payments?fields=id,invoice,stripe_payment_id&limit=-1")
die_on(st, d, "payments")
have_payment = {str(p.get("invoice")) for p in d["data"]}
seq = 901
p_created = 0
for inv in invoices:
    if inv.get("status") != "paid" or str(inv["id"]) in have_payment:
        continue
    if str(inv.get("organization")) == "1":
        continue
    ref = f"pi_demo_{seq:04d}"
    seq += 1
    pay_date = inv.get("due_date") or inv.get("issue_date") or "2026-06-15"
    _, was = upsert("os_payments", {"invoice": inv["id"]}, {
        "invoice": inv["id"], "amount": float(inv.get("total") or 0),
        "status": "paid", "payment_date": pay_date,
        "payment_method_type": "card", "stripe_payment_id": ref,
        "organization": inv.get("organization"),
        "contact": inv.get("contact") or best_contact(inv.get("organization")),
        "is_test_data": False,
        "metadata": {"source": "demo-seed", "provider_ref": ref}})
    p_created += was
print(f"os_payments: created {p_created}")

# ── E. products ──────────────────────────────────────────────────────────────
# retainer project for maintained_by semantics
ret_id, was = upsert("os_projects",
                     {"name": "Cedar & Co - Care Plan Retainer"},
                     {"name": "Cedar & Co - Care Plan Retainer",
                      "description": "Monthly care plan covering hosting, updates, monitoring and small content changes for Cedar & Co properties.",
                      "organization": ORG, "kind": "retainer", "status": "active",
                      "start_date": "2025-10-01", "is_test_data": False})
print(f"os_projects retainer: {'created' if was else 'exists'} ({ret_id})")

ASSET = lambda title: f"{BASE}/assets/{files[title]}?download" if title in files else None
NEW_PRODUCTS = [
    {"name": "Cedar Seasonal Campaign Microsite", "slug": "cedar-seasonal-campaign-microsite",
     "status": "archived", "organization": ORG, "source_project": P_MENU,
     "delivered_date": "2025-12-05", "contract_end_date": "2026-03-31",
     "access_url": "https://season.cedarandco.example",
     "maintained_by": None,
     "description": "Holiday and seasonal campaign microsite for Cedar & Co Coffee.\n\n"
                    "- Gift guide with bundle builder\n- Countdown shipping-cutoff banner\n- Campaign analytics wired to the main site profile\n\n"
                    "Archived after the winter campaign ended; assets remain available below.",
     "assets": [{"label": "Campaign photography selects", "url": ASSET("Project photo 12")},
                {"label": "Holiday photography pack", "url": ASSET("Coffee roasting")}]},
    {"name": "Cedar Loyalty Microsite", "slug": "cedar-loyalty-microsite",
     "status": "active", "organization": ORG, "source_project": P_LOYALTY,
     "delivered_date": "2026-06-20", "contract_end_date": None,
     "access_url": "https://loyalty.cedarandco.example",
     "maintained_by": ret_id,
     "description": "Members-only loyalty microsite.\n\n"
                    "- Points balance and reward tiers\n- Digital punch card with QR redemption\n- Referral links with double-sided bonuses\n\n"
                    "Maintained under the Cedar care plan retainer.",
     "assets": [{"label": "Member onboarding guide", "url": ASSET("Dashboard mockup")},
                {"label": "Launch photography", "url": ASSET("Cafe interior")}]},
]
pr_created = pr_skipped = 0
for p in NEW_PRODUCTS:
    p["assets"] = [a for a in p["assets"] if a["url"]]
    p["is_test_data"] = False
    _, was = upsert("os_products", {"name": p["name"]}, p)
    pr_created += was
    pr_skipped += (not was)
print(f"os_products: created {pr_created} / skipped {pr_skipped}")

# maintained_by fill-null on the existing Cedar website product
st, d = req("/items/os_products?filter[name][_eq]=Cedar%20%26%20Co%20Website&fields=id,maintained_by&limit=1")
if st == 200 and d.get("data"):
    row = d["data"][0]
    if not row.get("maintained_by"):
        st, d2 = req(f"/items/os_products/{row['id']}", "PATCH", {"maintained_by": ret_id})
        die_on(st, d2, "fill maintained_by")
        print("os_products: Cedar & Co Website maintained_by FILLED")
    else:
        print("os_products: Cedar & Co Website maintained_by exists")

print("SEED DONE")
