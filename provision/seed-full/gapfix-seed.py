#!/usr/bin/env python3
"""Gap-fix seeding for the Muster demo portal (2026-07-16).

Fixes four adversarial-verification failures:
  1. employee/invoices: Active Subscriptions KPI reads 0 because every
     recurring/fixed_term os_invoices row has subscription_status NULL.
     Backfill subscription_status (and a fake stripe_subscription_id ref)
     ONLY where currently NULL. Never overwrites a non-null value.
  2. employee/packages: `packages` collection does not exist. Create it with
     the exact PACKAGE_FIELDS fragment fields, grant demo policy read, seed 9.
  3. employee/services: `services` collection does not exist. Create it with
     the exact SERVICE_FIELDS fragment fields, grant demo policy read, seed 10.
  4. /employee-portal/personal: reminders / personal_inbox / studio_projects /
     studio_publish_targets collections do not exist. Create + grant read +
     seed. Also vary priority on the six workspace=personal os_tasks rows and
     add two more, plus workspace=personal os_projects companions for Studio.

Idempotent: collections/fields/relations/permissions checked before create;
rows upserted by natural key. All seeded rows is_test_data:false where the
field exists. Admin token read from ~/elk-os/.env inside this script; the
token value is never printed.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

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
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"  # Demo Read-Only

def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
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

# ---------------------------------------------------------------- helpers

def choices(vals):
    return [{"text": v.replace("_", " ").title(), "value": v} for v in vals]

def pk_uuid():
    return {"field": "id", "type": "uuid",
            "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
            "schema": {"is_primary_key": True, "length": 36, "has_auto_increment": False}}

def f_string(name, opts=None):
    meta = {"interface": "select-dropdown", "options": {"choices": choices(opts)}} if opts \
        else {"interface": "input"}
    return {"field": name, "type": "string", "meta": meta, "schema": {}}

def f_text(name):
    return {"field": name, "type": "text", "meta": {"interface": "input-multiline"}, "schema": {}}

def f_decimal(name):
    return {"field": name, "type": "decimal", "meta": {"interface": "input"},
            "schema": {"numeric_precision": 10, "numeric_scale": 2}}

def f_int(name):
    return {"field": name, "type": "integer", "meta": {"interface": "input"}, "schema": {}}

def f_bool(name, default=False):
    return {"field": name, "type": "boolean", "meta": {"interface": "boolean"},
            "schema": {"default_value": default}}

def f_ts(name):
    return {"field": name, "type": "timestamp", "meta": {"interface": "datetime"}, "schema": {}}

def f_json(name):
    return {"field": name, "type": "json", "meta": {"interface": "input-code"}, "schema": {}}

def f_uuid(name):
    return {"field": name, "type": "uuid", "meta": {"interface": "input"}, "schema": {}}

def f_m2o(name):
    return {"field": name, "type": "uuid",
            "meta": {"interface": "select-dropdown-m2o", "special": ["m2o"]}, "schema": {}}

def f_created():
    return {"field": "date_created", "type": "timestamp",
            "meta": {"interface": "datetime", "readonly": True, "hidden": True,
                     "special": ["date-created"]}, "schema": {}}

def f_updated():
    return {"field": "date_updated", "type": "timestamp",
            "meta": {"interface": "datetime", "readonly": True, "hidden": True,
                     "special": ["date-updated"]}, "schema": {}}

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

def ensure_field(collection, fdef):
    st, _ = req(f"/fields/{collection}/{fdef['field']}")
    if st == 200:
        return False
    st, data = req(f"/fields/{collection}", "POST", fdef)
    die_on(st, data, f"add field {collection}.{fdef['field']}")
    print(f"  field {collection}.{fdef['field']}: ADDED")
    return True

def ensure_relation(collection, field, related, one_field=None, on_delete="SET NULL"):
    st, _ = req(f"/relations/{collection}/{field}")
    if st == 200:
        return False
    st, data = req("/relations", "POST", {
        "collection": collection,
        "field": field,
        "related_collection": related,
        "meta": {"one_field": one_field, "sort_field": None},
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

def upsert(collection, natural_filter, payload):
    """Search by natural key, create if absent. Returns (id, created)."""
    q = "&".join(f"filter[{k}][_eq]={urllib.parse.quote(str(v))}" for k, v in natural_filter.items())
    st, data = req(f"/items/{collection}?{q}&fields=id&limit=1")
    die_on(st, data, f"search {collection}")
    if data["data"]:
        return data["data"][0]["id"], False
    st, data = req(f"/items/{collection}", "POST", payload)
    die_on(st, data, f"create {collection} row")
    return data["data"]["id"], True

# =====================================================================
# 1. INVOICES: subscription_status backfill (NULL rows only)
# =====================================================================
print("== 1. os_invoices subscription backfill ==")
SUB_MAP = {
    "INV-2026-002": "active",   "INV-2026-302": "active",
    "INV-2026-303": "active",   "INV-2026-304": "active",
    "INV-2026-305": "active",   "INV-2026-306": "active",
    "INV-2026-308": "active",   "INV-2026-312": "active",
    "INV-2026-313": "active",   "INV-2026-315": "active",
    "INV-2026-316": "active",   "INV-2026-321": "active",
    "INV-2026-300": "past_due", "INV-2026-311": "past_due",
    "INV-2026-322": "past_due", "INV-2026-314": "cancelled",
}
st, data = req("/items/os_invoices?limit=-1"
               "&fields=id,invoice_number,billing_type,subscription_status,stripe_subscription_id"
               "&filter[billing_type][_in]=recurring,fixed_term")
die_on(st, data, "list recurring invoices")
patched = skipped = 0
for row in data["data"]:
    num = row.get("invoice_number") or ""
    target = SUB_MAP.get(num)
    if not target:
        skipped += 1
        continue
    patch = {}
    if row.get("subscription_status") is None:
        patch["subscription_status"] = target
    if not row.get("stripe_subscription_id"):
        patch["stripe_subscription_id"] = "sub_demo_" + num.split("-")[-1]
    if patch:
        st, d2 = req(f"/items/os_invoices/{row['id']}", "PATCH", patch)
        die_on(st, d2, f"patch invoice {num}")
        patched += 1
    else:
        skipped += 1
print(f"os_invoices: patched {patched} / skipped {skipped} (already set)")

# =====================================================================
# 2. PACKAGES: collection + permission + rows
# =====================================================================
print("== 2. packages ==")
ensure_collection("packages", "inventory_2", "Package offerings catalog (demo)", [
    pk_uuid(),
    f_string("name"),
    f_text("description"),
    f_decimal("price"),
    f_string("status", ["draft", "active", "archived"]),
    f_string("type", ["support", "retainer", "sprint", "project"]),
    f_string("billing_cycle", ["monthly", "quarterly", "one_time"]),
    f_int("hours_included"),
    f_decimal("overage_rate"),
    f_int("support_hours"),
])
ensure_read_permission("packages")

PACKAGES = [
    ("Starter Care Plan", "Monthly website care for small marketing sites. Uptime monitoring, dependency updates, and a small bucket of content edits.", 450, "active", "support", "monthly", 4, 125, 4),
    ("Site Care Plus", "Everything in Starter Care plus performance budgets, a monthly analytics summary, and priority response within one business day.", 950, "active", "support", "monthly", 8, 120, 8),
    ("Growth Retainer", "Ongoing design and development hours for teams shipping every month. Hours roll into a shared backlog groomed with your team.", 2400, "active", "retainer", "monthly", 20, 110, 8),
    ("Quarterly Design Retainer", "A quarterly block of senior design time for brand, web, and campaign work. Planned each quarter, reported monthly.", 5400, "active", "retainer", "quarterly", 45, 105, 6),
    ("Enterprise Support", "Dedicated support pod with a named lead, generous included hours, and same day response on production incidents.", 8500, "active", "support", "monthly", 60, 95, 24),
    ("SEO Sprint", "A four week sprint covering technical audit fixes, on page improvements, and a measurement baseline.", 3200, "active", "sprint", "one_time", 30, None, None),
    ("Brand Refresh", "Compressed brand update: logo refinement, palette and type system, and a mini guideline set.", 6800, "active", "project", "one_time", 55, None, None),
    ("Launch Pad", "Fixed scope marketing site launch package for early stage teams. Five pages, CMS wiring, analytics baseline.", 1800, "draft", "project", "one_time", 15, None, None),
    ("Analytics Concierge", "Monthly analytics review, dashboard upkeep, and a written insights memo for leadership.", 1250, "draft", "support", "monthly", 6, 130, 2),
]
c = s = 0
for name, desc, price, status, typ, cycle, hrs, over, sup in PACKAGES:
    _, created = upsert("packages", {"name": name}, {
        "name": name, "description": desc, "price": price, "status": status,
        "type": typ, "billing_cycle": cycle, "hours_included": hrs,
        "overage_rate": over, "support_hours": sup,
    })
    c += created
    s += (not created)
print(f"packages: created {c} / skipped {s}")

# =====================================================================
# 3. SERVICES: collection + permission + rows
# =====================================================================
print("== 3. services ==")
ensure_collection("services", "handyman", "Service catalog (demo)", [
    pk_uuid(),
    f_string("name"),
    f_string("title"),
    f_text("description"),
    f_decimal("default_rate"),
    f_decimal("unit_cost"),
    f_string("pricing_type", ["hourly", "fixed", "retainer", "unit"]),
    f_string("category", ["strategy", "design", "development", "marketing", "operations"]),
    f_string("status", ["draft", "active", "archived"]),
    f_int("sort"),
])
ensure_read_permission("services")

SERVICES = [
    ("Discovery Sprint", "Product Discovery Sprint", "Two week discovery: stakeholder interviews, competitive scan, and a prioritized roadmap with estimates.", 4800, 3600, "fixed", "strategy", "active", 1),
    ("Next.js Site Build", "Marketing Site Build (Next.js)", "Design to production build of a content driven marketing site with CMS integration and CI deploys.", 165, 118, "hourly", "development", "active", 2),
    ("Design Retainer", "Senior Design Retainer", "Reserved senior designer time for iterative product and brand work, planned in monthly blocks.", 140, 96, "retainer", "design", "active", 3),
    ("SEO Audit", "Technical SEO Audit", "Crawl, index, and Core Web Vitals audit with a ranked remediation plan and expected impact per fix.", 2600, 1700, "fixed", "marketing", "active", 4),
    ("Hosting & Care Plan", "Hosting and Care Plan", "Managed hosting, backups, uptime monitoring, and dependency updates billed per site per month.", 95, 41, "unit", "operations", "active", 5),
    ("Brand System", "Brand Identity System", "Full identity system: logo suite, color and type tokens, usage guidelines, and an asset kit.", 9500, 6800, "fixed", "design", "active", 6),
    ("Analytics Setup", "Analytics and Event Setup", "Privacy friendly analytics install, event map, conversion goals, and a stakeholder dashboard.", 1900, 1150, "fixed", "marketing", "active", 7),
    ("Content Strategy", "Content Strategy Engagement", "Editorial audit, messaging hierarchy, and a 90 day content calendar with briefs.", 150, 105, "hourly", "strategy", "active", 8),
    ("Accessibility Review", "WCAG 2.1 AA Review", "Manual and automated accessibility review with annotated fixes and a retest pass.", 2200, 1400, "fixed", "development", "draft", 9),
    ("API Integration", "Third Party API Integration", "Scoped integration work: payment, CRM, or messaging APIs with tests and monitoring.", 175, 125, "hourly", "development", "archived", 10),
]
c = s = 0
for name, title, desc, rate, cost, ptype, cat, status, sort in SERVICES:
    _, created = upsert("services", {"name": name}, {
        "name": name, "title": title, "description": desc,
        "default_rate": rate, "unit_cost": cost, "pricing_type": ptype,
        "category": cat, "status": status, "sort": sort,
    })
    c += created
    s += (not created)
print(f"services: created {c} / skipped {s}")

# =====================================================================
# 4. PERSONAL: reminders + inbox + studio + os_tasks variance
# =====================================================================
print("== 4a. reminders ==")
ensure_collection("reminders", "notifications", "iOS-synced reminders mirror (demo)", [
    pk_uuid(),
    f_string("caldav_uid"),
    f_string("caldav_etag"),
    f_string("list_name"),
    f_string("title"),
    f_text("notes"),
    f_ts("due_at"),
    f_string("rrule"),
    f_bool("is_completed", False),
    f_ts("completed_at"),
    f_int("priority"),
    f_string("apple_url"),
    f_string("caldav_url"),
    f_ts("synced_at"),
    f_string("source", ["ios", "portal", "email", "shortcut"]),
    f_string("sync_state", ["synced", "pending_push", "orphaned"]),
    f_uuid("linked_task"),
    f_uuid("linked_project"),
])
ensure_read_permission("reminders")

SYNCED_AT = "2026-07-16T13:05:00Z"
REMINDERS = [
    # uid, title, due_at, priority, source, sync_state, notes
    ("demo-rem-001", "Send Harbor and Finch invoice follow up", "2026-07-10T16:00:00Z", 1, "ios", "synced", "INV-2026-311 is past due. Nudge accounts payable contact."),
    ("demo-rem-002", "Check musterr.dev TLS renewal", "2026-07-13T15:00:00Z", 5, "ios", "synced", None),
    ("demo-rem-003", "Chase Cedar Analytics SOW signature", "2026-07-15T19:00:00Z", 1, "ios", "synced", "Redlines went back Friday. Renewal call is next week."),
    ("demo-rem-004", "Post stand-up notes to ops channel", "2026-07-16T16:30:00Z", 5, "ios", "synced", None),
    ("demo-rem-005", "Approve Northlight homepage copy", "2026-07-16T20:00:00Z", 1, "ios", "synced", None),
    ("demo-rem-006", "Export June burn report for finance", "2026-07-16T22:00:00Z", 9, "ios", "synced", None),
    ("demo-rem-007", "Prep Q3 roadmap deck outline", "2026-07-17T18:00:00Z", 5, "ios", "synced", None),
    ("demo-rem-008", "Rotate demo API tokens", "2026-07-18T17:00:00Z", 1, "ios", "synced", "Quarterly rotation window closes Friday."),
    ("demo-rem-009", "Draft Beacon and Bloom proposal", "2026-07-20T17:00:00Z", 5, "ios", "synced", None),
    ("demo-rem-010", "Plan team offsite agenda", "2026-07-22T17:00:00Z", 9, "ios", "synced", None),
    ("demo-rem-011", "Order color calibration target", "2026-07-21T17:00:00Z", 0, "portal", "pending_push", None),
    ("demo-rem-012", "Sketch portfolio redesign ideas", None, 0, "ios", "synced", None),
]
c = s = 0
for uid, title, due, prio, source, state, notes in REMINDERS:
    _, created = upsert("reminders", {"caldav_uid": uid}, {
        "caldav_uid": uid, "caldav_etag": f"etag-{uid}", "list_name": "Muster",
        "title": title, "notes": notes, "due_at": due, "rrule": None,
        "is_completed": False, "completed_at": None, "priority": prio,
        "apple_url": None, "caldav_url": None,
        "synced_at": SYNCED_AT if state == "synced" else None,
        "source": source, "sync_state": state,
        "linked_task": None, "linked_project": None,
    })
    c += created
    s += (not created)
print(f"reminders: created {c} / skipped {s}")

print("== 4b. personal_inbox ==")
ensure_collection("personal_inbox", "inbox", "Personal capture inbox (demo)", [
    pk_uuid(),
    f_text("raw_text"),
    f_string("subject"),
    f_string("from_address"),
    f_string("source", ["email", "shortcut", "portal"]),
    f_uuid("attachment"),
    f_string("triage_status", ["pending", "converted", "dismissed"]),
    f_string("converted_to", ["reminder", "task", "idea"]),
    f_string("converted_id"),
    f_created(),
    f_updated(),
])
ensure_read_permission("personal_inbox")

INBOX = [
    ("Fwd: Updated brand assets from Northlight", "Anna sent over the refreshed logo files and asked which formats we need for the portal header. The zip is on the shared drive.", "anna.kessler@northlight.example", "email", "pending", None),
    ("Domain renewal notice: beaconandbloom.example", "Registrar notice: beaconandbloom.example renews on 2026-08-02. Confirm the auto renew card is current.", "renewals@registrar.example", "email", "pending", None),
    ("Idea: Harbor migration case study", "Write up the Harbor and Finch replatform as a case study. Angle: zero downtime cutover and the 38 percent LCP win.", None, "shortcut", "pending", None),
    ("Voice memo: Cedar renewal pitch angle", "Lead with the quarterly insights memo they liked, then propose the analytics concierge add on before the August renewal call.", None, "shortcut", "pending", None),
    ("Clip: competitor pricing page teardown", "Saved a teardown of three studio pricing pages. Good patterns: anchor tier naming and transparent overage rates.", None, "portal", "pending", None),
    ("Fwd: Payout schedule change notice", "Payment processor moves to a two day rolling payout starting August. Check cash flow assumptions in the forecast sheet.", "notices@payments.example", "email", "pending", None),
    ("Call the print shop about proof samples", "Pier series proofs are ready. Pickup window is Tuesday to Friday, 10 to 4.", None, "shortcut", "converted", "reminder"),
    ("Newsletter: 10 design trends for 2027", "Trend roundup newsletter. Nothing actionable.", "digest@designweekly.example", "email", "dismissed", None),
]
c = s = 0
for subject, raw, sender, source, triage, conv in INBOX:
    _, created = upsert("personal_inbox", {"subject": subject}, {
        "subject": subject, "raw_text": raw, "from_address": sender,
        "source": source, "attachment": None, "triage_status": triage,
        "converted_to": conv, "converted_id": None,
    })
    c += created
    s += (not created)
print(f"personal_inbox: created {c} / skipped {s}")

print("== 4c. studio ==")
# os_projects.workspace: additive field the portal source expects
ensure_field("os_projects", f_string("workspace"))

ensure_collection("studio_projects", "palette", "Creative pipeline companions (demo)", [
    pk_uuid(),
    f_string("discipline", ["photo", "design", "art", "other"]),
    f_string("pipeline_stage", ["idea", "plan", "shoot_draft", "cull_edit", "publish", "done"]),
    f_ts("stage_entered_at"),
    f_int("gallery"),
    f_text("shot_list"),
    f_json("reference_links"),
    f_text("location_notes"),
    f_text("gear_notes"),
    f_m2o("project"),
])
ensure_collection("studio_publish_targets", "publish", "Studio publish checklist (demo)", [
    pk_uuid(),
    f_m2o("studio_project"),
    f_string("target", ["wlsr_me", "portfolio", "outside_door_art", "instagram", "print", "other"]),
    f_string("status", ["todo", "done"]),
    f_string("url"),
    f_ts("published_at"),
])
# o2m alias so fields=publish_targets.* resolves
ensure_field("studio_projects", {"field": "publish_targets", "type": "alias",
                                 "meta": {"interface": "list-o2m", "special": ["o2m"]},
                                 "schema": None})
ensure_relation("studio_projects", "project", "os_projects", on_delete="SET NULL")
ensure_relation("studio_publish_targets", "studio_project", "studio_projects",
                one_field="publish_targets", on_delete="CASCADE")
ensure_read_permission("studio_projects")
ensure_read_permission("studio_publish_targets")

STUDIO = [
    # project name, os_status, discipline, stage, entered, shot_list, ref_links, location, gear, targets
    ("Golden Hour Pier Series", "in_progress", "photo", "cull_edit", "2026-07-12T18:00:00Z",
     "Pilings at low tide\nLong exposure ferry wake\nRail detail close ups\nSilhouette pair at rail",
     [{"label": "Mood board", "url": "https://boards.wlsr.example/pier-series"}],
     "North pier, golden hour 7:40 to 8:20 pm. Backup: marina breakwater.",
     "85mm f1.8 prime, 6 stop ND, travel tripod",
     [("wlsr_me", "todo", None, None), ("instagram", "todo", None, None), ("print", "todo", None, None)]),
    ("Muster Landing Illustrations", "in_progress", "design", "publish", "2026-07-14T17:00:00Z",
     None,
     [{"label": "Landing draft", "url": "https://landing.muster.example/draft"}],
     None, None,
     [("wlsr_me", "done", "https://wlsr.example/work/muster-landing", "2026-07-15T20:00:00Z"),
      ("portfolio", "todo", None, None)]),
    ("Charcoal Figure Studies", "new", "art", "idea", "2026-07-06T16:00:00Z",
     None, None, None, "Willow charcoal, newsprint pad", []),
    ("Client Case Study Covers", "in_progress", "design", "plan", "2026-07-10T16:00:00Z",
     None,
     [{"label": "Cover grid refs", "url": "https://type.example/specimens"}],
     None, None, []),
    ("Desert Road Trip Photo Essay", "in_progress", "photo", "shoot_draft", "2026-07-08T15:00:00Z",
     "Route 89 pullouts\nMotel neon at dusk\nDiner counter portrait",
     None,
     "Day 1 Bend to Alvord, day 2 Alvord to Boise.",
     "35mm and 50mm primes, polarizer",
     [("portfolio", "todo", None, None)]),
    ("Generative Poster Experiments", "completed", "art", "done", "2026-06-28T18:00:00Z",
     None, None, None, None,
     [("instagram", "done", "https://instagram.example/p/demo-posters", "2026-07-01T18:00:00Z"),
      ("portfolio", "done", "https://wlsr.example/work/poster-experiments", "2026-07-02T17:00:00Z"),
      ("print", "todo", None, None)]),
]
proj_c = studio_c = tgt_c = sk = 0
for (pname, pstatus, disc, stage, entered, shots, refs, loc, gear, targets) in STUDIO:
    pid, created = upsert("os_projects", {"name": pname, "workspace": "personal"}, {
        "name": pname, "workspace": "personal", "status": pstatus,
        "project_type": "design" if disc == "design" else "other",
        "description": "Personal studio project.", "is_test_data": False,
    })
    proj_c += created
    sid, created = upsert("studio_projects", {"project": pid}, {
        "project": pid, "discipline": disc, "pipeline_stage": stage,
        "stage_entered_at": entered, "gallery": None, "shot_list": shots,
        "reference_links": refs, "location_notes": loc, "gear_notes": gear,
    })
    studio_c += created
    for (tname, tstatus, turl, tpub) in targets:
        _, created = upsert("studio_publish_targets",
                            {"studio_project": sid, "target": tname}, {
            "studio_project": sid, "target": tname, "status": tstatus,
            "url": turl, "published_at": tpub,
        })
        tgt_c += created
print(f"os_projects(personal): created {proj_c} / studio_projects: created {studio_c} / publish_targets: created {tgt_c}")

print("== 4d. personal os_tasks variance ==")
PRIORITY_MAP = {
    "Prep Cedar retro notes": "P1",
    "Review Harbor sprint burndown": "P0",
    "Draft Northlight kickoff agenda": "P1",
    "Update weekly status doc": "P3",
    "Plan Q3 capacity review": "P2",
    "Organize demo screenshot library": "P3",
}
st, data = req("/items/os_tasks?limit=-1&fields=id,name,priority"
               "&filter[workspace][_eq]=personal")
die_on(st, data, "list personal tasks")
patched = skipped = 0
for row in data["data"]:
    want = PRIORITY_MAP.get(row["name"])
    if want and row.get("priority") != want:
        st, d2 = req(f"/items/os_tasks/{row['id']}", "PATCH", {"priority": want})
        die_on(st, d2, f"patch task {row['name']}")
        patched += 1
    else:
        skipped += 1

NEW_TASKS = [
    ("File June expense receipts", "P3", "2026-07-18T17:00:00Z"),
    ("Renew studio insurance policy", "P1", "2026-07-28T17:00:00Z"),
]
created = 0
for name, prio, due in NEW_TASKS:
    _, was_created = upsert("os_tasks", {"name": name, "workspace": "personal"}, {
        "name": name, "priority": prio, "due_date": due, "status": "pending",
        "type": "task", "responsibility": "team", "is_visible_to_client": False,
        "workspace": "personal", "is_test_data": False,
    })
    created += was_created
print(f"os_tasks personal: patched {patched} / created {created} / skipped {skipped}")

print("ALL DONE")
