#!/usr/bin/env python3
"""F4 foundation-taxonomy-config seeder for the Muster demo (cms.musterr.dev).

Seeds: os_email_templates (7), os_project_templates (5), os_items rate card (9),
os_products catalog (8 new), organization_addresses (8 HQ rows), verifies
os_deal_stages (5), sets os_settings.organization_folder_root from F2's
assets-manifest.json if readable, polls for the F1-added os_products.maintained_by
field and links 2 products to retainer-ish projects when present.

Rules honored: add-only, idempotent upsert by natural key, is_test_data false
where the field exists, no em dashes in content, never edits the 2 pre-existing
os_products rows, never prints secrets (token loaded inside this script).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("DIRECTUS_URL", "https://cms.musterr.dev").rstrip("/")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-07-16"


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


def request(method, path, payload=None, retries=3):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                return r.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                last_err = (e.code, body)
                continue
            return e.code, {"_raw": body}
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                last_err = (0, str(e))
                continue
            return 0, {"_raw": str(e)}
    return last_err[0], {"_raw": last_err[1]}


def get(path):
    return request("GET", path)


def assert_no_dashes(obj):
    s = json.dumps(obj, ensure_ascii=False)
    if "\u2014" in s or "\u2013" in s:
        raise ValueError("em/en dash found in payload: " + s[:200])


def upsert(collection, filter_qs, payload, counters):
    """Search by natural key; create if absent, patch if present."""
    assert_no_dashes(payload)
    status, found = get(f"/items/{collection}?{filter_qs}&fields=id&limit=2")
    if status != 200:
        raise RuntimeError(f"{collection} search failed {status}: {found}")
    rows = found.get("data", [])
    if rows:
        rid = rows[0]["id"]
        status, res = request("PATCH", f"/items/{collection}/{rid}", payload)
        if status != 200:
            raise RuntimeError(f"{collection} patch {rid} failed {status}: {res}")
        counters["updated"] += 1
        return rid
    status, res = request("POST", f"/items/{collection}", payload)
    if status not in (200, 201):
        raise RuntimeError(f"{collection} create failed {status}: {res}")
    counters["created"] += 1
    return res["data"]["id"]


def report(collection, c):
    print(f"{collection}: created {c['created']} / updated {c['updated']} / skipped {c['skipped']}")


def eq(field, value):
    return f"filter[{field}][_eq]={urllib.parse.quote(str(value))}"


# ---------------------------------------------------------------- email templates

EMAIL_TEMPLATES = [
    {
        "name": "Invoice Sent",
        "subject": "Invoice {{invoice_number}} from Muster Digital",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "Your invoice {{invoice_number}} for {{project_name}} is ready. The total due is "
            "{{invoice_total}}, and payment is due by {{due_date}}. You can view the full line "
            "item breakdown and pay online at {{invoice_url}}.\n\n"
            "If anything on the invoice looks off, reply to this email and we will sort it out "
            "before the due date. Thank you for working with us."
        ),
    },
    {
        "name": "Payment Receipt",
        "subject": "Payment received for {{invoice_number}}",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "We received your payment of {{payment_amount}} on {{payment_date}} for invoice "
            "{{invoice_number}}. The remaining balance on the {{organization_name}} account is "
            "now {{balance_due}}.\n\n"
            "A PDF receipt is attached for your records. No further action is needed, and we "
            "appreciate the prompt payment."
        ),
    },
    {
        "name": "Proposal Follow-up",
        "subject": "Checking in on proposal {{proposal_number}}",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "A quick follow-up on the proposal we sent for {{proposal_title}} on {{sent_date}}. "
            "The pricing and timeline in that document are valid through {{expiration_date}}, so "
            "there is still time to lock in the current scope.\n\n"
            "Happy to walk through phasing, budget, or timeline questions on a short call. You "
            "can grab a slot that works for you at {{booking_url}}.\n\n"
            "If the timing is not right this quarter, just say so and we will check back later "
            "in the year."
        ),
    },
    {
        "name": "Project Kickoff",
        "subject": "Kickoff for {{project_name}} is scheduled",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "We are all set to kick off {{project_name}}. The kickoff call is scheduled for "
            "{{kickoff_date}} at {{kickoff_time}}, and you can join with this link: "
            "{{meeting_url}}. {{project_manager}} will lead the session and be your main point "
            "of contact going forward.\n\n"
            "Before the call, please gather any brand assets, credentials, and reference sites "
            "you want us to review. We will cover scope, milestones, and the communication "
            "rhythm, and you will leave with a clear picture of the first two weeks.\n\n"
            "Looking forward to getting started."
        ),
    },
    {
        "name": "Weekly Status Update",
        "subject": "{{project_name}} weekly update for {{week_of}}",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "Here is where {{project_name}} stands for the week of {{week_of}}. Completed: "
            "{{completed_items}}. Up next: {{next_items}}. Overall the project is "
            "{{percent_complete}} complete and tracking {{schedule_status}} against the plan.\n\n"
            "Current blockers or items waiting on your side: {{blockers}}. You can see the live "
            "task board and timeline any time in your portal at {{portal_url}}.\n\n"
            "Reply here with questions and we will pick them up in the next working session."
        ),
    },
    {
        "name": "Support Ticket Received",
        "subject": "We received your ticket {{ticket_id}}",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "Thanks for reaching out. Your ticket {{ticket_id}} about {{ticket_subject}} is in "
            "our queue and has been triaged as {{priority}} priority. You can expect a first "
            "response within {{response_sla}}.\n\n"
            "You can add screenshots, context, or replies directly on the ticket at "
            "{{ticket_url}}. Anything you add before we pick it up helps us resolve it faster."
        ),
    },
    {
        "name": "Renewal Reminder",
        "subject": "Your {{plan_name}} plan renews on {{renewal_date}}",
        "body": (
            "Hi {{contact_first_name}},\n\n"
            "This is a friendly reminder that the {{plan_name}} plan for {{organization_name}} "
            "renews on {{renewal_date}}. The renewal amount is {{renewal_amount}} and it will be "
            "charged to the payment method on file ({{payment_method}}).\n\n"
            "If you want to change tiers, update billing details, or talk through what the plan "
            "covered this year, visit {{billing_url}} or reply to this email before the renewal "
            "date. No action is needed to continue as is."
        ),
    },
]


def seed_email_templates():
    c = {"created": 0, "updated": 0, "skipped": 0}
    for t in EMAIL_TEMPLATES:
        upsert("os_email_templates", eq("name", t["name"]), t, c)
    report("os_email_templates", c)


# ---------------------------------------------------------------- project templates

PROJECT_TEMPLATES = [
    {
        "name": "Website Build",
        "description": "<p>Standard marketing site engagement: discovery through launch on the agency Next.js and Directus stack. Fits 6 to 10 week timelines.</p>",
        "status": "active",
        "tasks": [
            {"name": "Discovery workshop", "type": "meeting", "points": 3},
            {"name": "Sitemap and content inventory", "type": "task", "points": 3},
            {"name": "Wireframes", "type": "deliverable", "points": 5},
            {"name": "Visual design system", "type": "deliverable", "points": 8},
            {"name": "Homepage build", "type": "task", "points": 5},
            {"name": "Interior page templates", "type": "task", "points": 8},
            {"name": "CMS integration", "type": "task", "points": 5},
            {"name": "Content entry and migration", "type": "task", "points": 3},
            {"name": "QA and accessibility pass", "type": "task", "points": 3},
            {"name": "Launch", "type": "milestone", "points": 2},
        ],
    },
    {
        "name": "Brand Identity Sprint",
        "description": "<p>Compressed identity engagement: research, logo system, color and type, delivered as a guidelines document with a full asset handoff.</p>",
        "status": "active",
        "tasks": [
            {"name": "Brand discovery session", "type": "meeting", "points": 3},
            {"name": "Competitive and audience research", "type": "task", "points": 3},
            {"name": "Moodboards and creative direction", "type": "deliverable", "points": 3},
            {"name": "Logo concepts", "type": "deliverable", "points": 8},
            {"name": "Refinement round", "type": "task", "points": 5},
            {"name": "Color and type system", "type": "deliverable", "points": 5},
            {"name": "Brand guidelines document", "type": "deliverable", "points": 5},
            {"name": "Final asset handoff", "type": "milestone", "points": 2},
        ],
    },
    {
        "name": "SEO Retainer Onboarding",
        "description": "<p>First month of a search retainer: technical audit, baseline research, tracking, and the roadmap that drives the monthly cadence.</p>",
        "status": "active",
        "tasks": [
            {"name": "Technical SEO audit", "type": "task", "points": 5},
            {"name": "Analytics and Search Console access", "type": "task", "points": 1},
            {"name": "Keyword research baseline", "type": "task", "points": 5},
            {"name": "Content gap analysis", "type": "task", "points": 3},
            {"name": "Local listings cleanup", "type": "task", "points": 2},
            {"name": "Reporting dashboard setup", "type": "task", "points": 3},
            {"name": "Month one roadmap review", "type": "meeting", "points": 2},
        ],
    },
    {
        "name": "App MVP",
        "description": "<p>Product build from discovery to a production MVP: auth, core feature set, admin tooling, payments, and a beta cycle before launch.</p>",
        "status": "active",
        "tasks": [
            {"name": "Product discovery workshop", "type": "meeting", "points": 5},
            {"name": "User stories and acceptance criteria", "type": "task", "points": 3},
            {"name": "Data model and API design", "type": "task", "points": 5},
            {"name": "Auth and account flows", "type": "task", "points": 5},
            {"name": "Core feature build", "type": "task", "points": 13},
            {"name": "Admin dashboard", "type": "task", "points": 8},
            {"name": "Payments integration", "type": "task", "points": 5},
            {"name": "Beta test round", "type": "task", "points": 3},
            {"name": "Bug triage and hardening", "type": "task", "points": 5},
            {"name": "Production launch", "type": "milestone", "points": 3},
        ],
    },
    {
        "name": "Care Plan Onboarding",
        "description": "<p>Onboarding checklist for the hosting care plan: environment audit, backups, monitoring, and the first monthly report.</p>",
        "status": "active",
        "tasks": [
            {"name": "Hosting environment audit", "type": "task", "points": 2},
            {"name": "Backup and monitoring setup", "type": "task", "points": 3},
            {"name": "Dependency and plugin updates", "type": "task", "points": 2},
            {"name": "Uptime and alert channels", "type": "task", "points": 1},
            {"name": "Care plan welcome call", "type": "meeting", "points": 1},
            {"name": "First monthly report", "type": "deliverable", "points": 2},
        ],
    },
]


def seed_project_templates():
    c = {"created": 0, "updated": 0, "skipped": 0}
    for t in PROJECT_TEMPLATES:
        upsert("os_project_templates", eq("name", t["name"]), t, c)
    report("os_project_templates", c)


# ---------------------------------------------------------------- rate card items

RATE_CARD = [
    ("Discovery Workshop", "lightbulb", 800, 1500,
     "Half-day facilitated session covering goals, audiences, scope, and success metrics. Output is a written brief the whole engagement hangs off."),
    ("Design Sprint", "pen-tool", 2400, 4500,
     "One-week concept sprint: moodboards, two design directions, and a clickable prototype reviewed with stakeholders on day five."),
    ("Next.js Development Day", "code", 600, 1100,
     "One senior developer day on the agency Next.js stack. Used for feature work, integrations, and post-launch improvements."),
    ("CMS Setup", "database", 900, 1800,
     "Directus instance provisioning: collections, roles, editorial permissions, and a content model matched to the approved designs."),
    ("SEO Audit", "search", 700, 1400,
     "Technical and content audit: crawl health, Core Web Vitals, metadata, structured data, and a prioritized fix list."),
    ("Hosting Care Plan Monthly", "server", 120, 450,
     "Monthly hosting and maintenance: updates, daily backups, uptime monitoring, and a small block of support time."),
    ("Analytics Setup", "bar-chart-3", 500, 950,
     "Matomo property setup with goal tracking, event taxonomy, dashboard views, and a handoff walkthrough for the client team."),
    ("Content Migration", "file-text", 400, 850,
     "Structured migration of existing pages, posts, and media into the new CMS, including redirects and URL mapping."),
    ("Brand System", "palette", 3200, 6500,
     "Full identity system: logo suite, color and type scales, usage guidelines, and production-ready asset exports."),
]


def seed_items():
    c = {"created": 0, "updated": 0, "skipped": 0}
    for name, icon, cost, price, desc in RATE_CARD:
        payload = {
            "name": name,
            "description": desc,
            "icon": icon,
            "unit_cost": cost,
            "unit_price": price,
            "tax_rate": 0,
            "status": "active",
        }
        upsert("os_items", eq("name", name), payload, c)
    report("os_items", c)


# ---------------------------------------------------------------- products catalog

PRODUCTS = [
    {
        "name": "Cedar & Co Website",
        "slug": "cedar-co-website",
        "organization": 2,
        "source_project": "430df3e9-7f6d-4369-81cf-d9e5dc0fab00",
        "status": "active",
        "delivered_date": "2025-09-18",
        "contract_end_date": "2026-08-02",
        "access_url": "https://cedarandco.com",
        "description": "Marketing site for the roastery and all three cafes. Next.js front end on Directus with menu, locations, and wholesale inquiry flows.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/cedar-co-website"},
            {"label": "Staging", "url": "https://staging.cedarandco.com"},
            {"label": "Style Guide", "url": "https://cedarandco.com/style-guide"},
        ],
    },
    {
        "name": "Cedar Wholesale Portal",
        "slug": "cedar-wholesale-portal",
        "organization": 2,
        "source_project": "a42f4921-7747-4319-b09e-644f639e89c5",
        "status": "active",
        "delivered_date": "2026-03-06",
        "contract_end_date": "2027-03-06",
        "access_url": "https://cedarandco.com",
        "description": "B2B ordering portal for cafe and grocery wholesale accounts: tiered pricing, standing orders, and invoice history.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/cedar-wholesale-portal"},
            {"label": "Staging", "url": "https://staging-wholesale.cedarandco.com"},
        ],
        "_maintained_by": "a42f4921-7747-4319-b09e-644f639e89c5",
    },
    {
        "name": "Northlight Brand System",
        "slug": "northlight-brand-system",
        "organization": 3,
        "source_project": "91528c06-daee-41eb-b614-363afb1eb531",
        "status": "active",
        "delivered_date": "2025-11-14",
        "contract_end_date": "2026-11-30",
        "access_url": "https://northlightlaw.com",
        "description": "Complete identity system for the firm: logo suite, stationery, pitch templates, and a hosted brand guidelines site.",
        "assets": [
            {"label": "Style Guide", "url": "https://northlightlaw.com/brand"},
            {"label": "Repository", "url": "https://github.com/muster-demo/northlight-brand-system"},
        ],
        "_maintained_by": "193e5bd8-e9b2-471e-91e9-7c19aa2a2c7a",
    },
    {
        "name": "Vellum Portfolio Site",
        "slug": "vellum-portfolio-site",
        "organization": 4,
        "source_project": "4ae1d3fa-92fb-443d-86c8-4636df95e41c",
        "status": "active",
        "delivered_date": "2026-01-22",
        "contract_end_date": "2027-01-31",
        "access_url": "https://vellum.studio",
        "description": "Case-study driven portfolio platform with a CMS-managed project index, editorial layouts, and a motion-friendly media pipeline.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/vellum-portfolio"},
            {"label": "Staging", "url": "https://staging.vellum.studio"},
        ],
    },
    {
        "name": "Harbor Booking App",
        "slug": "harbor-booking-app",
        "organization": 5,
        "source_project": "d16e4ef5-a11c-4165-8f5b-2a79fa1a1e51",
        "status": "active",
        "delivered_date": "2026-04-10",
        "contract_end_date": "2027-04-30",
        "access_url": "https://harborfitness.co",
        "description": "Class booking web app: schedules, memberships, waitlists, and front-desk check-in, integrated with the gym's payment provider.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/harbor-booking-app"},
            {"label": "Staging", "url": "https://staging.harborfitness.co"},
        ],
    },
    {
        "name": "Bloom Shopify Storefront",
        "slug": "bloom-shopify-storefront",
        "organization": 6,
        "source_project": "3d5677cf-af08-4df2-a29a-6a4925ab9268",
        "status": "archived",
        "delivered_date": "2025-08-29",
        "contract_end_date": "2026-06-30",
        "access_url": "https://bloombotanicals.com",
        "description": "Custom Shopify theme for the plant and garden catalog with subscription bundles and a care-guide content section. Support contract ended June 2026.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/bloom-shopify-theme"},
        ],
    },
    {
        "name": "Sterling Reservations System",
        "slug": "sterling-reservations-system",
        "organization": 7,
        "source_project": "cd1eae58-ec99-4444-bbe4-ae6ab9370cea",
        "status": "active",
        "delivered_date": "2026-05-27",
        "contract_end_date": "2027-05-31",
        "access_url": "https://sterlingandvine.com",
        "description": "Reservations and table management for all three locations: online booking, floor plans, and nightly service reports for managers.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/sterling-reservations"},
            {"label": "Staging", "url": "https://staging.sterlingandvine.com"},
        ],
    },
    {
        "name": "Meridian Grant Portal",
        "slug": "meridian-grant-portal",
        "organization": 8,
        "source_project": "c6581803-8fe8-43e7-bb56-4f1e758e2a25",
        "status": "active",
        "delivered_date": "2026-06-30",
        "contract_end_date": "2027-06-30",
        "access_url": "https://meridianfund.org",
        "description": "Grant application and review portal: applicant intake, reviewer scoring workflows, and award tracking for the environmental grants program.",
        "assets": [
            {"label": "Repository", "url": "https://github.com/muster-demo/meridian-grant-portal"},
            {"label": "Staging", "url": "https://staging.meridianfund.org"},
            {"label": "Style Guide", "url": "https://meridianfund.org/brand"},
        ],
    },
]


def seed_products():
    c = {"created": 0, "updated": 0, "skipped": 0}
    for p in PRODUCTS:
        payload = {k: v for k, v in p.items() if not k.startswith("_")}
        payload["is_test_data"] = False
        upsert("os_products", eq("name", p["name"]), payload, c)
    report("os_products", c)


def maintained_by_field_exists():
    status, _ = get("/fields/os_products/maintained_by")
    return status == 200


def link_maintained_by(poll_attempts=10, poll_sleep=30):
    present = maintained_by_field_exists()
    attempts = 1
    while not present and attempts < poll_attempts:
        print(f"os_products.maintained_by absent, waiting {poll_sleep}s (attempt {attempts}/{poll_attempts})")
        time.sleep(poll_sleep)
        present = maintained_by_field_exists()
        attempts += 1
    if not present:
        print("os_products.maintained_by: STILL ABSENT after polling, seeded without it")
        return False
    linked = 0
    for p in PRODUCTS:
        target = p.get("_maintained_by")
        if not target:
            continue
        status, found = get(f"/items/os_products?{eq('name', p['name'])}&fields=id,maintained_by&limit=1")
        rows = found.get("data", []) if status == 200 else []
        if not rows:
            print(f"maintained_by link: product not found for {p['name']}")
            continue
        status, res = request("PATCH", f"/items/os_products/{rows[0]['id']}", {"maintained_by": target})
        if status == 200:
            linked += 1
        else:
            print(f"maintained_by link FAILED for {p['name']}: {status} {res}")
    print(f"os_products.maintained_by: linked {linked} products")
    return True


# ---------------------------------------------------------------- org addresses

ADDRESSES = [
    (1, "100 Demo Street, Suite 400", "Portland", "OR", "97204"),
    (2, "214 Alder Street", "Portland", "OR", "97205"),
    (3, "812 Marine Drive, Suite 300", "Seattle", "WA", "98104"),
    (4, "45 Mercer Street, Floor 3", "New York", "NY", "10013"),
    (5, "1520 Harborview Way", "San Diego", "CA", "92101"),
    (6, "733 Greenhouse Lane", "Austin", "TX", "78704"),
    (7, "289 Vintner Row", "Napa", "CA", "94559"),
    (8, "1660 Lincoln Street, Suite 2100", "Denver", "CO", "80264"),
]


def seed_addresses():
    c = {"created": 0, "updated": 0, "skipped": 0}
    for org, street, city, region, postal in ADDRESSES:
        payload = {
            "organization": org,
            "name": "HQ",
            "street_address": street,
            "address_locality": city,
            "address_region": region,
            "postal_code": postal,
            "address_country": "US",
            "is_primary_billing": True,
        }
        upsert("organization_addresses",
               eq("organization", org) + "&" + eq("name", "HQ"),
               payload, c)
    report("organization_addresses", c)


# ---------------------------------------------------------------- deal stages check

EXPECTED_STAGES = {
    "81fdea8c-ffd0-48b0-8816-ee76bbc28f04": ("Lead", 1),
    "cc8f1d39-cc6e-4e76-b83c-04caa601eec0": ("Qualified", 2),
    "0ba6c5e9-1b90-450a-8033-a996224aa54b": ("Proposal", 3),
    "58707423-12f0-42a4-9d9f-9051816a5bd1": ("Negotiation", 4),
    "01668fb5-ecbb-4ad6-8518-bfc06fd25887": ("Won", 5),
}


def verify_deal_stages():
    status, res = get("/items/os_deal_stages?fields=id,name,sort&limit=-1")
    rows = res.get("data", []) if status == 200 else []
    by_id = {r["id"]: r for r in rows}
    ok = True
    for sid, (name, sort) in EXPECTED_STAGES.items():
        r = by_id.get(sid)
        if not r or r.get("name") != name or r.get("sort") != sort:
            ok = False
            print(f"os_deal_stages MISMATCH for {name}: {r}")
    print(f"os_deal_stages: {len(rows)} rows, expected 5 present with sort 1-5: {'OK' if ok and len(rows) == 5 else 'CHECK'}")


# ---------------------------------------------------------------- settings folder root

def set_org_folder_root():
    manifest_path = os.path.join(SCRIPT_DIR, "assets-manifest.json")
    if not os.path.exists(manifest_path):
        print("os_settings.organization_folder_root: assets-manifest.json not readable, left unset")
        return
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        branding = manifest.get("folders", {}).get("Branding")
    except Exception as e:
        print(f"os_settings.organization_folder_root: manifest unreadable ({e}), left unset")
        return
    if not branding:
        print("os_settings.organization_folder_root: no Branding folder in manifest, left unset")
        return
    status, res = get("/items/os_settings")
    current = (res.get("data") or {}).get("organization_folder_root") if status == 200 else None
    if current == branding:
        print("os_settings.organization_folder_root: already set to Branding folder, skipped")
        return
    if current:
        print(f"os_settings.organization_folder_root: already set to {current}, NOT overwriting (add-only)")
        return
    status, res = request("PATCH", "/items/os_settings", {"organization_folder_root": branding})
    if status == 200:
        print(f"os_settings.organization_folder_root: set to Branding folder {branding}")
    else:
        print(f"os_settings.organization_folder_root: PATCH failed {status} {res}")


# ---------------------------------------------------------------- verification

REST_PROJECTION = (
    "/items/os_products?fields=id,name,status,delivered_date,contract_end_date,"
    "access_url,assets,organization.id,organization.name,source_project.id,"
    "source_project.name,maintained_by.id,maintained_by.name&limit=5"
)

GQL_WITH_MAINTAINED = """
query { os_products(limit: 5) { id name status delivered_date contract_end_date
access_url assets organization { id name } source_project { id name }
maintained_by { id name } } }
"""

GQL_WITHOUT_MAINTAINED = """
query { os_products(limit: 5) { id name status delivered_date contract_end_date
access_url assets organization { id name } source_project { id name } } }
"""


def graphql(query):
    return request("POST", "/graphql", {"query": query})


def verify():
    print("--- VERIFY ---")
    status, res = get(REST_PROJECTION)
    n = len(res.get("data", [])) if status == 200 else 0
    print(f"REST products projection (with maintained_by): HTTP {status}, rows {n}")
    if status != 200:
        print(f"REST projection error body: {json.dumps(res)[:300]}")

    status, res = graphql(GQL_WITH_MAINTAINED)
    errs = res.get("errors")
    if status == 200 and not errs:
        rows = res["data"]["os_products"]
        print(f"GraphQL products probe (with maintained_by): HTTP 200, rows {len(rows)}, errors none")
        for r in rows:
            mb = (r.get("maintained_by") or {}).get("name")
            print(f"  {r['name']} | {r['status']} | delivered {r['delivered_date']} | "
                  f"contract_end {r['contract_end_date']} | org {r['organization']['name']} | "
                  f"src {r['source_project']['name']} | maintained_by {mb}")
    else:
        print(f"GraphQL with maintained_by failed (HTTP {status}): {json.dumps(errs or res)[:300]}")
        status2, res2 = graphql(GQL_WITHOUT_MAINTAINED)
        errs2 = res2.get("errors")
        rows2 = (res2.get("data") or {}).get("os_products", []) if status2 == 200 else []
        print(f"GraphQL fallback without maintained_by: HTTP {status2}, rows {len(rows2)}, "
              f"errors {'none' if not errs2 else json.dumps(errs2)[:200]}")

    for col in ["os_email_templates", "os_project_templates", "os_items",
                "os_products", "organization_addresses", "os_deal_stages"]:
        status, res = get(f"/items/{col}?aggregate[count]=*")
        cnt = res.get("data", [{}])[0].get("count") if status == 200 else f"ERR {status}"
        print(f"count {col}: {cnt}")


def main():
    verify_only = "--verify-only" in sys.argv
    if not verify_only:
        seed_email_templates()
        seed_project_templates()
        seed_items()
        seed_products()
        seed_addresses()
        verify_deal_stages()
        set_org_folder_root()
        link_maintained_by()
    verify()


if __name__ == "__main__":
    main()
