#!/usr/bin/env python3
"""Gap-fix seeding for the Muster demo portal (2026-07-16), wave 2.

Fixes three adversarial-verification failures:
  1. /employee-portal/tools: `tools` + `tools_projects` collections do not
     exist, so /api/portal/tools GraphQL 502s. Create both with the exact
     fields the route queries (app/api/portal/tools/route.ts), grant the demo
     policy read, seed 18 launchpad tools with brand colors, costs, renewal
     dates inside the next 90 days, and m2m project links. Paid staples get a
     mirrored os_expenses row linked via tools.expense.
  2. /employee-portal/help (and the client help center + support page): the
     help_collections + help_articles collections do not exist, so
     /api/portal/help/collections 502s. Create both, grant read, seed 6
     collections and 23 published markdown articles with mixed audience
     (all / employee / client).
  3. client-portal capture: demo@muster.dev is role Employee, so the
     client-portal layout bounces every /client-portal/* URL to the employee
     dashboard. Create a "Client" role attached to the SAME Demo Read-Only
     policy (no policy edits), a client demo user (client@muster.dev), a
     contact + organizations_contacts link into org 2 (Cedar & Co Coffee) so
     resolveOrganization works, and top up org-2 client-portal data:
     budget_cap (fill-null only), billable project expenses, four paid
     invoices spread across the last 90 days, and a project_links collection
     with client-visible links (dashboard OrgLinksHub + project detail).

Idempotent: collections/fields/relations/permissions checked before create;
rows upserted by natural key; PATCHes only fill NULL fields. Every seeded row
carries is_test_data: false where the field exists. Admin token is read from
~/elk-os/.env INSIDE this script and never printed. Output is counts, ids and
demo content names only.

Run: python3 ~/elk-os/provision/seed-full/gapfix-tools-help-client.py
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

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
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"  # Demo Read-Only

DEMO_EMAIL = "demo@muster.dev"        # public demo creds (landing page)
DEMO_PASS = "muster-demo"
CLIENT_EMAIL = "client@muster.dev"    # new client-role demo user (this script)
CLIENT_PASS = "muster-demo"

ORG_CEDAR = 2
PROJ_CEDAR_WEB = "430df3e9-7f6d-4369-81cf-d9e5dc0fab00"   # Cedar Website Redesign
PROJ_CEDAR_WHOLESALE = "a42f4921-7747-4319-b09e-644f639e89c5"
PROJ_NORTHLIGHT_BRAND = "91528c06-daee-41eb-b614-363afb1eb531"
PROJ_NORTHLIGHT_SEO = "193e5bd8-e9b2-471e-91e9-7c19aa2a2c7a"
PROJ_VELLUM_PORTFOLIO = "4ae1d3fa-92fb-443d-86c8-4636df95e41c"
PROJ_VELLUM_MOTION = "b9a8afa7-7138-4b3d-84cc-407e6d28f0dc"
PROJ_HARBOR_BOOKING = "d16e4ef5-a11c-4165-8f5b-2a79fa1a1e51"
PROJ_BLOOM_SHOPIFY = "3d5677cf-af08-4df2-a29a-6a4925ab9268"
PROJ_STERLING_RES = "cd1eae58-ec99-4444-bbe4-ae6ab9370cea"
PROJ_MERIDIAN_GRANT = "c6581803-8fe8-43e7-bb56-4f1e758e2a25"


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

# ---------------------------------------------------------------- helpers

def choices(vals):
    return [{"text": str(v).replace("_", " ").replace("-", " ").title(), "value": v} for v in vals]


def pk_uuid():
    return {"field": "id", "type": "uuid",
            "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
            "schema": {"is_primary_key": True, "length": 36, "has_auto_increment": False}}


def pk_int():
    return {"field": "id", "type": "integer",
            "meta": {"hidden": True, "readonly": True, "interface": "input"},
            "schema": {"is_primary_key": True, "has_auto_increment": True}}


def f_string(name, opts=None, default=None):
    meta = {"interface": "select-dropdown", "options": {"choices": choices(opts)}} if opts \
        else {"interface": "input"}
    schema = {"default_value": default} if default is not None else {}
    return {"field": name, "type": "string", "meta": meta, "schema": schema}


def f_text(name, md=False):
    iface = "input-rich-text-md" if md else "input-multiline"
    return {"field": name, "type": "text", "meta": {"interface": iface}, "schema": {}}


def f_decimal(name):
    return {"field": name, "type": "decimal", "meta": {"interface": "input"},
            "schema": {"numeric_precision": 10, "numeric_scale": 2}}


def f_int(name):
    return {"field": name, "type": "integer", "meta": {"interface": "input"}, "schema": {}}


def f_bool(name, default=False):
    return {"field": name, "type": "boolean", "meta": {"interface": "boolean"},
            "schema": {"default_value": default}}


def f_date(name):
    return {"field": name, "type": "date", "meta": {"interface": "datetime"}, "schema": {}}


def f_m2o_uuid(name):
    return {"field": name, "type": "uuid",
            "meta": {"interface": "select-dropdown-m2o", "special": ["m2o"]}, "schema": {}}


def f_m2o_int(name):
    return {"field": name, "type": "integer",
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


def ensure_relation(collection, field, related, one_field=None, junction_field=None,
                    on_delete="SET NULL"):
    st, _ = req(f"/relations/{collection}/{field}")
    if st == 200:
        return False
    meta = {"one_field": one_field, "sort_field": None}
    if junction_field:
        meta["junction_field"] = junction_field
    st, data = req("/relations", "POST", {
        "collection": collection,
        "field": field,
        "related_collection": related,
        "meta": meta,
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
    q = "&".join(f"filter[{k}][_eq]={urllib.parse.quote(str(v))}"
                 for k, v in natural_filter.items())
    st, data = req(f"/items/{collection}?{q}&fields=id&limit=1")
    die_on(st, data, f"search {collection}")
    if data["data"]:
        return data["data"][0]["id"], False
    st, data = req(f"/items/{collection}", "POST", payload)
    die_on(st, data, f"create {collection} row")
    return data["data"]["id"], True


# =====================================================================
# 1. TOOLS: collections + relations + permission + rows
# =====================================================================
print("== 1. tools launchpad ==")

TOOL_CATEGORIES = ["ORGANIZATION", "SERVER", "DESIGN", "DATABASE_PROVIDER",
                   "AUTHENTICATION", "LLM_SERVICE", "MONITORING", "EMAIL_SERVICE",
                   "COMMUNICATION", "ANALYTICS", "CI_CD", "STORAGE", "CDN",
                   "DOMAIN_REGISTRY", "VERSION_CONTROL", "OTHER"]

ensure_collection("tools", "handyman", "SaaS tool / subscription launchpad (demo)", [
    pk_uuid(),
    f_string("name"),
    f_string("category", TOOL_CATEGORIES),
    f_text("description"),
    f_string("website"),
    f_string("login_url"),
    f_decimal("cost"),
    f_string("billing_cycle", ["monthly", "yearly", "one-time"]),
    f_bool("is_subscription"),
    f_bool("has_subscription"),
    f_date("renewal_date"),
    f_date("start_date"),
    f_bool("auto_renew"),
    f_string("account_email"),
    f_string("vendor"),
    f_string("icon"),
    f_string("color"),
    f_text("notes"),
    f_bool("frequently_used"),
    f_string("status", ["published", "archived"], default="published"),
    f_bool("is_test_data"),
    f_created(),
    f_updated(),
])
ensure_field("tools", f_m2o_uuid("expense"))
ensure_relation("tools", "expense", "os_expenses")

ensure_collection("tools_projects", "link", "tools <-> os_projects junction (demo)", [
    pk_int(),
    f_m2o_uuid("tools_id"),
    f_m2o_uuid("project_id"),
])
ensure_field("tools", {"field": "projects", "type": "alias",
                       "meta": {"interface": "list-m2m", "special": ["m2m"]},
                       "schema": None})
ensure_relation("tools_projects", "tools_id", "tools",
                one_field="projects", junction_field="project_id", on_delete="CASCADE")
ensure_relation("tools_projects", "project_id", "os_projects",
                junction_field="tools_id", on_delete="CASCADE")

ensure_read_permission("tools")
ensure_read_permission("tools_projects")

# name, category, vendor, color, website, login_url, cost, cycle, renewal,
# frequently_used, description, projects
TOOLS = [
    ("GitHub", "VERSION_CONTROL", "GitHub", "#181717", "https://github.com",
     "https://github.com/login", 48.00, "monthly", "2026-08-04", True,
     "Git hosting, pull requests, and code review for every client build.",
     [PROJ_CEDAR_WEB, PROJ_CEDAR_WHOLESALE, PROJ_HARBOR_BOOKING, PROJ_MERIDIAN_GRANT]),
    ("Netlify", "SERVER", "Netlify", "#00C7B7", "https://www.netlify.com",
     "https://app.netlify.com", 99.00, "monthly", "2026-07-28", True,
     "Static hosting and deploy previews for marketing and portfolio sites.",
     [PROJ_CEDAR_WEB, PROJ_BLOOM_SHOPIFY, PROJ_VELLUM_PORTFOLIO]),
    ("Neon", "DATABASE_PROVIDER", "Neon", "#00E599", "https://neon.tech",
     "https://console.neon.tech", 69.00, "monthly", "2026-08-01", False,
     "Serverless Postgres behind the wholesale portal and booking apps.",
     [PROJ_CEDAR_WHOLESALE, PROJ_HARBOR_BOOKING, PROJ_MERIDIAN_GRANT]),
    ("Figma", "DESIGN", "Figma", "#F24E1E", "https://www.figma.com",
     "https://www.figma.com/login", 540.00, "yearly", "2026-09-12", True,
     "Design files, prototypes, and brand libraries for all studio work.",
     [PROJ_NORTHLIGHT_BRAND, PROJ_VELLUM_PORTFOLIO, PROJ_CEDAR_WEB]),
    ("Resend", "EMAIL_SERVICE", "Resend", "#0F0F0F", "https://resend.com",
     "https://resend.com/login", 20.00, "monthly", "2026-07-25", False,
     "Transactional email API for reservation and order notifications.",
     [PROJ_STERLING_RES, PROJ_CEDAR_WHOLESALE]),
    ("Matomo Cloud", "ANALYTICS", "Matomo", "#3152A0", "https://matomo.org",
     "https://demo-agency.matomo.cloud", 29.00, "monthly", "2026-08-09", False,
     "Privacy-first web analytics for client sites and SEO retainers.",
     [PROJ_CEDAR_WEB, PROJ_NORTHLIGHT_SEO]),
    ("AWS", "SERVER", "Amazon Web Services", "#FF9900", "https://aws.amazon.com",
     "https://console.aws.amazon.com", 214.37, "monthly", "2026-08-03", False,
     "EC2, S3, and Route 53 for the grant portal and booking backends.",
     [PROJ_MERIDIAN_GRANT, PROJ_HARBOR_BOOKING]),
    ("Cloudflare", "CDN", "Cloudflare", "#F38020", "https://www.cloudflare.com",
     "https://dash.cloudflare.com", 25.00, "monthly", "2026-08-15", False,
     "DNS, CDN, and WAF in front of ecommerce and reservation sites.",
     [PROJ_BLOOM_SHOPIFY, PROJ_STERLING_RES]),
    ("Anthropic API", "LLM_SERVICE", "Anthropic", "#D97757", "https://www.anthropic.com",
     "https://console.anthropic.com", 250.00, "monthly", "2026-07-31", False,
     "Claude API credits for document intake on the grant portal.",
     [PROJ_MERIDIAN_GRANT]),
    ("Sentry", "MONITORING", "Sentry", "#362D59", "https://sentry.io",
     "https://sentry.io/auth/login/", 29.00, "monthly", "2026-08-19", False,
     "Error tracking and release health for the app builds.",
     [PROJ_HARBOR_BOOKING, PROJ_CEDAR_WHOLESALE]),
    ("Slack", "COMMUNICATION", "Slack", "#4A154B", "https://slack.com",
     "https://muster-demo.slack.com", 87.50, "monthly", "2026-08-06", True,
     "Team chat, client channels, and deploy notifications.", []),
    ("Notion", "ORGANIZATION", "Notion", "#111111", "https://www.notion.so",
     "https://www.notion.so/login", 96.00, "monthly", "2026-07-30", False,
     "Internal wiki, meeting notes, and process documentation.", []),
    ("1Password", "AUTHENTICATION", "1Password", "#0094F5", "https://1password.com",
     "https://my.1password.com", 19.95, "monthly", "2026-08-22", False,
     "Shared vaults for client credentials and service accounts.", []),
    ("Namecheap", "DOMAIN_REGISTRY", "Namecheap", "#DE3723", "https://www.namecheap.com",
     "https://www.namecheap.com/myaccount/login/", 156.00, "yearly", "2026-09-28", False,
     "Domain registration and renewals for client properties.", []),
    ("Backblaze B2", "STORAGE", "Backblaze", "#E21E29", "https://www.backblaze.com",
     "https://secure.backblaze.com/user_signin.htm", 12.40, "monthly", "2026-08-11", False,
     "Offsite object storage for footage and project archives.",
     [PROJ_VELLUM_MOTION]),
    ("CircleCI", "CI_CD", "CircleCI", "#343434", "https://circleci.com",
     "https://app.circleci.com", 30.00, "monthly", "2026-08-25", False,
     "CI pipelines for the booking app test suite.", [PROJ_HARBOR_BOOKING]),
    ("Google Search Console", "ANALYTICS", "Google", "#458CF5",
     "https://search.google.com/search-console",
     "https://search.google.com/search-console", None, None, None, False,
     "Index coverage and query data for SEO retainers.",
     [PROJ_NORTHLIGHT_SEO, PROJ_CEDAR_WEB]),
    ("Excalidraw", "DESIGN", "Excalidraw", "#6965DB", "https://excalidraw.com",
     "https://excalidraw.com", None, None, None, False,
     "Quick architecture sketches and workshop whiteboards.", []),
]

# Paid staples that mirror an os_expenses row (tool-expense-sync engine shape).
EXPENSE_MIRRORS = {
    "Netlify": ("monthly",),
    "Neon": ("monthly",),
    "Figma": ("yearly",),
    "Anthropic API": ("monthly",),
    "Slack": ("monthly",),
}

created = updated = skipped = 0
tool_ids = {}
for (name, cat, vendor, color, website, login_url, cost, cycle, renewal,
     freq, desc, projects) in TOOLS:
    payload = {
        "name": name, "category": cat, "vendor": vendor, "color": color,
        "website": website, "login_url": login_url, "description": desc,
        "cost": cost, "billing_cycle": cycle, "renewal_date": renewal,
        "is_subscription": bool(cost and cycle in ("monthly", "yearly")),
        "has_subscription": name in EXPENSE_MIRRORS,
        "auto_renew": bool(cost), "frequently_used": freq,
        "account_email": "ops@muster.dev", "start_date": "2026-01-05",
        "status": "published", "is_test_data": False,
    }
    tid, was_created = upsert("tools", {"name": name}, payload)
    tool_ids[name] = tid
    if was_created:
        created += 1
    else:
        skipped += 1
print(f"tools: created {created} / skipped {skipped} (existing)")

jc = js = 0
for (name, _cat, _v, _c, _w, _l, _cost, _cy, _r, _f, _d, projects) in TOOLS:
    for pid in projects:
        _, was_created = upsert(
            "tools_projects",
            {"tools_id": tool_ids[name], "project_id": pid},
            {"tools_id": tool_ids[name], "project_id": pid})
        if was_created:
            jc += 1
        else:
            js += 1
print(f"tools_projects: created {jc} / skipped {js}")

ec = es = 0
for name, (interval,) in EXPENSE_MIRRORS.items():
    row = next(t for t in TOOLS if t[0] == name)
    cost, renewal, vendor = row[6], row[8], row[2]
    exp_payload = {
        "name": f"{name} subscription", "vendor": vendor, "category": "software",
        "billing_term": "recurring", "recurrence_interval": interval,
        "next_billing_date": renewal, "cost": cost, "status": "approved",
        "is_billable": False, "is_reimbursable": False, "is_test_data": False,
        "date": "2026-07-01T09:00:00Z", "notify_on_renewal": True,
        "notify_days_before": 7,
        "description": f"Auto-synced from the {name} tool card (demo).",
    }
    eid, was_created = upsert("os_expenses", {"name": f"{name} subscription"}, exp_payload)
    if was_created:
        ec += 1
    else:
        es += 1
    # Link tool -> expense only when currently NULL (never rewrite).
    st, data = req(f"/items/tools/{tool_ids[name]}?fields=expense")
    die_on(st, data, "read tool expense link")
    if data["data"].get("expense") is None:
        st, data = req(f"/items/tools/{tool_ids[name]}", "PATCH", {"expense": eid})
        die_on(st, data, f"link expense for {name}")
print(f"os_expenses (tool mirrors): created {ec} / skipped {es}")

# =====================================================================
# 2. HELP CENTER: collections + permission + rows
# =====================================================================
print("== 2. help center ==")

ensure_collection("help_collections", "help", "Help center shelves (demo)", [
    pk_int(),
    f_string("title"),
    f_string("slug"),
    f_text("description"),
    f_string("icon"),
    f_int("sort"),
])
ensure_collection("help_articles", "article", "Help center articles (demo)", [
    pk_int(),
    f_string("title"),
    f_string("slug"),
    f_text("summary"),
    f_text("content", md=True),
    f_string("audience", ["all", "employee", "client"], default="all"),
    f_string("status", ["published", "draft", "archived"], default="published"),
    f_int("sort"),
    f_created(),
    f_updated(),
])
ensure_field("help_articles", f_m2o_int("help_collection"))
ensure_relation("help_articles", "help_collection", "help_collections")

ensure_read_permission("help_collections")
ensure_read_permission("help_articles")

HELP_COLLECTIONS = [
    ("Getting Started", "getting-started", "rocket_launch", 1,
     "Your first steps in the portal: signing in, finding your way around, and setting up your account."),
    ("Delivery and Tasks", "delivery-and-tasks", "checklist", 2,
     "How work moves from request to done: tasks, sprints, deliverables, and approvals."),
    ("CRM", "crm", "groups", 3,
     "Organizations, contacts, deals, and activity tracking for the sales pipeline."),
    ("Billing and Invoices", "billing-and-invoices", "receipt_long", 4,
     "Invoices, payments, subscriptions, and how billing statuses work."),
    ("Analytics", "analytics", "monitoring", 5,
     "Traffic reports, workflow activity, and usage dashboards explained."),
    ("Administration", "administration", "admin_panel_settings", 6,
     "Team management, roles, notifications, and data controls."),
]

hc_created = hc_skipped = 0
hc_ids = {}
for title, slug, icon, sort, desc in HELP_COLLECTIONS:
    cid, was_created = upsert("help_collections", {"slug": slug}, {
        "title": title, "slug": slug, "icon": icon, "sort": sort, "description": desc})
    hc_ids[slug] = cid
    if was_created:
        hc_created += 1
    else:
        hc_skipped += 1
print(f"help_collections: created {hc_created} / skipped {hc_skipped}")

def art(collection_slug, title, slug, audience, sort, summary, content):
    return (collection_slug, title, slug, audience, sort, summary, content)

HELP_ARTICLES = [
    # Getting Started
    art("getting-started", "Welcome to the portal", "welcome-to-the-portal", "all", 1,
        "What the portal is for and what you can do here.",
        "## Welcome\n\nThe portal is the single place where projects, tasks, invoices, and updates live.\n\n"
        "- **Dashboard** gives you a snapshot of active work and anything waiting on you.\n"
        "- **Projects** shows scope, timelines, and progress for every engagement.\n"
        "- **Invoices** keeps your billing history and open balances in one place.\n\n"
        "Use the search bar at the top of any page (or press Cmd+K) to jump straight to a project, task, or invoice."),
    art("getting-started", "Signing in and account basics", "signing-in-and-account-basics", "all", 2,
        "Password sign-in, magic links, and updating your profile.",
        "## Signing in\n\nYou can sign in with your email and password, or request a magic link if you prefer not to type a password.\n\n"
        "## Your profile\n\nOpen **Settings** from the sidebar to update your name, avatar, and notification preferences.\n\n"
        "If you get locked out, use the password reset link on the login page. Reset emails arrive within a minute."),
    art("getting-started", "Navigating your dashboard", "navigating-your-dashboard", "all", 3,
        "A tour of the metric cards, timeline chart, and recent activity feed.",
        "## The dashboard\n\nThe cards along the top summarize active projects, open tasks, and invoices that need attention.\n\n"
        "The **Project Timeline** chart plots invoice due dates against project deadlines over the last three months, so you can see busy weeks at a glance.\n\n"
        "**Recent Activity** lists the latest completed tasks, shipped releases, and posted updates across your projects."),
    art("getting-started", "Inviting teammates", "inviting-teammates", "employee", 4,
        "How employee accounts are provisioned and what access they get.",
        "## Adding a teammate\n\nEmployee accounts are provisioned by an administrator from the Directus admin panel.\n\n"
        "1. Create the user with their work email.\n"
        "2. Assign the **Employee** role.\n"
        "3. Ask them to sign in and set a password via the reset flow.\n\n"
        "Employees see every organization and project. Client users only ever see their own organization's data."),
    # Delivery and Tasks
    art("delivery-and-tasks", "How tasks flow from request to done", "task-flow-request-to-done", "all", 1,
        "The five task statuses and what each one means.",
        "## Task lifecycle\n\nEvery task moves through the same five statuses:\n\n"
        "1. **Pending**: captured, not yet scheduled.\n"
        "2. **Active**: committed to the current cycle.\n"
        "3. **In progress**: someone is working on it now.\n"
        "4. **In review**: finished, awaiting review or approval.\n"
        "5. **Completed**: done and verified.\n\n"
        "Tasks marked visible to clients appear in the client portal task list as soon as they are created."),
    art("delivery-and-tasks", "Sprint boards explained", "sprint-boards-explained", "employee", 2,
        "Reading the board columns, points, and sprint burndown.",
        "## The board\n\nThe sprint board groups tasks by status column. Drag a card to change its status; the change is saved immediately.\n\n"
        "**Points** follow the Fibonacci scale (1, 2, 3, 5, 8, 13, 21) and feed the sprint capacity line.\n\n"
        "Use the sprint selector in the toolbar to review past sprints and their completion rates."),
    art("delivery-and-tasks", "Approving deliverables", "approving-deliverables", "client", 3,
        "How to review, approve, or request changes on a deliverable.",
        "## Reviewing a deliverable\n\nWhen the team submits a deliverable, it appears on your project page with a **Pending review** badge.\n\n"
        "- Open the deliverable link to see the work.\n"
        "- Click **Approve** if it is ready.\n"
        "- Click **Request changes** and leave a comment if it needs another pass.\n\n"
        "Every decision is recorded with a timestamp so both sides share the same history."),
    art("delivery-and-tasks", "Task priorities and points", "task-priorities-and-points", "employee", 4,
        "P0 through P3 definitions and how estimates are set.",
        "## Priorities\n\n- **P0**: drop everything, production is affected.\n- **P1**: needed this sprint.\n"
        "- **P2**: normal backlog priority.\n- **P3**: nice to have.\n\n"
        "## Points\n\nEstimate effort, not time. A 1 is a trivial change; a 21 should almost always be split before it enters a sprint."),
    # CRM
    art("crm", "Organizations and contacts", "organizations-and-contacts", "employee", 1,
        "The two core CRM records and how they link together.",
        "## Structure\n\n**Organizations** are companies; **contacts** are people. A contact can belong to several organizations through the membership link.\n\n"
        "Open an organization to see its projects, invoices, deals, and every contact associated with it.\n\n"
        "Keep emails current: portal access for client users is resolved through the contact's email address."),
    art("crm", "Tracking deals through stages", "tracking-deals-through-stages", "employee", 2,
        "Pipeline stages and keeping deal values honest.",
        "## The pipeline\n\nDeals move across five stages from first contact to closed. Drag a deal card between columns to update its stage.\n\n"
        "Record the expected value and close date on every deal; the pipeline totals on the deals page and dashboard are computed from those fields.\n\n"
        "Mark a deal **Closed Won** to convert it into project kickoff work."),
    art("crm", "Logging activities and meetings", "logging-activities-and-meetings", "employee", 3,
        "Why every call and meeting belongs in the activity log.",
        "## Log it or it did not happen\n\nUse **Activities** to record calls, meetings, and emails against an organization or deal.\n\n"
        "Activities show up on the organization timeline and roll into the workflow activity feed, which is what the dashboard chart reads.\n\n"
        "Attach contacts to each activity so follow-ups land with the right person."),
    art("crm", "Linking contacts to projects", "linking-contacts-to-projects", "employee", 4,
        "Project contacts drive updates and portal visibility.",
        "## Project contacts\n\nAdd contacts to a project to define who receives updates and who can see the project in the client portal.\n\n"
        "The primary contact is the default recipient for invoice and update notifications."),
    # Billing and Invoices
    art("billing-and-invoices", "Reading your invoice", "reading-your-invoice", "client", 1,
        "Line items, totals, and where to download a PDF.",
        "## Anatomy of an invoice\n\nEach invoice lists line items with quantities and unit prices, a subtotal, tax, and the total due.\n\n"
        "The **amount paid** and **amount due** figures update automatically as payments are recorded.\n\n"
        "Use the download button on the invoice page to save a PDF copy for your records."),
    art("billing-and-invoices", "Payment methods and receipts", "payment-methods-and-receipts", "client", 2,
        "How to pay an open invoice and find receipts.",
        "## Paying an invoice\n\nOpen invoices include a payment link. Card and bank transfer payments are recorded within minutes; a receipt is emailed automatically.\n\n"
        "Past receipts live on the **Payments** tab of each invoice. If a payment does not appear after an hour, contact your project lead."),
    art("billing-and-invoices", "Invoice statuses explained", "invoice-statuses-explained", "all", 3,
        "Draft, submitted, paid, overdue, and what each means.",
        "## Statuses\n\n- **Draft**: being prepared, not yet payable.\n- **Submitted**: sent and awaiting payment.\n"
        "- **Paid**: settled in full.\n- **Overdue**: past its due date.\n- **Voided / cancelled / refunded**: no longer payable.\n\n"
        "Overdue invoices surface on the dashboard for both the team and the client until they are settled."),
    art("billing-and-invoices", "Recurring billing and subscriptions", "recurring-billing-and-subscriptions", "all", 4,
        "Fixed-term plans, renewals, and pausing a subscription.",
        "## Recurring invoices\n\nRetainers and hosting plans bill on a schedule. The subscription status on the invoice shows whether the plan is active, past due, or cancelled.\n\n"
        "Renewal reminders go out seven days before each billing date. To change or pause a plan, raise a support ticket from the portal."),
    # Analytics
    art("analytics", "Your website traffic report", "your-website-traffic-report", "client", 1,
        "Visits, page views, and where the numbers come from.",
        "## Traffic report\n\nThe analytics section shows visits, unique visitors, page views, and top pages for your site over the selected period.\n\n"
        "Data comes from a privacy-first analytics platform: no cookies, no personal data, and numbers typically appear within an hour of a visit.\n\n"
        "Use the period selector to compare the last 7, 30, or 90 days."),
    art("analytics", "Workflow activity chart", "workflow-activity-chart", "employee", 2,
        "What feeds the dashboard activity chart and how to read it.",
        "## The activity chart\n\nThe dashboard chart reads the workflow activity log: task completions, shipped releases, deploys, and posted updates.\n\n"
        "Spikes usually line up with sprint boundaries and release days. A quiet week on the chart with a busy board is a sign work is not being logged."),
    art("analytics", "AI token usage dashboard", "ai-token-usage-dashboard", "employee", 3,
        "Tracking assistant usage and cost per project.",
        "## Token usage\n\nThe AI usage tab meters assistant tokens per day and per project so costs stay predictable.\n\n"
        "Figures update daily. Use the project filter to see which engagements drive usage."),
    # Administration
    art("administration", "Managing team members and roles", "managing-team-members-and-roles", "employee", 1,
        "Roles in the demo workspace and what each can access.",
        "## Roles\n\n- **Administrator**: full access, including the CMS admin panel.\n"
        "- **Employee**: every portal section across all organizations.\n"
        "- **Client**: read-only view of their own organization's projects, invoices, and updates.\n\n"
        "Role changes are made in the CMS by an administrator and take effect on next sign-in."),
    art("administration", "Demo data and test accounts", "demo-data-and-test-accounts", "employee", 2,
        "How the demo workspace is seeded and reset.",
        "## Demo workspace\n\nThis workspace is populated with fictional organizations, projects, and billing history so every section shows realistic data.\n\n"
        "The demo sign-ins are read-only by policy: browsing is unrestricted, while create, edit, and delete actions are blocked."),
    art("administration", "Notification settings", "notification-settings", "all", 3,
        "Choosing what lands in your inbox versus the in-app feed.",
        "## Notifications\n\nOpen **Settings** and choose which events email you: task assignments, deliverable approvals, invoice activity, and weekly digests.\n\n"
        "In-app notifications always appear in the bell menu regardless of email preferences."),
    art("administration", "Data export and backups", "data-export-and-backups", "employee", 4,
        "Nightly backups and how to export collections.",
        "## Backups\n\nThe CMS database is backed up nightly and retained for 30 days.\n\n"
        "For one-off exports, any collection view in the admin panel can be exported to CSV or JSON with the current filters applied."),
]

ha_created = ha_skipped = 0
for coll_slug, title, slug, audience, sort, summary, content in HELP_ARTICLES:
    _, was_created = upsert("help_articles", {"slug": slug}, {
        "title": title, "slug": slug, "summary": summary, "content": content,
        "audience": audience, "sort": sort, "status": "published",
        "help_collection": hc_ids[coll_slug]})
    if was_created:
        ha_created += 1
    else:
        ha_skipped += 1
print(f"help_articles: created {ha_created} / skipped {ha_skipped}")

# =====================================================================
# 3. PROJECT LINKS: collection + permission + rows
# =====================================================================
print("== 3. project_links ==")

ensure_collection("project_links", "link", "Important links per project (demo)", [
    pk_int(),
    f_string("type", ["frontend", "cms", "analytics", "repository", "hosting",
                      "database", "staging", "other"]),
    f_string("label"),
    f_string("url"),
    f_text("notes"),
    f_int("sort"),
    f_string("role_visibility", ["client_only", "internal_only", "both"], default="both"),
    f_string("status", ["published", "draft", "archived"], default="published"),
    f_bool("is_test_data"),
])
ensure_field("project_links", f_m2o_uuid("project"))
ensure_relation("project_links", "project", "os_projects", on_delete="CASCADE")
ensure_read_permission("project_links")

LINKS = [
    (PROJ_CEDAR_WEB, "frontend", "Live site", "https://cedarandco.example", "both", 1),
    (PROJ_CEDAR_WEB, "staging", "Staging preview", "https://staging.cedarandco.example", "both", 2),
    (PROJ_CEDAR_WEB, "cms", "Content editor", "https://cms.cedarandco.example", "both", 3),
    (PROJ_CEDAR_WEB, "repository", "GitHub repository", "https://github.com/muster-demo/cedar-website", "internal_only", 4),
    (PROJ_CEDAR_WEB, "analytics", "Traffic dashboard", "https://analytics.muster.dev/?idSite=2", "both", 5),
    (PROJ_CEDAR_WHOLESALE, "frontend", "Wholesale portal (beta)", "https://wholesale.cedarandco.example", "both", 1),
    (PROJ_CEDAR_WHOLESALE, "repository", "GitHub repository", "https://github.com/muster-demo/cedar-wholesale", "internal_only", 2),
    (PROJ_CEDAR_WHOLESALE, "database", "Neon console", "https://console.neon.tech/app/projects/cedar-wholesale", "internal_only", 3),
    (PROJ_BLOOM_SHOPIFY, "frontend", "Storefront", "https://bloombotanicals.example", "both", 1),
    (PROJ_BLOOM_SHOPIFY, "hosting", "Shopify admin", "https://admin.shopify.com/store/bloom-botanicals-demo", "internal_only", 2),
    (PROJ_HARBOR_BOOKING, "staging", "TestFlight build", "https://testflight.apple.com/join/harbor-demo", "both", 1),
    (PROJ_HARBOR_BOOKING, "repository", "GitHub repository", "https://github.com/muster-demo/harbor-booking", "internal_only", 2),
    (PROJ_NORTHLIGHT_SEO, "analytics", "SEO dashboard", "https://analytics.muster.dev/?idSite=3", "both", 1),
]

pl_created = pl_skipped = 0
for pid, ltype, label, url, vis, sort in LINKS:
    _, was_created = upsert("project_links", {"project": pid, "label": label}, {
        "project": pid, "type": ltype, "label": label, "url": url,
        "role_visibility": vis, "status": "published", "sort": sort,
        "is_test_data": False})
    if was_created:
        pl_created += 1
    else:
        pl_skipped += 1
print(f"project_links: created {pl_created} / skipped {pl_skipped}")

# =====================================================================
# 4. CLIENT DEMO SESSION: role + access + user + contact + org link
# =====================================================================
print("== 4. client demo session ==")

# 4a. Client role (new role; existing roles/policies untouched).
st, data = req("/roles?filter[name][_eq]=Client&fields=id,name")
die_on(st, data, "list roles")
if data["data"]:
    client_role = data["data"][0]["id"]
    print(f"  role Client: exists ({client_role})")
else:
    st, data = req("/roles", "POST", {
        "name": "Client", "icon": "supervised_user_circle",
        "description": "Demo client role. Read-only via the Demo Read-Only policy."})
    die_on(st, data, "create Client role")
    client_role = data["data"]["id"]
    print(f"  role Client: CREATED ({client_role})")

# 4b. Attach the EXISTING Demo Read-Only policy to the new role (additive
# directus_access row; the policy itself is not modified).
st, data = req(f"/access?filter[role][_eq]={client_role}&filter[policy][_eq]={DEMO_POLICY}&fields=id")
die_on(st, data, "list access")
if data["data"]:
    print("  access Client -> Demo Read-Only: exists")
else:
    st, data = req("/access", "POST", {"role": client_role, "policy": DEMO_POLICY})
    die_on(st, data, "attach policy to Client role")
    print("  access Client -> Demo Read-Only: CREATED")

# 4c. Client demo user.
st, data = req(f"/users?filter[email][_eq]={urllib.parse.quote(CLIENT_EMAIL)}&fields=id,email,role")
die_on(st, data, "list users")
if data["data"]:
    client_user = data["data"][0]["id"]
    print(f"  user {CLIENT_EMAIL}: exists ({client_user})")
else:
    st, data = req("/users", "POST", {
        "email": CLIENT_EMAIL, "password": CLIENT_PASS, "role": client_role,
        "first_name": "Rowan", "last_name": "Ashford",
        "title": "Owner, Cedar & Co Coffee", "status": "active",
        "is_test_data": False, "test_only": False})
    die_on(st, data, "create client user")
    client_user = data["data"]["id"]
    print(f"  user {CLIENT_EMAIL}: CREATED ({client_user})")

# 4d. Contact row wired to the user (resolveOrganization strategies 2 + 3).
contact_id, was_created = upsert("contacts", {"email": CLIENT_EMAIL}, {
    "first_name": "Rowan", "last_name": "Ashford", "email": CLIENT_EMAIL,
    "job_title": "Owner", "status": "active", "user": client_user,
    "is_test_data": False})
print(f"  contact {CLIENT_EMAIL}: {'CREATED' if was_created else 'exists'} ({contact_id})")
# Fill the user FK if the contact pre-existed without it (fill-null only).
st, data = req(f"/items/contacts/{contact_id}?fields=user")
die_on(st, data, "read contact user FK")
if data["data"].get("user") is None:
    st, data = req(f"/items/contacts/{contact_id}", "PATCH", {"user": client_user})
    die_on(st, data, "link contact.user")
    print("  contact.user FK: LINKED")

# 4e. Membership junction into Cedar & Co Coffee (org 2).
_, was_created = upsert("organizations_contacts",
                        {"organizations_id": ORG_CEDAR, "contacts_id": contact_id},
                        {"organizations_id": ORG_CEDAR, "contacts_id": contact_id})
print(f"  organizations_contacts org{ORG_CEDAR}<->contact: {'CREATED' if was_created else 'exists'}")

# =====================================================================
# 5. ORG 2 CLIENT-PORTAL TOP-UP: budget caps, billable expenses, invoices
# =====================================================================
print("== 5. org 2 top-up ==")

# 5a. budget_cap: fill-null only, never rewrite an existing value.
for pid, cap in [(PROJ_CEDAR_WEB, "24000.00"), (PROJ_CEDAR_WHOLESALE, "18000.00")]:
    st, data = req(f"/items/os_projects/{pid}?fields=budget_cap,name")
    die_on(st, data, "read project budget_cap")
    if data["data"].get("budget_cap") is None:
        st, d2 = req(f"/items/os_projects/{pid}", "PATCH", {"budget_cap": cap})
        die_on(st, d2, "set budget_cap")
        print(f"  budget_cap {data['data']['name']}: SET {cap}")
    else:
        print(f"  budget_cap {data['data']['name']}: already set")

# 5b. Billable expenses on the two Cedar projects (BudgetBurnCard fuel).
ORG2_EXPENSES = [
    (PROJ_CEDAR_WEB, "Stock photography license", "marketing", 340.00,
     "2026-05-22T10:00:00Z", "paid", "Twelve hero and menu images for the redesign."),
    (PROJ_CEDAR_WEB, "Commercial font licensing", "software", 199.00,
     "2026-06-03T10:00:00Z", "approved", "Web license for the display typeface."),
    (PROJ_CEDAR_WEB, "Netlify build minutes overage", "software", 45.00,
     "2026-06-28T10:00:00Z", "paid", "Preview deploy overage during launch week."),
    (PROJ_CEDAR_WHOLESALE, "Neon Postgres project tier", "software", 69.00,
     "2026-06-01T10:00:00Z", "paid", "Dedicated database branch for the wholesale portal."),
    (PROJ_CEDAR_WHOLESALE, "Address validation API credits", "software", 120.00,
     "2026-06-18T10:00:00Z", "approved", "Bulk validation for the wholesale account import."),
    (PROJ_CEDAR_WHOLESALE, "Load testing day pass", "professional_services", 85.00,
     "2026-07-02T10:00:00Z", "submitted", "Checkout flow load test before beta invite."),
]
oe_created = oe_skipped = 0
for pid, name, cat, cost, date, status, desc in ORG2_EXPENSES:
    _, was_created = upsert("os_expenses", {"name": name, "project": pid}, {
        "name": name, "project": pid, "category": cat, "cost": cost,
        "date": date, "status": status, "billing_term": "one_time",
        "is_billable": True, "is_reimbursable": False, "is_test_data": False,
        "vendor": "Muster (pass-through)", "description": desc})
    if was_created:
        oe_created += 1
    else:
        oe_skipped += 1
print(f"os_expenses (org2 billable): created {oe_created} / skipped {oe_skipped}")

# 5c. Paid invoices spread across the last 90 days (dashboard timeline chart).
ORG2_INVOICES = [
    ("INV-2026-421", PROJ_CEDAR_WEB, "2026-04-14", "2026-04-28", 2800.00),
    ("INV-2026-422", PROJ_CEDAR_WHOLESALE, "2026-05-05", "2026-05-19", 3450.00),
    ("INV-2026-423", PROJ_CEDAR_WEB, "2026-05-26", "2026-06-09", 5200.00),
    ("INV-2026-424", PROJ_CEDAR_WHOLESALE, "2026-06-16", "2026-06-30", 2150.00),
]
inv_created = inv_skipped = 0
for num, pid, issue, due, total in ORG2_INVOICES:
    _, was_created = upsert("os_invoices", {"invoice_number": num}, {
        "invoice_number": num, "organization": ORG_CEDAR, "project": pid,
        "status": "paid", "billing_type": "one_time",
        "issue_date": f"{issue}T00:00:00Z", "due_date": f"{due}T00:00:00Z",
        "subtotal": f"{total:.2f}", "total": f"{total:.2f}", "total_tax": "0.00",
        "amount_paid": f"{total:.2f}", "amount_due": "0.00",
        "is_test_data": False})
    if was_created:
        inv_created += 1
    else:
        inv_skipped += 1
print(f"os_invoices (org2 window spread): created {inv_created} / skipped {inv_skipped}")

# =====================================================================
# 6. VERIFY: fragment-shaped reads as the demo + client users
# =====================================================================
print("== 6. verify ==")
ok = True

def gql(query, variables=None, token=TOKEN):
    st, data = req("/graphql", "POST", {"query": query, "variables": variables or {}},
                   token=token)
    return st, data

# 6a. demo-user session token (public creds).
st, login = req("/auth/login", "POST", {"email": DEMO_EMAIL, "password": DEMO_PASS},
                token=None)
demo_token = (login or {}).get("data", {}).get("access_token")
print(f"  demo login: HTTP {st} token={'yes' if demo_token else 'NO'}")
ok = ok and bool(demo_token)

# 6b. tools: the EXACT GetTools query from app/api/portal/tools/route.ts.
GET_TOOLS = """
  query GetTools {
    tools(limit: 300, sort: ["name"]) {
      id name category description website login_url cost billing_cycle
      is_subscription renewal_date auto_renew account_email vendor icon color
      status is_test_data
      expense { id cost status next_billing_date recurrence_interval }
      projects { project_id { id name } }
    }
  }
"""
st, data = gql(GET_TOOLS, token=demo_token)
errs = (data or {}).get("errors")
rows = ((data or {}).get("data") or {}).get("tools") or []
linked = sum(1 for r in rows if r.get("projects"))
withexp = sum(1 for r in rows if r.get("expense"))
print(f"  GetTools as demo: HTTP {st} rows={len(rows)} withProjects={linked} "
      f"withExpense={withexp} errors={errs or 'none'}")
ok = ok and st == 200 and not errs and len(rows) >= 12

# 6c. help: replicate the collections route's two REST reads as demo user.
st, data = req("/items/help_collections?fields=id,title,slug,description,icon,sort"
               "&sort=sort,title&limit=100", token=demo_token)
n_cols = len((data or {}).get("data") or [])
print(f"  help_collections as demo: HTTP {st} rows={n_cols}")
ok = ok and st == 200 and n_cols >= 5
flt = urllib.parse.quote(json.dumps({"_and": [{"status": {"_eq": "published"}}]}))
st, data = req("/items/help_articles?aggregate[count]=id&groupBy[]=help_collection"
               f"&filter={flt}", token=demo_token)
groups = (data or {}).get("data") or []
total_arts = sum(int((g.get("count") or {}).get("id", 0)) for g in groups)
print(f"  help_articles aggregate as demo: HTTP {st} groups={len(groups)} articles={total_arts}")
ok = ok and st == 200 and total_arts >= 15

# 6d. client login + org resolution (queryContactOrganization shape).
st, login = req("/auth/login", "POST", {"email": CLIENT_EMAIL, "password": CLIENT_PASS},
                token=None)
client_token = (login or {}).get("data", {}).get("access_token")
print(f"  client login: HTTP {st} token={'yes' if client_token else 'NO'}")
ok = ok and bool(client_token)

st, me = req("/users/me?fields=id,email,role.name", token=client_token)
role_name = (((me or {}).get("data") or {}).get("role") or {}).get("name")
print(f"  client /users/me: HTTP {st} role={role_name}")
ok = ok and role_name == "Client"

GET_CONTACT_ORG = """
  query GetContactOrg($filter: contacts_filter) {
    contacts(filter: $filter, limit: 1) {
      id email
      organizations { organizations_id { id name } }
    }
  }
"""
st, data = gql(GET_CONTACT_ORG,
               {"filter": {"email": {"_icontains": CLIENT_EMAIL}}}, token=client_token)
errs = (data or {}).get("errors")
contacts = ((data or {}).get("data") or {}).get("contacts") or []
orgs = (contacts[0].get("organizations") if contacts else []) or []
org_name = (orgs[0].get("organizations_id") or {}).get("name") if orgs else None
print(f"  GetContactOrg as client: HTTP {st} org={org_name} errors={errs or 'none'}")
ok = ok and org_name == "Cedar & Co Coffee"

# 6e. client-visible org 2 rows the dashboard + projects pages read.
st, data = req("/items/os_projects?filter[organization][_eq]=2&fields=id,name,due_date"
               "&limit=-1", token=client_token)
n_proj = len((data or {}).get("data") or [])
st2, data2 = req("/items/os_invoices?filter[organization][_eq]=2&fields=id&limit=-1",
                 token=client_token)
n_inv = len((data2 or {}).get("data") or [])
st3, data3 = req("/items/project_links?filter[project][organization][_eq]=2&fields=id"
                 "&limit=-1", token=client_token)
n_links = len((data3 or {}).get("data") or [])
print(f"  org2 as client: projects={n_proj} invoices={n_inv} project_links={n_links}")
ok = ok and n_proj >= 2 and n_inv >= 10 and n_links >= 5

print(f"VERIFY RESULT: {'PASS' if ok else 'FAIL'}")
raise SystemExit(0 if ok else 1)
