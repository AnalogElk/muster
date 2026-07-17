#!/usr/bin/env python3
"""Gap-fix seeding for the four client-portal sections that failed verification.

Root cause of all four failures was the role bounce: no client-role demo user
existed, so /client-portal/* redirected to /employee-portal/dashboard. A
parallel agent in this build already created the Client role (5f3c9df9), the
client@muster.dev user (91fb50ea, password verified working), the contact +
organizations_contacts link to Cedar & Co Coffee (org 2), the help collections
and articles, and the ticket rows. This script fixes what is still missing:

1. os_notifications has ZERO rows for the client user (all 30 rows target the
   Employee demo user, which can never reach /client-portal/notifications).
   Seeds 12 rows with recipient_user = client user.
2. directus_users is missing the custom `notification_preferences` field that
   both settings hydration paths select via /users/me?fields=... A missing
   field fails the WHOLE fetch (drift signature), nulling title/location on
   the settings page. Adds the field additively.
3. Client-visible help coverage is thin on two shelves (analytics: 1,
   administration: 1). Upserts 4 client/all-audience articles by slug.
4. Client user profile: location and avatar are null. Completes the new
   user's row (location + generated SVG initials avatar) so client settings
   renders a full account card.

All writes are additive and idempotent (upsert by natural key). is_test_data
is set false on every collection row that carries the flag.
"""
import io
import json
import os
import urllib.request
import urllib.parse
import uuid

BASE = "https://cms.musterr.dev"
CLIENT_USER = "91fb50ea-5ead-4713-9c48-a32bb945932f"
ORG_CEDAR = 2
PROJ_REDESIGN = "430df3e9"  # prefix only, resolved below
PROJ_WHOLESALE = "a42f4921"


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


def req(path, method="GET", body=None, raw_data=None, content_type="application/json"):
    data = raw_data if raw_data is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": content_type,
    })
    try:
        with urllib.request.urlopen(r) as resp:
            payload = resp.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:400]}


# ---------------------------------------------------------------- 1. field add
def ensure_notification_preferences_field():
    fields = req("/fields/directus_users").get("data", [])
    names = {f["field"] for f in fields}
    if "notification_preferences" in names:
        print("directus_users.notification_preferences: skipped 1 (exists)")
        return
    res = req("/fields/directus_users", method="POST", body={
        "field": "notification_preferences",
        "type": "json",
        "meta": {"interface": "input-code", "special": ["cast-json"], "hidden": True},
        "schema": {},
    })
    if "_error" in res:
        print("directus_users.notification_preferences: ERROR", res["_error"], res["_body"])
    else:
        print("directus_users.notification_preferences: created 1")


# ---------------------------------------------------------- 2. notifications
def resolve_project(prefix):
    rows = req("/items/os_projects?filter[organization][_eq]=%d&fields=id,name&limit=50" % ORG_CEDAR).get("data", [])
    for r in rows:
        if r["id"].startswith(prefix):
            return r["id"]
    return None


def seed_notifications():
    redesign = resolve_project(PROJ_REDESIGN)
    wholesale = resolve_project(PROJ_WHOLESALE)
    inv_302 = "1a8f5fb7-9891-41a5-8c9f-abb75d30413f"
    inv_305 = "587b2914-caba-4987-9df6-54890c032d94"
    inv_306 = "adfd63c9-7fe1-4271-89b9-5e46442a03a0"

    def n(dedupe, type_, title, body, href, days_ago, read_days_ago=None,
          source_collection=None, source_id=None):
        return {
            "dedupe_key": dedupe, "type": type_, "title": title, "body": body,
            "href": href, "days_ago": days_ago, "read_days_ago": read_days_ago,
            "source_collection": source_collection, "source_id": source_id,
        }

    plan = [
        n("client-inv-302-overdue", "invoice",
          "Invoice INV-2026-302 is overdue",
          "Invoice INV-2026-302 for $950.00 was due on Jul 2 and is now marked overdue. You can review the line items and payment options in Billing.",
          "/client-portal/invoices", 0.2, None, "os_invoices", inv_302),
        n("client-redesign-phase-3", "project",
          "Website Redesign moved to Build phase",
          "The Cedar & Co Website Redesign project advanced from Design to Build. Homepage and menu templates are now in development.",
          "/client-portal/projects", 1, None, "os_projects", redesign),
        n("client-ticket-csv-export-reply", "activity",
          "New reply on your ticket: Add CSV export to wholesale order history",
          "Priya Shah replied to your support ticket with a proposed scope for the CSV export feature.",
          "/client-portal/support", 2, None, "os_client_tickets", None),
        n("client-task-menu-photos", "task",
          "Task ready for your review: Seasonal menu photography",
          "The seasonal menu photography selects are uploaded and awaiting your approval before they go live.",
          "/client-portal/tasks", 3, None, None, None),
        n("client-inv-305-paid", "invoice",
          "Payment received for INV-2026-305",
          "Your payment of $1,200.00 for invoice INV-2026-305 was received. A receipt has been added to your billing history.",
          "/client-portal/invoices", 5, 4, "os_invoices", inv_305),
        n("client-wholesale-preview", "project",
          "Wholesale Portal preview link is live",
          "A staging preview of the Wholesale Portal is available. Log in with your usual portal credentials to browse the order flow.",
          "/client-portal/projects", 7, 6, "os_projects", wholesale),
        n("client-update-traffic-report", "activity",
          "June traffic report published",
          "Your June analytics summary is ready: sessions up 18 percent month over month, with the new espresso subscription page leading growth.",
          "/client-portal/analytics", 9, 8, None, None),
        n("client-task-wholesale-pricing", "task",
          "Input needed: wholesale pricing tiers",
          "The team needs your confirmation on the three wholesale pricing tiers before the pricing tables are built.",
          "/client-portal/tasks", 12, 10, None, None),
        n("client-ticket-login-loop-resolved", "activity",
          "Your ticket was resolved: Wholesale portal login loop",
          "The login loop affecting new wholesale accounts has been fixed and verified. The ticket has been marked resolved.",
          "/client-portal/support", 15, 14, "os_client_tickets", None),
        n("client-inv-306-paid", "invoice",
          "Payment received for INV-2026-306",
          "Your payment of $1,500.00 for invoice INV-2026-306 was received. Thank you.",
          "/client-portal/invoices", 20, 19, "os_invoices", inv_306),
        n("client-redesign-kickoff", "project",
          "Website Redesign kickoff complete",
          "Kickoff notes and the project timeline are posted. First design concepts are scheduled for review next week.",
          "/client-portal/projects", 28, 27, "os_projects", redesign),
        n("client-brand-assets-added", "activity",
          "New brand assets uploaded",
          "Updated logo lockups and the summer campaign photo set were added to your brand assets library.",
          "/client-portal/brand-assets", 34, 33, None, None),
    ]

    import datetime
    now = datetime.datetime(2026, 7, 16, 17, 0, 0)
    created = updated = skipped = 0
    for item in plan:
        existing = req("/items/os_notifications?filter[dedupe_key][_eq]=%s&fields=id&limit=1"
                       % urllib.parse.quote(item["dedupe_key"])).get("data", [])
        if existing:
            skipped += 1
            continue
        ts = now - datetime.timedelta(days=item["days_ago"])
        body = {
            "id": str(uuid.uuid4()),
            "title": item["title"],
            "body": item["body"],
            "type": item["type"],
            "href": item["href"],
            "organization": ORG_CEDAR,
            "recipient_user": CLIENT_USER,
            "dedupe_key": item["dedupe_key"],
            "date_created": ts.isoformat() + "Z",
        }
        if item["read_days_ago"] is not None:
            body["read_at"] = (now - datetime.timedelta(days=item["read_days_ago"])).isoformat() + "Z"
        if item["source_collection"]:
            body["source_collection"] = item["source_collection"]
        if item["source_id"]:
            body["source_id"] = item["source_id"]
        res = req("/items/os_notifications", method="POST", body=body)
        if "_error" in res:
            print("  notification ERROR", item["dedupe_key"], res["_error"], res["_body"])
        else:
            # Directus ignores date_created on create (system-managed special
            # field) but accepts it via PATCH as admin; backdate so the feed
            # shows a realistic timeline instead of one seed-time burst.
            new_id = res["data"]["id"]
            fix = req("/items/os_notifications/" + new_id, method="PATCH",
                      body={"date_created": ts.isoformat() + "Z"})
            if "_error" in fix:
                print("  notification backdate ERROR", item["dedupe_key"], fix["_error"])
            created += 1
    print("os_notifications (client): created %d / updated %d / skipped %d" % (created, updated, skipped))


# ------------------------------------------------------------ 3. help articles
HELP_ARTICLES = [
    {
        "slug": "reading-your-monthly-analytics-report",
        "collection_slug": "analytics",
        "title": "Reading your monthly analytics report",
        "summary": "What the traffic, engagement, and conversion numbers in your monthly report mean and how to act on them.",
        "audience": "client",
        "content": """Your monthly analytics report summarizes how your site performed over the previous calendar month. This guide explains each section.

## Sessions and visitors

Sessions count every visit to your site; unique visitors count people. A rising session count with flat visitors usually means your existing audience is returning more often, which is a good sign for content and email campaigns.

## Top pages

The top pages table shows where visitors spend time. Watch for:

- New landing pages climbing the list after a campaign launch
- Product or service pages with high exits, which may need clearer calls to action
- Blog posts that keep attracting search traffic months after publication

## Conversions

Conversions track the actions that matter to your business, such as contact form submissions or completed checkouts. The report shows the conversion rate alongside raw counts so a traffic spike never hides a drop in quality.

## Questions

If a number looks off or you want a deeper dive on a specific page, open a support ticket and we will pull the underlying data for you.""",
    },
    {
        "slug": "comparing-traffic-month-over-month",
        "collection_slug": "analytics",
        "title": "Comparing traffic month over month",
        "summary": "How to use the Analytics tab in your portal to spot trends instead of reacting to single-month swings.",
        "audience": "client",
        "content": """Single-month numbers can mislead. Seasonality, campaigns, and even weather affect traffic. The Analytics tab in your portal is built for trend reading.

## Use the range selector

Switch the date range to 90 days or 6 months before drawing conclusions. A dip that looks alarming in a 30-day view often disappears in the quarterly trend line.

## What we consider normal variance

Week-to-week swings of 10 to 20 percent are normal for most small business sites. We flag anything outside that band in your monthly report.

## When to reach out

Contact us if you see:

1. A sustained drop lasting more than three weeks
2. A sudden spike from a referrer you do not recognize
3. Conversion rate falling while traffic holds steady

Each of those has a specific diagnostic path and the earlier we look, the faster the fix.""",
    },
    {
        "slug": "tracking-project-progress-from-your-portal",
        "collection_slug": "delivery-and-tasks",
        "title": "Tracking project progress from your portal",
        "summary": "Where to find phase status, recent updates, and upcoming milestones for every active project.",
        "audience": "client",
        "content": """Every active project has a detail page in your portal with live status straight from our delivery board.

## The project card

Each project card shows the current phase (Discovery, Design, Build, Review, or Launch), percent complete, and the next milestone date. These update automatically as our team moves work forward.

## Project updates

The Updates feed collects the written summaries our team posts at least weekly on active projects: what shipped, what is in progress, and anything we need from you.

## Tasks that need you

When a task is waiting on your input, such as content approval or a design sign-off, it appears under Tasks with a badge. Responding quickly there keeps your timeline intact.

## Notifications

Enable notifications in Settings to get an alert whenever a phase changes or a deliverable is ready for review.""",
    },
    {
        "slug": "updating-your-account-details",
        "collection_slug": "administration",
        "title": "Updating your account details",
        "summary": "How to change your name, title, location, and notification preferences from the Settings page.",
        "audience": "all",
        "content": """The Settings page manages the account you use to sign in to the portal.

## Profile

Your name, job title, and location appear to our team on tickets and messages you send. Keeping them current helps us route requests to the right person.

## Notifications

The notification toggles control which events send you an email in addition to the in-portal alert. Project phase changes and invoice events are on by default; you can switch any category off at any time.

## Password and security

Use the password section to change your sign-in password. If your organization uses shared credentials, coordinate with your team before changing them.

## Something you cannot change?

Email address changes and adding teammates are handled by our staff so access stays tied to your organization. Open a support ticket and we will take care of it within one business day.""",
    },
]


def seed_help_articles():
    colls = req("/items/help_collections?fields=id,slug&limit=50").get("data", [])
    by_slug = {c["slug"]: c["id"] for c in colls}
    max_sort_rows = req("/items/help_articles?fields=sort&sort=-sort&limit=1").get("data", [])
    next_sort = (max_sort_rows[0]["sort"] or 0) + 1 if max_sort_rows else 1
    created = skipped = 0
    for art in HELP_ARTICLES:
        existing = req("/items/help_articles?filter[slug][_eq]=%s&fields=id&limit=1"
                       % urllib.parse.quote(art["slug"])).get("data", [])
        if existing:
            skipped += 1
            continue
        coll_id = by_slug.get(art["collection_slug"])
        if not coll_id:
            print("  help_articles ERROR: no collection", art["collection_slug"])
            continue
        res = req("/items/help_articles", method="POST", body={
            "title": art["title"],
            "slug": art["slug"],
            "summary": art["summary"],
            "content": art["content"],
            "audience": art["audience"],
            "status": "published",
            "sort": next_sort,
            "help_collection": coll_id,
        })
        next_sort += 1
        if "_error" in res:
            print("  help_articles ERROR", art["slug"], res["_error"], res["_body"])
        else:
            created += 1
    print("help_articles: created %d / updated 0 / skipped %d" % (created, skipped))


# ------------------------------------------------------- 4. client user profile
AVATAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="128" fill="#6F4E37"/>
  <circle cx="128" cy="128" r="118" fill="none" stroke="#8B6A50" stroke-width="6"/>
  <text x="128" y="150" font-family="Helvetica, Arial, sans-serif" font-size="96" font-weight="600"
        fill="#F5EFE7" text-anchor="middle">RA</text>
</svg>
"""


def upload_avatar():
    title = "Avatar Rowan Ashford"
    existing = req("/files?filter[title][_eq]=%s&fields=id&limit=1" % urllib.parse.quote(title)).get("data", [])
    if existing:
        return existing[0]["id"], False
    boundary = "----muster" + uuid.uuid4().hex
    body = io.BytesIO()
    def part(name, value, filename=None, ctype=None):
        body.write(("--%s\r\n" % boundary).encode())
        if filename:
            body.write(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, filename)).encode())
            body.write(("Content-Type: %s\r\n\r\n" % ctype).encode())
        else:
            body.write(('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode())
        value = value.encode() if isinstance(value, str) else value
        body.write(value)
        body.write(b"\r\n")
    part("title", title)
    part("file", AVATAR_SVG, filename="avatar-rowan-ashford.svg", ctype="image/svg+xml")
    body.write(("--%s--\r\n" % boundary).encode())
    res = req("/files", method="POST", raw_data=body.getvalue(),
              content_type="multipart/form-data; boundary=" + boundary)
    if "_error" in res:
        print("  avatar upload ERROR", res["_error"], res["_body"])
        return None, False
    return res["data"]["id"], True


def complete_client_profile():
    u = req("/users/%s?fields=id,location,avatar,title" % CLIENT_USER).get("data", {})
    patch = {}
    if not u.get("location"):
        patch["location"] = "Portland, OR"
    if not u.get("avatar"):
        file_id, uploaded = upload_avatar()
        if file_id:
            patch["avatar"] = file_id
            print("  avatar file: %s (%s)" % (file_id, "uploaded" if uploaded else "reused"))
    if not patch:
        print("client user profile: skipped 1 (complete)")
        return
    res = req("/users/" + CLIENT_USER, method="PATCH", body=patch)
    if "_error" in res:
        print("client user profile: ERROR", res["_error"], res["_body"])
    else:
        print("client user profile: updated fields %s" % sorted(patch.keys()))


# ------------------------------------------------------------- 5. org tickets
# The client support widget defaults to the org's FIRST project by
# sort=-date_updated (nulls first). Two Cedar & Co projects added later in the
# build have no tickets, so the default view rendered "No tickets yet". Seed
# 2 tickets with alternating staff/client response threads on each org-2
# project that has none. Idempotent by subject.
EMPLOYEE_USER = "257a4b75-deff-476d-953d-1898c57f6684"

TICKET_PLAN = {
    "Cedar & Co - Loyalty Card Microsite": [
        {
            "subject": "QR code on punch cards scans to old URL",
            "description": "The QR code printed on the new punch cards still points to the temporary staging link instead of the loyalty microsite. Customers get a not-found page when they scan it in store.",
            "category": "bug", "priority": "high", "status": "open",
            "days_ago": 2,
            "responses": [
                (False, "Flagging this as urgent for the Saturday rush. We have about 200 cards already printed.", 1.8),
                (True, "Thanks Rowan. The staging URL will 301 to the live microsite within the hour, so every printed card keeps working. We will confirm here once the redirect is verified from a phone scan.", 1.5),
                (False, "Scanned one from the register just now and it lands on the rewards page. Appreciate the fast turnaround.", 1.0),
            ],
        },
        {
            "subject": "Add double points weekend banner",
            "description": "Marketing wants a dismissible banner on the loyalty microsite announcing double points for the last weekend of July. Copy is ready, artwork attached in the brand assets library.",
            "category": "feature_request", "priority": "normal", "status": "pending",
            "days_ago": 6,
            "responses": [
                (True, "We can ship this as a configurable banner so your team can reuse it for future promos. Scheduling build for this sprint; preview link to follow by Thursday.", 5.5),
                (False, "Configurable works great. Please default it to hidden after August 2.", 5.0),
            ],
        },
    ],
    "Cedar & Co - Spring Menu Launch": [
        {
            "subject": "Seasonal menu PDF shows last year's prices",
            "description": "The downloadable spring menu PDF on the landing page still lists 2025 prices for the cold brew flight and the pastry box. Web menu is correct; only the PDF is stale.",
            "category": "bug", "priority": "normal", "status": "resolved",
            "days_ago": 12, "resolved_days_ago": 10,
            "responses": [
                (True, "Good catch. The PDF was exported before the final price pass. Regenerating from the approved sheet and replacing the asset today.", 11.5),
                (False, "Confirmed the new PDF shows current prices. Thanks.", 10.2),
            ],
        },
        {
            "subject": "Can we A/B test the hero photo?",
            "description": "The team is split between the latte art close-up and the patio wide shot for the spring landing page hero. Is a simple A/B test possible with the current setup?",
            "category": "question", "priority": "low", "status": "new",
            "days_ago": 1,
            "responses": [
                (True, "Yes, we can run a 50/50 split through the analytics snippet already on the page and report click-through on the order CTA after two weeks. No extra tooling needed. Want us to set it up?", 0.5),
            ],
        },
    ],
}


def seed_org_tickets():
    import datetime
    now = datetime.datetime(2026, 7, 16, 17, 0, 0)
    projs = req("/items/os_projects?filter[organization][_eq]=%d&fields=id,name&limit=50" % ORG_CEDAR).get("data", [])
    by_name = {p["name"]: p["id"] for p in projs}
    created = skipped = 0
    for proj_name, tickets in TICKET_PLAN.items():
        proj_id = by_name.get(proj_name)
        if not proj_id:
            print("  os_client_tickets: project not found:", proj_name)
            continue
        for t in tickets:
            existing = req("/items/os_client_tickets?filter[subject][_eq]=%s&fields=id&limit=1"
                           % urllib.parse.quote(t["subject"])).get("data", [])
            if existing:
                skipped += 1
                continue
            ts = now - datetime.timedelta(days=t["days_ago"])
            body = {
                "id": str(uuid.uuid4()),
                "subject": t["subject"],
                "description": t["description"],
                "category": t["category"],
                "priority": t["priority"],
                "status": t["status"],
                "project": proj_id,
                "submitted_by": CLIENT_USER,
                "is_test_data": False,
            }
            if t.get("resolved_days_ago") is not None:
                body["resolved_at"] = (now - datetime.timedelta(days=t["resolved_days_ago"])).isoformat() + "Z"
            res = req("/items/os_client_tickets", method="POST", body=body)
            if "_error" in res:
                print("  os_client_tickets ERROR", t["subject"][:30], res["_error"], res["_body"])
                continue
            tid = res["data"]["id"]
            req("/items/os_client_tickets/" + tid, method="PATCH",
                body={"date_created": ts.isoformat() + "Z"})
            for is_staff, message, r_days in t["responses"]:
                r = req("/items/os_client_ticket_responses", method="POST", body={
                    "id": str(uuid.uuid4()),
                    "ticket": tid,
                    "is_staff": is_staff,
                    "author": EMPLOYEE_USER if is_staff else CLIENT_USER,
                    "message": message,
                })
                if "_error" in r:
                    print("  response ERROR", t["subject"][:30], r["_error"], r["_body"])
                    continue
                req("/items/os_client_ticket_responses/" + r["data"]["id"], method="PATCH",
                    body={"date_created": (now - datetime.timedelta(days=r_days)).isoformat() + "Z"})
            created += 1
    print("os_client_tickets (org 2 gap projects): created %d / updated 0 / skipped %d" % (created, skipped))


if __name__ == "__main__":
    ensure_notification_preferences_field()
    seed_notifications()
    seed_help_articles()
    complete_client_profile()
    seed_org_tickets()
