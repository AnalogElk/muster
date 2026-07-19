#!/usr/bin/env python3
"""gapfix6-brand-kb: run-2 final gap fix for client/brand-assets and client/kb.

1. Brand assets depth: 3 new client_approved dam_assets for org 2 (Cedar & Co)
   so the Logos and Web sections of /client-portal/brand-assets show more than
   one card each:
     - Cedar & Co logo on cream          -> cedar-logos-brand-marks
     - Cedar & Co wordmark, horizontal   -> cedar-logos-brand-marks
     - Summer menu web banner            -> cedar-web-social
   Media objects are PNG renditions rendered off-box (sharp on the
   workstation, same convention as fetch-dam-objects.py logo PNGs) and must
   already sit under ~/elk-os/mocks/data/agency-directus-assets/<key>; this
   script FAILS LOUD if an object is missing or empty so a dangling
   dam_assets row is never created.

2. Client KB depth: 2 new client-visible kb_spaces with 9 published pages
   (min_role client) so /client-portal/kb shows more than one shelf:
     - Cedar & Co Project Docs (5 pages)   [stopgap for board task d3c0f38a,
       project-scoped KB; kb_spaces has no org field yet, so this space is
       visible to every client role viewer. The demo has one client user.]
     - Billing & Payments (4 pages)

Idempotent: every row upserts by natural key (dam: bucket+key, junction:
asset+collection, kb: slug). Add-only: nothing existing is modified; the
only PATCHes are date_created backdates on rows THIS script created (the
date-created special overrides create payloads).

kb_spaces / kb_pages / dam_* carry no is_test_data field in the live schema
(verified against demo-schema.json), so the flag cannot be written; the
portal test-data filter does not query these collections.

Demo policy read grants: dam_* and kb_* reads already exist for policy
c69b84d1 (run2-P3-dam.py and run-1 D6); verified again here via a fresh
client session probe instead of blind permission writes.
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cms.musterr.dev"
DATA = os.path.expanduser("~/elk-os/mocks/data/agency-directus-assets")


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


def req(path, method="GET", body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": "Bearer " + (token or TOKEN),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        return e.code, payload


def upsert(collection, filt_query, body, label, stats):
    st, resp = req(f"/items/{collection}?{filt_query}&limit=1&fields=id")
    if st == 200 and resp.get("data"):
        stats["skipped"] += 1
        return resp["data"][0]["id"], False
    st2, resp2 = req(f"/items/{collection}", "POST", body)
    if st2 in (200, 204):
        stats["created"] += 1
        return (resp2.get("data") or {}).get("id"), True
    stats["failed"] += 1
    print(f"  {collection} {label}: FAILED {st2}", json.dumps(resp2)[:300])
    return None, False


# ---------------------------------------------------------------------------
# 1. Brand assets (org 2, Cedar & Co Coffee)
# ---------------------------------------------------------------------------
# (key, title, collection_slug, (mime, w, h), tags, colors, description,
#  alt_text, seo_filename, credit, download_count, created)
NEW_ASSETS = [
    ("dam/cedar-and-co-coffee/cedar-logo-cream.png",
     "Cedar & Co logo on cream", "cedar-logos-brand-marks",
     ("image/png", 512, 512),
     ["logo", "brand", "alternate"], ["#F5EFE6", "#6F4E37"],
     "Alternate monogram lockup for light backgrounds and packaging.",
     "Cedar & Co Coffee monogram in roast brown on a cream field",
     "cedar-and-co-logo-cream.png", "Muster Studio", 7, "2026-02-06T10:00:00Z"),
    ("dam/cedar-and-co-coffee/cedar-wordmark-horizontal.png",
     "Cedar & Co wordmark, horizontal", "cedar-logos-brand-marks",
     ("image/png", 1600, 512),
     ["logo", "wordmark", "brand"], ["#6F4E37", "#F5EFE6"],
     "Horizontal wordmark for site headers, email footers, and signage.",
     "Cedar & Co Coffee wordmark with letterspaced COFFEE subline",
     "cedar-and-co-wordmark-horizontal.png", "Muster Studio", 5,
     "2026-02-12T10:00:00Z"),
    ("dam/cedar-and-co-coffee/cedar-summer-web-banner.png",
     "Summer menu web banner", "cedar-web-social",
     ("image/png", 2400, 800),
     ["banner", "web", "seasonal"], ["#6F4E37", "#F5EFE6", "#B08D5B"],
     "Web banner for the summer menu campaign landing page and newsletter.",
     "Summer Menu 2026 banner in cream lettering on roast brown",
     "cedar-summer-web-banner.png", "Muster Studio", 3,
     "2026-06-12T10:00:00Z"),
]


def seed_assets():
    # Fail loud before any row write if a media object is missing/empty.
    for key, *_ in NEW_ASSETS:
        p = os.path.join(DATA, key)
        if not (os.path.isfile(p) and os.path.getsize(p) > 0):
            print(f"FATAL: mock object missing or empty: {p}")
            raise SystemExit(1)

    st, resp = req("/items/dam_collections?filter[org][_eq]=2&fields=id,slug&limit=50")
    if st != 200:
        print("FATAL: cannot list dam_collections", st)
        raise SystemExit(1)
    slug_to_id = {r["slug"]: r["id"] for r in resp["data"]}

    stats = {"created": 0, "skipped": 0, "failed": 0}
    jstats = {"created": 0, "skipped": 0, "failed": 0}
    created_keys = []
    for (key, title, coll_slug, meta, tags, colors, desc, alt, seo, credit,
         dls, created) in NEW_ASSETS:
        mime, w, h = meta
        size = os.path.getsize(os.path.join(DATA, key))
        body = {
            "org": 2,
            "s3_uri": f"s3://agency-directus-assets/{key}",
            "bucket": "agency-directus-assets",
            "key": key,
            "checksum": hashlib.md5(key.encode()).hexdigest(),
            "mime": mime, "width": w, "height": h, "size_bytes": size,
            "exif": {"note": "Generated demo asset; PNG rendition of the brand SVG"},
            "title": title, "description": desc, "alt_text": alt,
            "seo_filename": seo, "tags": tags, "dominant_colors": colors,
            "status": "client_approved", "ai_state": "none",
            "credit": credit, "download_count": dls,
            "date_created": created,
        }
        aid, was_created = upsert(
            "dam_assets",
            "filter[bucket][_eq]=agency-directus-assets&filter[key][_eq]="
            + urllib.parse.quote(key, safe=""),
            body, key, stats)
        if not aid:
            continue
        if was_created:
            created_keys.append((aid, created))
        cid = slug_to_id.get(coll_slug)
        if cid:
            upsert(
                "dam_assets_collections",
                f"filter[dam_assets_id][_eq]={aid}&filter[dam_collections_id][_eq]={cid}",
                {"dam_assets_id": aid, "dam_collections_id": cid},
                f"{key}->{coll_slug}", jstats)
        else:
            jstats["failed"] += 1
            print(f"  junction {key}: collection slug {coll_slug} not found")

    # Backdate only rows this run created (date-created special overrides).
    backdated = 0
    for aid, created in created_keys:
        st2, _ = req(f"/items/dam_assets/{aid}", "PATCH", {"date_created": created})
        if st2 in (200, 204):
            backdated += 1
    print(f"dam_assets: created {stats['created']} / skipped {stats['skipped']} / failed {stats['failed']}")
    print(f"dam_assets_collections: created {jstats['created']} / skipped {jstats['skipped']} / failed {jstats['failed']}")
    print(f"dam_assets backdated: {backdated}")
    return stats["failed"] == 0 and jstats["failed"] == 0


# ---------------------------------------------------------------------------
# 2. Client KB spaces + pages
# ---------------------------------------------------------------------------
SPACES = [
    {
        "slug": "cedar-project-docs",
        "name": "Cedar & Co Project Docs",
        "description": "Living documents for the Cedar & Co engagement: launch checklists, content planning, and guides to the tools we have built for your team.",
        "icon": "folder-open",
        "order": 6,
        "min_role": "client",
        "is_client_visible": True,
        "status": "published",
    },
    {
        "slug": "billing-and-payments",
        "name": "Billing & Payments",
        "description": "How invoicing works, which payment methods we accept, and what every line item on your invoice means.",
        "icon": "credit-card",
        "order": 7,
        "min_role": "client",
        "is_client_visible": True,
        "status": "published",
    },
]

PAGES = [
    # (space_slug, slug, title, order, summary, tags, created, body)
    ("cedar-project-docs", "website-launch-checklist", "Website Launch Checklist", 1,
     "Everything that happens in launch week, who owns each step, and what we need from your team.",
     ["launch", "checklist"], "2026-04-20T10:00:00Z", """## The week before launch

- **Content freeze** takes effect five business days out. Anything submitted after the freeze ships in the first post-launch content batch.
- We run a full crawl of the staging site and fix broken links, missing alt text, and page titles.
- Your team signs off on the final staging review link.

## Launch day

1. DNS cutover happens in the morning window (9:00 to 11:00 Pacific) so we have the full day to monitor.
2. Redirects from every legacy URL are verified against the redirect map you approved.
3. Analytics and search console verification are confirmed live within the first hour.

## The week after

- We watch Core Web Vitals and error logs daily for the first five business days.
- A post-launch report lands in your portal with traffic, performance, and any follow-up items.

Questions during launch week go to your project thread in Messages, not email, so the whole team sees them."""),
    ("cedar-project-docs", "content-calendar-workflow", "Content Calendar & Publishing Workflow", 2,
     "How seasonal menu content moves from draft to published, and the lead times each type needs.",
     ["content", "workflow"], "2026-05-04T10:00:00Z", """## Lead times

| Content type | Lead time |
| --- | --- |
| Menu item update | 2 business days |
| Seasonal landing page | 2 weeks |
| Campaign (banner, email, social kit) | 3 weeks |

## The workflow

1. **Draft**: your team adds copy and imagery to the shared calendar.
2. **Review**: we edit for tone, check images against the brand book, and stage the page.
3. **Approve**: you get a staging link; one click approves it for publish.
4. **Publish**: scheduled for the date on the calendar, usually 6:00 am Pacific.

Seasonal menus (spring, summer, fall, holiday) get a planning call one month before the season starts. The summer 2026 cycle is in the calendar now."""),
    ("cedar-project-docs", "wholesale-portal-guide", "Wholesale Portal User Guide", 3,
     "A walkthrough of the wholesale ordering portal for your cafe and grocery accounts.",
     ["wholesale", "guide"], "2026-05-18T10:00:00Z", """## Accounts and access

Every wholesale customer gets a login tied to their business. You approve new account requests from the admin queue; nothing goes live without your sign-off.

## Placing orders

- Customers order from the live price sheet; tier pricing applies automatically.
- Order cutoff is Tuesday 5:00 pm for Friday delivery routes.
- Standing orders repeat weekly until the customer pauses them.

## What you can edit yourselves

- Price sheet items and tier thresholds
- Delivery route days
- The announcement banner on the portal home page

Changes to checkout flow, invoicing, or account structure come through us; open a support ticket and we will scope it."""),
    ("cedar-project-docs", "loyalty-app-beta", "Loyalty App Beta: What to Expect", 4,
     "Timeline, test group, and how feedback gets triaged during the loyalty app beta.",
     ["loyalty", "beta"], "2026-06-08T10:00:00Z", """## Timeline

- **July**: internal beta with staff accounts at the Pearl District location.
- **August**: invite-only customer beta (200 members from the email list).
- **September**: public launch alongside the fall menu.

## What testers see

Punch-card style rewards, order-ahead for pickup, and the seasonal menu. Payments stay in the existing register system during beta; the app never stores card numbers.

## Feedback

In-app feedback lands directly on our board and gets triaged twice a week. Anything blocking a purchase is same-day. You will see a digest of themes in your monthly report rather than every individual comment."""),
    ("cedar-project-docs", "reading-monthly-analytics", "Reading Your Monthly Analytics Report", 5,
     "What each section of the monthly report means and which numbers are worth acting on.",
     ["analytics", "report"], "2026-06-24T10:00:00Z", """## The three numbers that matter

1. **Organic sessions**: people finding you through search. Slow, steady growth is the healthy pattern.
2. **Menu page conversion**: visitors who view the menu and then take an action (directions, order, wholesale inquiry).
3. **Wholesale inquiries**: form submissions from the wholesale page, tracked end to end.

## What to skim

Bounce rate and time-on-page move around a lot month to month; we flag them only when a trend holds for a quarter.

## Seasonality

Coffee traffic peaks in the fall and around gifting seasons. The report compares each month against the same month last year, not the previous month, so seasonal swings do not read as wins or losses."""),
    ("billing-and-payments", "how-invoicing-works", "How Invoicing Works", 1,
     "When invoices are issued, what the statuses mean, and where to find every invoice we have sent.",
     ["billing", "invoices"], "2026-03-10T10:00:00Z", """## The cycle

- **Recurring services** (hosting, care plans, retainers) invoice on the 1st of each month, due net 15.
- **Project milestones** invoice when the milestone is approved, due net 30.
- **Pass-through expenses** (licensed stock, print runs) appear as separate line items with receipts attached.

## Statuses

| Status | Meaning |
| --- | --- |
| Draft | Being prepared, not yet payable |
| Submitted | Sent to you, awaiting payment |
| Paid | Payment received and receipted |
| Overdue | Past the due date; a reminder has gone out |

Every invoice, past and current, lives under Invoices in this portal. PDFs are always available there; no need to keep email copies."""),
    ("billing-and-payments", "payment-methods-autopay", "Payment Methods & Autopay", 2,
     "Accepted payment methods, how autopay works, and how to change the card or account on file.",
     ["billing", "payments"], "2026-03-12T10:00:00Z", """## Accepted methods

- Card (Visa, Mastercard, Amex)
- ACH bank transfer (no processing fee)
- Check, for annual contracts by prior arrangement

## Autopay

Recurring invoices can charge automatically on the due date. Autopay covers recurring services only; project milestone invoices always come to you for manual approval first.

## Changing your payment method

Update the card or bank account from Settings in this portal. Changes apply from the next invoice; an invoice already submitted keeps the method it was issued under unless you ask us to reissue it."""),
    ("billing-and-payments", "understanding-invoice-line-items", "Understanding Your Invoice Line Items", 3,
     "A plain-language key to the line items, rates, and taxes that appear on our invoices.",
     ["billing", "line-items"], "2026-03-14T10:00:00Z", """## Line item types

- **Fixed fee**: a flat amount for a scoped deliverable. The description names the milestone it belongs to.
- **Time and materials**: hours at the contracted rate, with the period worked in the description.
- **Subscription**: a recurring service for the calendar month shown.
- **Expense**: a pass-through cost, billed at cost with the receipt attached to the invoice.

## Rates

Your contracted rates are fixed for the term of your agreement. Rate changes only ever take effect at renewal, with 60 days notice.

## Taxes

Sales tax applies only to taxable services in your state; the tax line shows the rate used. Wholesale and resale items carry your resale certificate on file."""),
    ("billing-and-payments", "changing-or-pausing-service", "Changing or Pausing Your Subscription", 4,
     "Notice periods and what happens to your site, data, and analytics if you pause or change plans.",
     ["billing", "subscriptions"], "2026-03-16T10:00:00Z", """## Changing plans

Plan changes take effect at the start of the next billing month. Upgrades can start sooner when capacity allows; ask in your project thread.

## Pausing

Care plans can pause for up to three months in any rolling year with 15 days notice. While paused:

- Your site stays live and monitored for uptime and security.
- Content updates and feature work stop.
- Analytics keep collecting, so your history has no gap when you resume.

## Ending service

We ask for 30 days notice. You own your domain, content, and data; we hand over repository access, exports, and DNS in the final week and remain available for a transition call."""),
]


def seed_kb():
    sstats = {"created": 0, "skipped": 0, "failed": 0}
    pstats = {"created": 0, "skipped": 0, "failed": 0}
    space_ids = {}
    for s in SPACES:
        sid, _ = upsert("kb_spaces", f"filter[slug][_eq]={s['slug']}", s, s["slug"], sstats)
        if sid:
            space_ids[s["slug"]] = sid

    created_pages = []
    for (space_slug, slug, title, order, summary, tags, created, body) in PAGES:
        sid = space_ids.get(space_slug)
        if not sid:
            pstats["failed"] += 1
            continue
        body_row = {
            "space": sid, "slug": slug, "title": title, "order": order,
            "summary": summary, "tags": tags, "body": body,
            "status": "published", "min_role": "client",
        }
        pid, was_created = upsert("kb_pages", f"filter[slug][_eq]={slug}", body_row, slug, pstats)
        if pid and was_created:
            created_pages.append((pid, created))

    backdated = 0
    for pid, created in created_pages:
        st2, _ = req(f"/items/kb_pages/{pid}", "PATCH", {"date_created": created})
        if st2 in (200, 204):
            backdated += 1
    print(f"kb_spaces: created {sstats['created']} / skipped {sstats['skipped']} / failed {sstats['failed']}")
    print(f"kb_pages: created {pstats['created']} / skipped {pstats['skipped']} / failed {pstats['failed']}")
    print(f"kb_pages backdated: {backdated}")
    return sstats["failed"] == 0 and pstats["failed"] == 0


# ---------------------------------------------------------------------------
# 3. Verify with a fresh CLIENT session token (proves demo policy reads)
# ---------------------------------------------------------------------------
def verify_as_client():
    r = urllib.request.Request(
        BASE + "/auth/login",
        data=json.dumps({"email": "client@muster.dev", "password": "muster-demo"}).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp2:
        ctoken = json.load(resp2)["data"]["access_token"]

    spaces_filter = json.dumps({"_and": [
        {"status": {"_eq": "published"}},
        {"min_role": {"_in": ["client"]}},
        {"is_client_visible": {"_eq": True}},
    ]})
    st, resp = req("/items/kb_spaces?filter=" + urllib.parse.quote(spaces_filter)
                   + "&fields=slug,name&limit=50", token=ctoken)
    slugs = [r["slug"] for r in resp.get("data", [])] if st == 200 else []
    print(f"VERIFY kb_spaces (client token, portal route filter): {st} -> {slugs}")

    pages_filter = json.dumps({"_and": [
        {"status": {"_eq": "published"}},
        {"min_role": {"_in": ["client"]}},
        {"space": {"slug": {"_in": ["cedar-project-docs", "billing-and-payments"]}}},
    ]})
    st, resp = req("/items/kb_pages?filter=" + urllib.parse.quote(pages_filter)
                   + "&fields=slug&limit=50", token=ctoken)
    print(f"VERIFY kb_pages (client token): {st} -> {len(resp.get('data', []))} pages")

    st, resp = req("/items/dam_assets?filter[org][_eq]=2&filter[status][_eq]=client_approved"
                   "&fields=key,title,mime&limit=50", token=ctoken)
    rows = resp.get("data", []) if st == 200 else []
    print(f"VERIFY dam_assets org2 client_approved (client token): {st} -> {len(rows)} assets")
    for row in rows:
        print("   ", row["key"])
    ok = (set(["cedar-project-docs", "billing-and-payments"]).issubset(set(slugs))
          and len(rows) >= 8)
    print("VERIFY:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ok1 = seed_assets()
    ok2 = seed_kb()
    ok3 = verify_as_client()
    raise SystemExit(0 if (ok1 and ok2 and ok3) else 1)
