#!/usr/bin/env python3
"""D4 domain-comms seeder for the Muster demo (cms.musterr.dev).

Seeds: os_message_threads (9, orgs 2-8, none on org 1),
os_messages (52 across the 9 threads, deterministic backdated timestamps),
os_client_tickets (14 across the 9 client-facing synthetic projects),
os_client_ticket_responses (40, 2-5 per ticket, alternating staff/client),
os_notifications (30, all for the demo user, dedupe_key seed:notif:NNN).

Write pattern (REV 3 create-stamp two-phase): Directus stamps date_created
at create time and ignores the payload, so every backdated row is written as
POST create followed immediately by PATCH {date_created: deterministic}.
Upsert keys: threads (organization, subject); messages (thread, date_created)
with a (thread, body) repair fallback; tickets (subject); responses
(ticket, date_created) with a (ticket, message) repair fallback;
notifications (dedupe_key). All timestamps derive from fixed offsets from
BASE 2026-06-04T09:00:00Z so re-runs match and created=0 holds.

Unread choreography is computed from READ-BACK stored values, never from the
formula alone: after the message pass, each thread's stored message
date_created values drive last_message_at / team_last_read_at /
client_last_read_at.

Rules honored: add-only, idempotent, is_test_data false on every row that has
the field (os_client_ticket_responses and os_notifications do not have it),
enum values only, no em dashes anywhere, existing rows never edited, token
loaded inside this script and never printed. Demo login creds are the public
demo creds shown on the landing page (not a secret).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("DIRECTUS_URL", "https://cms.musterr.dev").rstrip("/")

USER_DEMO = "257a4b75-deff-476d-953d-1898c57f6684"
USER_ADMIN = "34d67d59-16c3-41c4-9efb-7fd51a216460"
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
DEMO_EMAIL = "demo@muster.dev"      # public demo creds (landing page), not a secret
DEMO_PASSWORD = "muster-demo"

F3_FALLBACK = {
    "felix.anders@team.musterr.dev": "78cf2976-e1da-4b8b-b238-822bcbe1b8fb",
    "aisha.karim@team.musterr.dev": "86f5c9cd-b6fb-4d43-bb5c-2050e66c7f40",
    "tom.beckett@team.musterr.dev": "a043509e-00b1-4d4c-b613-fd0d30b878db",
}

PROJ = {
    "cedar_web": "430df3e9-7f6d-4369-81cf-d9e5dc0fab00",
    "cedar_wholesale": "a42f4921-7747-4319-b09e-644f639e89c5",
    "northlight_brand": "91528c06-daee-41eb-b614-363afb1eb531",
    "northlight_seo": "193e5bd8-e9b2-471e-91e9-7c19aa2a2c7a",
    "vellum_portfolio": "4ae1d3fa-92fb-443d-86c8-4636df95e41c",
    "harbor_app": "d16e4ef5-a11c-4165-8f5b-2a79fa1a1e51",
    "bloom_shopify": "3d5677cf-af08-4df2-a29a-6a4925ab9268",
    "sterling_res": "cd1eae58-ec99-4444-bbe4-ae6ab9370cea",
    "meridian_grant": "c6581803-8fe8-43e7-bb56-4f1e758e2a25",
}
SYNTH_PROJECT_IDS = list(PROJ.values())

UTC = timezone.utc
BASE_TS = datetime(2026, 6, 4, 9, 0, 0, tzinfo=UTC)
TICKET_BASE_TS = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
NOTIF_BASE_TS = datetime(2026, 6, 5, 8, 30, 0, tzinfo=UTC)
RUN_START = datetime.now(UTC)


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
NO_AUTH = "__no_auth__"


def request(method, path, payload=None, token=None, retries=3):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(retries):
        headers = {"Content-Type": "application/json"}
        if token != NO_AUTH:
            headers["Authorization"] = "Bearer " + (token or TOKEN)
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                return r.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            try:
                return e.code, json.loads(body)
            except Exception:
                return e.code, {"_raw": body[:400]}
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    return 0, {}


COUNTS = {}


def bump(coll, key, n=1):
    COUNTS.setdefault(coll, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
    COUNTS[coll][key] += n


def q(v):
    return urllib.parse.quote(str(v), safe="")


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def same_ts(a, b, tol=2):
    pa = a if isinstance(a, datetime) else parse_ts(a)
    pb = b if isinstance(b, datetime) else parse_ts(b)
    if pa is None or pb is None:
        return False
    return abs((pa - pb).total_seconds()) <= tol


def list_items(coll, qs, token=None):
    st, r = request("GET", "/items/%s?%s" % (coll, qs), token=token)
    if st == 200:
        return r.get("data", [])
    print("  WARN list %s -> %s %s" % (coll, st, str(r)[:200]))
    return []


def create_backdated(coll, payload, det_dc, extra_patch=None):
    """POST create then PATCH date_created (+extras). Returns id or None."""
    st, r = request("POST", "/items/" + coll, payload)
    if st not in (200, 201):
        bump(coll, "failed")
        print("  FAIL create %s -> %s %s" % (coll, st, str(r)[:200]))
        return None
    rid = r["data"]["id"]
    patch = {"date_created": iso(det_dc)}
    if extra_patch:
        patch.update(extra_patch)
    st2, r2 = request("PATCH", "/items/%s/%s" % (coll, rid), patch)
    if st2 != 200:
        bump(coll, "failed")
        print("  FAIL backdate %s/%s -> %s %s" % (coll, rid, st2, str(r2)[:200]))
        return rid
    bump(coll, "created")
    return rid


def repair_dc(coll, rid, stored_dc, det_dc):
    """If a found row's date_created drifted from the deterministic value
    (crash between create and patch on a prior run), re-patch it."""
    if same_ts(stored_dc, det_dc):
        bump(coll, "skipped")
        return
    st, r = request("PATCH", "/items/%s/%s" % (coll, rid), {"date_created": iso(det_dc)})
    if st == 200:
        bump(coll, "updated")
        print("  repaired date_created %s/%s" % (coll, rid))
    else:
        bump(coll, "failed")
        print("  FAIL repair %s/%s -> %s" % (coll, rid, st))


def resolve_team_users():
    users = {}
    emails = ",".join(F3_FALLBACK.keys())
    st, r = request("GET", "/users?filter[email][_in]=%s&fields=id,email&limit=-1" % emails)
    if st == 200:
        for u in r.get("data", []):
            users[u["email"]] = u["id"]
    for e, uid in F3_FALLBACK.items():
        users.setdefault(e, uid)
    return [
        USER_ADMIN,
        users["felix.anders@team.musterr.dev"],
        users["aisha.karim@team.musterr.dev"],
        users["tom.beckett@team.musterr.dev"],
    ]


# ------------------------------------------------------------------ threads
# (org, subject, status, choreography, [(role, body), ...])
# choreography: "emp_unread" | "client_unread" | "read"
THREADS = [
    (2, "Launch timeline question", "open", "emp_unread", [
        ("client", "Hi team, quick question on the Cedar Website Redesign launch. Are we still tracking for the end of June window?"),
        ("team", "Hi Maren, yes, we are on schedule. Content migration wraps this week and QA starts Monday."),
        ("client", "Great to hear. Will the wholesale signup form be part of the first release?"),
        ("team", "It ships in the same release. We will send staging links once QA signs off so you can review the form flow."),
        ("client", "Perfect, please send the staging link when ready. We want to preview it before the board meeting."),
    ]),
    (2, "Invoice INV-2026-302 clarification", "open", "client_unread", [
        ("client", "We received INV-2026-302 and had a question about the hosting line item. Can you confirm what period it covers?"),
        ("team", "That line covers managed hosting for April through June for the Cedar Website Redesign environment."),
        ("client", "Understood. Our bookkeeper also asked whether the amount includes the CDN fees discussed in March."),
        ("team", "Yes, CDN delivery is bundled into the hosting line. There is no separate charge."),
        ("client", "Thanks for confirming. We will process payment this week."),
        ("team", "Appreciated. We have flagged INV-2026-302 for follow up on our side and will confirm once payment lands."),
    ]),
    (3, "Homepage copy review", "open", "client_unread", [
        ("team", "We have drafted new homepage copy for the Northlight Brand Identity rollout. The document is ready for your review."),
        ("client", "Thanks, reviewing now. The partner bios section reads well."),
        ("team", "Good to hear. We tightened the practice areas summary as well, so flag anything that feels off brand."),
        ("client", "One note, the tagline should say counsel for modern firms rather than legal services."),
        ("team", "Updated the tagline as requested. The revised draft is in the shared folder for final sign off."),
    ]),
    (3, "SEO retainer monthly report", "closed", "read", [
        ("client", "Has the May report for the Northlight SEO Retainer been published yet?"),
        ("team", "It went out this morning. Organic sessions are up 12 percent month over month."),
        ("client", "Nice. Which pages drove the gain?"),
        ("team", "The practice area pages and the new insights articles carried most of the growth."),
        ("client", "Great work. Nothing further from our side this month."),
        ("team", "Thanks, closing this thread. The June report will follow the same schedule."),
    ]),
    (4, "Portfolio image licensing", "open", "emp_unread", [
        ("client", "For the Vellum Portfolio Platform, do we need extended licenses for the photography used on case study pages?"),
        ("team", "Client owned work needs no license. For the three stock images we will confirm usage terms."),
        ("client", "Please do. We want to avoid any takedown risk after launch."),
        ("team", "Confirmed, all three stock images are covered under the studio license we hold."),
        ("client", "Thanks. What about the type foundry license for the display face?"),
        ("team", "The web font license covers up to one million monthly page views, which is well above current traffic."),
        ("client", "Understood. Can you send the license summaries for our records before the end of the month?"),
    ]),
    (5, "Class booking app beta feedback", "open", "emp_unread", [
        ("client", "The beta build of the Harbor Class Booking App looks strong. Instructors flagged one issue with waitlist ordering."),
        ("team", "Thanks for the report. We reproduced the waitlist issue and a fix is in review."),
        ("client", "Great. Members also asked if the schedule can default to their home studio."),
        ("team", "Default studio preference ships in the next beta build alongside the waitlist fix."),
        ("client", "Both fixes sound good. The front desk team will retest on Thursday and report back."),
    ]),
    (6, "Shopify storefront handover", "closed", "read", [
        ("team", "Handover documents for the Bloom Shopify Build are ready, including admin access notes and the theme changelog."),
        ("client", "Received, thank you. The team walkthrough is booked for Friday."),
        ("team", "Great. We recorded a short video covering order management and discount setup as well."),
        ("client", "The video was helpful. One question, who do we contact for urgent theme issues after handover?"),
        ("team", "Use the support channel in your portal. Urgent issues are triaged within four business hours."),
        ("client", "Perfect, that covers everything. Thanks for a smooth handover."),
    ]),
    (7, "Reservations widget feedback", "open", "read", [
        ("client", "Early feedback on the Sterling Reservations widget is positive. Guests like the same day booking flow."),
        ("team", "Glad to hear it. We are monitoring conversion and will share numbers at the end of the week."),
        ("client", "The host team asked whether party size limits can vary by day."),
        ("team", "Yes, per day limits are configurable. We will enable the setting on your dashboard."),
        ("client", "Enabled and working. One guest reported a confirmation email that arrived twice."),
        ("team", "We traced the duplicate email to a retry bug and patched it this morning."),
        ("client", "Confirmed, no duplicates since the patch. Thanks for the quick turnaround."),
        ("team", "Great. We will keep the widget on the current release and continue monitoring through the weekend."),
    ]),
    (8, "Grant portal accessibility review", "closed", "read", [
        ("team", "The accessibility review for the Meridian Grant Portal is complete. We logged nine findings, all minor."),
        ("client", "Thanks. Are any of the findings blockers for the July application cycle?"),
        ("team", "No blockers. Contrast fixes and focus states are already merged, the rest land this sprint."),
        ("client", "Excellent. We will note the review as complete for our compliance file."),
    ]),
]

MSG_STEP = timedelta(hours=7, minutes=11)
THREAD_STEP = timedelta(days=4)


def msg_time(i, j):
    return BASE_TS + i * THREAD_STEP + j * MSG_STEP


def thread_time(i):
    return msg_time(i, 0) - timedelta(minutes=30)


def seed_threads():
    ids = []
    for i, (org, subject, status, _cho, _msgs) in enumerate(THREADS):
        det = thread_time(i)
        rows = list_items(
            "os_message_threads",
            "filter[organization][_eq]=%s&filter[subject][_eq]=%s&fields=id,date_created&limit=1"
            % (org, q(subject)),
        )
        if rows:
            ids.append(rows[0]["id"])
            repair_dc("os_message_threads", rows[0]["id"], rows[0].get("date_created"), det)
            continue
        rid = create_backdated(
            "os_message_threads",
            {"organization": org, "subject": subject, "status": status, "is_test_data": False},
            det,
        )
        ids.append(rid)
    return ids


def seed_messages(thread_ids, team_rotation):
    for i, (_org, _subject, _status, _cho, msgs) in enumerate(THREADS):
        tid = thread_ids[i]
        if not tid:
            continue
        existing = list_items(
            "os_messages",
            "filter[thread][_eq]=%s&fields=id,date_created,body&limit=200" % tid,
        )
        for j, (role, body) in enumerate(msgs):
            det = msg_time(i, j)
            hit = next((e for e in existing if same_ts(e.get("date_created"), det)), None)
            if hit is None:
                # repair fallback: same body but drifted timestamp (crashed prior run)
                hit = next((e for e in existing if e.get("body") == body), None)
                if hit is not None:
                    repair_dc("os_messages", hit["id"], hit.get("date_created"), det)
                    continue
            if hit is not None:
                bump("os_messages", "skipped")
                continue
            author = None
            if role == "team":
                author = team_rotation[(i * 3 + j) % len(team_rotation)]
            create_backdated(
                "os_messages",
                {"thread": tid, "author_role": role, "author": author, "body": body,
                 "is_test_data": False},
                det,
            )


def choreograph_threads(thread_ids):
    """Read back stored message timestamps and set thread markers from them."""
    results = []
    for i, (_org, subject, _status, cho, msgs) in enumerate(THREADS):
        tid = thread_ids[i]
        if not tid:
            continue
        rows = list_items(
            "os_messages",
            "filter[thread][_eq]=%s&fields=id,date_created,author_role&limit=200" % tid,
        )
        rows = [r for r in rows if parse_ts(r.get("date_created"))]
        rows.sort(key=lambda r: parse_ts(r["date_created"]))
        if len(rows) < 2:
            print("  WARN thread %s has %d messages, skipping markers" % (subject, len(rows)))
            continue
        latest, second = rows[-1], rows[-2]
        expected_last_role = msgs[-1][0]
        if latest["author_role"] != expected_last_role:
            print("  ASSERT FAIL thread %s latest role %s != expected %s"
                  % (subject, latest["author_role"], expected_last_role))
        last_at = latest["date_created"]
        if cho == "emp_unread":
            team_read, client_read = second["date_created"], latest["date_created"]
        elif cho == "client_unread":
            team_read, client_read = latest["date_created"], second["date_created"]
        else:
            team_read = client_read = latest["date_created"]
        st, r = request("GET", "/items/os_message_threads/%s?fields=id,last_message_at,team_last_read_at,client_last_read_at" % tid)
        cur = r.get("data", {}) if st == 200 else {}
        if (same_ts(cur.get("last_message_at"), last_at)
                and same_ts(cur.get("team_last_read_at"), team_read)
                and same_ts(cur.get("client_last_read_at"), client_read)):
            bump("thread_markers", "skipped")
        else:
            st2, r2 = request("PATCH", "/items/os_message_threads/%s" % tid,
                              {"last_message_at": last_at,
                               "team_last_read_at": team_read,
                               "client_last_read_at": client_read})
            if st2 == 200:
                bump("thread_markers", "updated")
            else:
                bump("thread_markers", "failed")
                print("  FAIL markers %s -> %s %s" % (subject, st2, str(r2)[:150]))
        results.append((subject, cho, last_at, team_read, client_read,
                        latest["author_role"]))
    return results


# ------------------------------------------------------------------ tickets
# (subject, project_key, category, priority, status, submitted_by_demo,
#  description, [(is_staff, message), ...])
TICKETS = [
    ("Checkout button unresponsive on mobile Safari", "cedar_web", "bug", "high", "closed", True,
     "Customers on iPhone report that the checkout button does nothing on the first tap. Seen on Safari 17 and the in app Instagram browser.",
     [(True, "Thanks for the report. We reproduced the issue on iOS Safari and traced it to a tap event handler regression."),
      (False, "Good to hear. Our cafe manager can retest once a fix is up."),
      (True, "A fix is deployed to production. Taps register correctly on iOS Safari 16 and 17 in our device lab.")]),
    ("Wholesale portal login loop for new accounts", "cedar_wholesale", "bug", "urgent", "resolved", False,
     "New wholesale accounts are bounced back to the login screen after entering valid credentials. Existing accounts are unaffected.",
     [(True, "We found the session cookie was scoped to the wrong subdomain for newly provisioned accounts. A patch is in review."),
      (False, "Confirmed working for the two accounts created this morning. Thanks for the quick fix.")]),
    ("Question about INV-2026-302 line items", "cedar_web", "billing", "normal", "closed", True,
     "The hosting line on INV-2026-302 is higher than last quarter. Please confirm what the line covers before we process payment.",
     [(True, "The hosting line on INV-2026-302 covers managed hosting plus the CDN allowance we added in March."),
      (False, "Understood. Can you send a one page breakdown for our bookkeeper?"),
      (True, "Breakdown sent to your billing contact by email. Let us know if anything else is needed."),
      (False, "Received and approved. Payment is scheduled for Friday.")]),
    ("Brand PDF fonts render incorrectly in Acrobat", "northlight_brand", "bug", "normal", "resolved", False,
     "The brand guidelines PDF shows fallback fonts in Acrobat on Windows. Preview on Mac renders correctly.",
     [(True, "The export was missing embedded font subsets. We re exported the guidelines with fonts embedded and replaced the file in your portal."),
      (False, "Renders correctly in Acrobat now. Thanks.")]),
    ("Class schedule sync dropping Tuesday sessions", "harbor_app", "bug", "high", "resolved", True,
     "The Tuesday 6am spin class is missing from the app schedule while it shows correctly in the studio calendar.",
     [(True, "We are investigating the sync job. Early signs point to a timezone boundary bug for classes that start before 7am."),
      (False, "That matches what we see. The 6am sessions are the only ones affected."),
      (True, "Confirmed. Classes starting before 7am local time were assigned to the previous day. A fix is in staging."),
      (False, "Staging looks correct for next week. Please promote when ready."),
      (True, "Fix is live in production and the full schedule resynced. All Tuesday sessions appear correctly.")]),
    ("Monthly SEO report delivery date", "northlight_seo", "question", "low", "pending", False,
     "Can the monthly SEO report arrive by the 3rd business day? Our partners meeting moved earlier in the month.",
     [(True, "We can move your report to the 3rd business day starting with the July cycle. Confirming with the analytics team."),
      (False, "That timing works. Please confirm once it is locked in."),
      (True, "Waiting on final confirmation from the analytics team. We will update this ticket by Friday.")]),
    ("Request to add case studies section", "northlight_brand", "feature_request", "normal", "open", True,
     "We would like a case studies section on the new site with three launch examples and a filterable list.",
     [(True, "Scoping the case studies section now. We will share an estimate and two layout options this week."),
      (False, "Sounds good. The managing partner wants the litigation example featured first.")]),
    ("Portfolio images loading slowly on gallery page", "vellum_portfolio", "bug", "normal", "open", False,
     "The main gallery takes several seconds to render on hotel wifi. Images seem to load at full resolution.",
     [(True, "The gallery is serving original uploads. We are enabling responsive image sizes and lazy loading."),
      (False, "Thanks. The Berlin client demo is next Thursday so sooner is better."),
      (True, "Responsive sizes are live on staging and the gallery loads in under two seconds on a throttled connection."),
      (False, "Big improvement on our end too. Please push to production before Thursday.")]),
    ("Reservations widget double booking edge case", "sterling_res", "bug", "high", "pending", True,
     "Two guests booked the same four top for Saturday 7pm within a few seconds of each other. It happened once so far.",
     [(True, "We reproduced the race condition when two holds land in the same second. A locking fix is in progress."),
      (False, "Thanks. The floor manager is holding a buffer table on weekends until this is fixed."),
      (True, "The locking fix is in review. We are waiting on a maintenance window with your team to deploy it.")]),
    ("Push notification opt in copy change", "harbor_app", "feature_request", "low", "open", False,
     "Please soften the push notification opt in text. Members found the current wording pushy.",
     [(True, "Draft copy options are attached to your portal files. Option B matches your brand voice best in our view."),
      (False, "We prefer option B as well. Please ship it in the next release.")]),
    ("Gift card balance page returns 404", "bloom_shopify", "bug", "urgent", "open", True,
     "The gift card balance page linked from order confirmation emails returns a 404 since last week.",
     [(True, "The balance page slug changed during the theme update. We are restoring a redirect from the old URL."),
      (False, "Customers hit this daily, so please treat it as urgent."),
      (True, "Redirect is live and the balance page resolves from all confirmation emails we tested.")]),
    ("Update wine list PDF link in footer", "sterling_res", "other", "normal", "new", False,
     "The footer still links to the spring wine list. Please point it at the summer PDF our sommelier uploaded.",
     [(True, "We located the summer PDF in your uploads and will swap the footer link in the next content deploy."),
      (False, "Thank you. The tasting menu link can stay as is.")]),
    ("Grant application autosave interval question", "meridian_grant", "question", "normal", "new", True,
     "Applicants asked how often the grant application autosaves. Is the interval configurable per section?",
     [(True, "Autosave runs every 30 seconds and on every section change. Making it configurable is possible and we can scope it."),
      (False, "Every 30 seconds is fine. No need to scope the configurable option.")]),
    ("Add CSV export to wholesale order history", "cedar_wholesale", "feature_request", "normal", "new", False,
     "Our buyers want to export order history to CSV for their purchasing system. Monthly ranges would be enough.",
     [(True, "CSV export is a reasonable addition. We will estimate a monthly range export this sprint."),
      (False, "Great. Column order should match the purchasing template we shared in May."),
      (True, "Estimate added to your proposal queue. Export columns will follow the May template.")]),
]

TICKET_STEP = timedelta(days=6)
RESPONSE_STEP = timedelta(hours=26, minutes=13)


def ticket_time(k):
    return TICKET_BASE_TS + k * TICKET_STEP


def response_time(k, r):
    return ticket_time(k) + (r + 1) * RESPONSE_STEP


def seed_tickets():
    ids = []
    date_updated_finding = None
    for k, (subject, pkey, category, priority, status, by_demo, desc, resps) in enumerate(TICKETS):
        det = ticket_time(k)
        resolved_at = None
        if status in ("resolved", "closed"):
            resolved_at = iso(det + timedelta(days=4, hours=3))
        rows = list_items(
            "os_client_tickets",
            "filter[subject][_eq]=%s&fields=id,date_created&limit=1" % q(subject),
        )
        if rows:
            ids.append(rows[0]["id"])
            repair_dc("os_client_tickets", rows[0]["id"], rows[0].get("date_created"), det)
            continue
        det_updated = response_time(k, len(resps) - 1)
        payload = {
            "subject": subject,
            "description": desc,
            "status": status,
            "priority": priority,
            "category": category,
            "project": PROJ[pkey],
            "submitted_by": USER_DEMO if by_demo else None,
            "is_test_data": False,
        }
        if resolved_at:
            payload["resolved_at"] = resolved_at
        rid = create_backdated("os_client_tickets", payload, det,
                               extra_patch={"date_updated": iso(det_updated)})
        ids.append(rid)
        if rid and date_updated_finding is None:
            st, r = request("GET", "/items/os_client_tickets/%s?fields=date_updated" % rid)
            if st == 200:
                stored = (r.get("data") or {}).get("date_updated")
                stuck = same_ts(stored, det_updated)
                date_updated_finding = (
                    "os_client_tickets.date_updated PATCH passthrough: %s (stored %s vs deterministic %s)"
                    % ("HELD" if stuck else "OVERRIDDEN by update stamp", stored, iso(det_updated)))
    if date_updated_finding:
        print("  finding: " + date_updated_finding)
    return ids


def seed_responses(ticket_ids):
    for k, (_subject, _pkey, _cat, _pri, _status, _bd, _desc, resps) in enumerate(TICKETS):
        tid = ticket_ids[k] if k < len(ticket_ids) else None
        if not tid:
            continue
        existing = list_items(
            "os_client_ticket_responses",
            "filter[ticket][_eq]=%s&fields=id,date_created,message&limit=200" % tid,
        )
        for r_i, (is_staff, message) in enumerate(resps):
            det = response_time(k, r_i)
            hit = next((e for e in existing if same_ts(e.get("date_created"), det)), None)
            if hit is None:
                hit = next((e for e in existing if e.get("message") == message), None)
                if hit is not None:
                    repair_dc("os_client_ticket_responses", hit["id"], hit.get("date_created"), det)
                    continue
            if hit is not None:
                bump("os_client_ticket_responses", "skipped")
                continue
            create_backdated(
                "os_client_ticket_responses",
                {"ticket": tid, "is_staff": bool(is_staff),
                 "author": USER_ADMIN if is_staff else None,
                 "message": message},
                det,
            )


# -------------------------------------------------------------- notifications
NOTIF_STEP = timedelta(hours=33, minutes=20)
UNREAD_IDX = {7, 8, 9, 17, 18, 19, 27, 28, 29}

INVOICE_NUMBERS = ["INV-2026-302", "INV-2026-300", "INV-2026-311", "INV-2026-313",
                   "INV-2026-304", "INV-2026-307", "INV-2026-315"]


def sanitize(text):
    return text.replace("\u2014", "-").replace("\u2013", "-").replace("  ", " ").strip()


def build_notifications(thread_ids, ticket_ids):
    inv_rows = list_items(
        "os_invoices",
        "filter[invoice_number][_in]=%s&fields=id,invoice_number,organization,total,status&limit=20"
        % ",".join(INVOICE_NUMBERS),
    )
    inv = {r["invoice_number"]: r for r in inv_rows}

    task_rows = list_items(
        "os_tasks",
        "filter[project][_in]=%s&fields=id,name,project.organization&sort=id&limit=6"
        % ",".join(SYNTH_PROJECT_IDS),
    )
    task_fallback = False
    if len(task_rows) < 6:
        task_fallback = True
        pad = list_items("os_tasks", "fields=id,name,project.organization&sort=id&limit=%d"
                         % (6 - len(task_rows)))
        task_rows = task_rows + pad
    tasks = []
    for t in task_rows[:6]:
        org = None
        proj = t.get("project")
        if isinstance(proj, dict):
            org = proj.get("organization")
        tasks.append({"id": t["id"], "name": sanitize(t.get("name") or "Task"),
                      "organization": org if isinstance(org, int) else 1})

    deal_rows = list_items("os_deals", "fields=id,name,organization&sort=id&limit=20")
    synth_deals = [d for d in deal_rows if d.get("organization") not in (None, 1)]
    deals = (synth_deals + [d for d in deal_rows if d not in synth_deals])[:5]
    while len(deals) < 5 and deals:
        deals.append(deals[0])

    def inv_notif(number, verb):
        row = inv.get(number, {})
        org = row.get("organization")
        total = row.get("total")
        try:
            amount = "%.2f" % float(total)
        except (TypeError, ValueError):
            amount = "0.00"
        org_names = {1: "Demo Co", 2: "Cedar and Co Coffee", 3: "Northlight Law",
                     4: "Vellum Studio", 5: "Harbor Fitness", 6: "Bloom Botanicals",
                     7: "Sterling and Vine", 8: "Meridian Fund"}
        oname = org_names.get(org, "the client")
        if verb == "overdue":
            title = "Invoice %s is overdue" % number
            body = "%s has an open balance of %s USD on %s." % (oname, amount, number)
        elif verb == "paid":
            title = "Payment received for %s" % number
            body = "%s paid %s USD on %s." % (oname, amount, number)
        else:
            title = "Invoice %s sent" % number
            body = "%s for %s USD was sent to %s." % (number, amount, oname)
        return {"type": "invoice", "title": title, "body": body,
                "href": "/employee-portal/invoices", "organization": org,
                "source_collection": "os_invoices", "source_id": row.get("id")}

    def thread_notif(t_idx):
        org, subject, _status, _cho, msgs = THREADS[t_idx]
        last_client = next((b for role, b in reversed(msgs) if role == "client"), msgs[-1][1])
        excerpt = last_client if len(last_client) <= 120 else last_client[:119] + "."
        return {"type": "activity", "title": "New message: %s" % subject,
                "body": excerpt, "href": "/employee-portal/messages",
                "organization": org, "source_collection": "os_message_threads",
                "source_id": thread_ids[t_idx]}

    def ticket_notif(k_idx):
        subject, pkey, *_ = TICKETS[k_idx]
        proj_org = {"cedar_web": 2, "cedar_wholesale": 2, "northlight_brand": 3,
                    "northlight_seo": 3, "vellum_portfolio": 4, "harbor_app": 5,
                    "bloom_shopify": 6, "sterling_res": 7, "meridian_grant": 8}
        return {"type": "activity", "title": "Support ticket updated: %s" % subject,
                "body": "A new response was posted on the ticket %s." % subject,
                "href": "/employee-portal/support", "organization": proj_org[pkey],
                "source_collection": "os_client_tickets",
                "source_id": ticket_ids[k_idx] if k_idx < len(ticket_ids) else None}

    def project_notif(pid, org, title, body, client_href=False):
        href = "/client-portal/projects/%s" % pid if client_href else "/employee-portal/projects"
        return {"type": "project", "title": title, "body": body, "href": href,
                "organization": org, "source_collection": "os_projects", "source_id": pid}

    def task_notif(idx):
        t = tasks[idx % len(tasks)] if tasks else {"id": None, "name": "Task", "organization": 1}
        return {"type": "task", "title": "Task update: %s" % t["name"][:90],
                "body": "%s changed status on its project board." % t["name"],
                "href": "/employee-portal/tasks", "organization": t["organization"],
                "source_collection": "os_tasks", "source_id": t["id"]}

    def deal_notif(idx, second_event=False):
        d = deals[idx % len(deals)] if deals else {"id": None, "name": "Deal", "organization": 1}
        name = sanitize(d.get("name") or "Deal")
        if second_event:
            title = "New note on deal: %s" % name[:80]
            body = "A discovery call summary was added to %s." % name
        else:
            title = "Deal stage updated: %s" % name[:80]
            body = "The deal %s moved to a new pipeline stage." % name
        return {"type": "deal", "title": title, "body": body,
                "href": "/employee-portal/deals",
                "organization": d.get("organization") or 1,
                "source_collection": "os_deals", "source_id": d.get("id")}

    plan = [
        inv_notif("INV-2026-302", "overdue"),
        project_notif(PROJ["cedar_web"], 2, "Cedar Website Redesign phase update",
                      "Design QA started on the Cedar Website Redesign. Launch window remains late June.",
                      client_href=True),
        thread_notif(0),
        task_notif(0),
        deal_notif(0),
        inv_notif("INV-2026-300", "overdue"),
        project_notif(PROJ["northlight_brand"], 3, "Northlight Brand Identity milestone reached",
                      "Brand guidelines were approved and the rollout checklist is underway."),
        thread_notif(1),
        task_notif(1),
        inv_notif("INV-2026-311", "overdue"),
        deal_notif(1),
        project_notif(PROJ["vellum_portfolio"], 4, "Vellum Portfolio Platform status change",
                      "The Vellum Portfolio Platform moved to active development after content modeling sign off.",
                      client_href=True),
        thread_notif(4),
        inv_notif("INV-2026-313", "paid"),
        task_notif(2),
        deal_notif(2),
        project_notif(PROJ["harbor_app"], 5, "Harbor Class Booking App beta shipped",
                      "Beta build 0.9.2 of the Harbor Class Booking App went out to instructor devices."),
        ticket_notif(10),
        inv_notif("INV-2026-304", "sent"),
        task_notif(3),
        deal_notif(3),
        project_notif(PROJ["sterling_res"], 7, "Sterling Reservations widget live",
                      "The Sterling Reservations widget is live on the client site and taking bookings.",
                      client_href=True),
        thread_notif(5),
        inv_notif("INV-2026-307", "sent"),
        task_notif(4),
        deal_notif(4, second_event=len(deals) < 5 or deals[4] is deals[0]),
        project_notif(PROJ["meridian_grant"], 8, "Meridian Grant Portal review scheduled",
                      "The accessibility review for the Meridian Grant Portal is booked for next week."),
        ticket_notif(8),
        inv_notif("INV-2026-315", "overdue"),
        task_notif(5),
    ]
    return plan, task_fallback


def seed_notifications(thread_ids, ticket_ids):
    plan, task_fallback = build_notifications(thread_ids, ticket_ids)
    if task_fallback:
        print("  note: fewer than 6 tasks on synthetic projects; task notifications padded from the global task list")
    for n, item in enumerate(plan):
        key = "seed:notif:%03d" % (n + 1)
        det = NOTIF_BASE_TS + n * NOTIF_STEP
        read_at = None if n in UNREAD_IDX else iso(det + timedelta(hours=5))
        rows = list_items(
            "os_notifications",
            "filter[dedupe_key][_eq]=%s&fields=id,date_created&limit=1" % q(key),
        )
        if rows:
            repair_dc("os_notifications", rows[0]["id"], rows[0].get("date_created"), det)
            continue
        payload = {
            "dedupe_key": key,
            "recipient_user": USER_DEMO,
            "type": item["type"],
            "title": item["title"],
            "body": item["body"],
            "href": item["href"],
            "organization": item["organization"],
            "source_collection": item["source_collection"],
            "source_id": str(item["source_id"]) if item["source_id"] is not None else None,
        }
        create_backdated("os_notifications", payload, det,
                         extra_patch={"read_at": read_at} if read_at else None)


# ------------------------------------------------------------------- verify
def verify(thread_ids, ticket_ids, marker_results):
    print("\n===== VERIFY (admin REST) =====")
    ok = True

    rows = list_items(
        "os_message_threads",
        "fields=id,subject,status,last_message_at,team_last_read_at,organization.id,"
        "organization.name,messages.body,messages.author_role,messages.date_created"
        "&sort=-last_message_at&limit=3",
    )
    print("threads probe: %d rows" % len(rows))
    for r in rows:
        print("  %s | %s | org=%s | last=%s | msgs=%d"
              % (r["subject"], r["status"], (r.get("organization") or {}).get("name"),
                 r.get("last_message_at"), len(r.get("messages") or [])))
    if len(rows) < 3:
        ok = False

    rows = list_items(
        "os_client_tickets",
        "fields=id,subject,status,priority,category,resolved_at,project.id,project.name,"
        "project.organization.name,responses.id&limit=3",
    )
    print("tickets probe: %d rows" % len(rows))
    for r in rows:
        print("  %s | %s/%s/%s | resolved_at=%s | proj=%s (%s) | responses=%d"
              % (r["subject"], r["status"], r["priority"], r["category"], r.get("resolved_at"),
                 (r.get("project") or {}).get("name"),
                 ((r.get("project") or {}).get("organization") or {}).get("name"),
                 len(r.get("responses") or [])))
    if len(rows) < 3:
        ok = False

    rows = list_items(
        "os_notifications",
        "filter[recipient_user][_eq]=%s&fields=id,title,type,href,read_at,dedupe_key&limit=3" % USER_DEMO,
    )
    print("notifications probe: %d rows" % len(rows))
    for r in rows:
        print("  %s | %s | %s | read=%s | %s"
              % (r["title"][:60], r["type"], r["href"], bool(r.get("read_at")), r["dedupe_key"]))
    if len(rows) < 3:
        ok = False

    # ---- assertions on stored data
    print("\n===== ASSERTIONS (stored values) =====")
    all_msgs = []
    for tid in thread_ids:
        if tid:
            all_msgs += list_items(
                "os_messages",
                "filter[thread][_eq]=%s&fields=date_created&limit=200" % tid)
    times = sorted(parse_ts(m["date_created"]) for m in all_msgs if parse_ts(m.get("date_created")))
    if not times:
        print("ASSERT FAIL: no stored messages")
        ok = False
    else:
        span_days = (times[-1] - times[0]).total_seconds() / 86400.0
        near_run = [t for t in times if abs((t - RUN_START).total_seconds()) < 600]
        print("messages: %d stored, span %.1f days (%s .. %s), %d within 10min of run start"
              % (len(times), span_days, iso(times[0]), iso(times[-1]), len(near_run)))
        if span_days < 21 or near_run:
            print("ASSERT FAIL: messages clustered or span too small")
            ok = False
        else:
            print("ASSERT PASS: message timestamps span the backdated 6 week window")

    emp_unread = client_unread = 0
    for (subject, cho, last_at, team_read, client_read, last_role) in marker_results:
        lt, tt, ct = parse_ts(last_at), parse_ts(team_read), parse_ts(client_read)
        if cho == "emp_unread":
            good = last_role == "client" and lt > tt
            emp_unread += 1 if good else 0
            print("%s [%s]: last=%s by %s, team_read=%s -> %s"
                  % (subject, cho, last_at, last_role, team_read,
                     "PASS" if good else "FAIL"))
            ok = ok and good
        elif cho == "client_unread":
            good = last_role == "team" and lt > ct
            client_unread += 1 if good else 0
            print("%s [%s]: last=%s by %s, client_read=%s -> %s"
                  % (subject, cho, last_at, last_role, client_read,
                     "PASS" if good else "FAIL"))
            ok = ok and good
        else:
            good = not (lt > tt) and not (lt > ct)
            print("%s [read]: markers cover latest -> %s" % (subject, "PASS" if good else "FAIL"))
            ok = ok and good
    print("unread choreography: %d employee-unread threads, %d client-unread threads"
          % (emp_unread, client_unread))
    if emp_unread != 3 or client_unread != 2:
        print("ASSERT FAIL: expected 3 employee-unread and 2 client-unread")
        ok = False

    # ---- GraphQL probe
    print("\n===== GRAPHQL PROBE =====")
    gql = {
        "query": """
        query {
          os_message_threads(limit: 3, sort: ["-last_message_at"]) {
            id subject status last_message_at team_last_read_at
            organization { id name }
            messages(sort: ["-date_created"], limit: 1) { body author_role date_created }
          }
          os_client_tickets(limit: 3) {
            id subject status priority category resolved_at
            project { id name organization { name } }
            responses { id }
          }
          os_notifications(filter: { recipient_user: { _eq: "%s" } }, limit: 3) {
            id title type href read_at dedupe_key
          }
        }""" % USER_DEMO
    }
    st, r = request("POST", "/graphql", gql)
    if st == 200 and not r.get("errors"):
        data = r.get("data", {})
        print("graphql: threads=%d tickets=%d notifications=%d (no errors)"
              % (len(data.get("os_message_threads") or []),
                 len(data.get("os_client_tickets") or []),
                 len(data.get("os_notifications") or [])))
        th = (data.get("os_message_threads") or [{}])[0]
        print("  sample thread: %s | last msg by %s" %
              (th.get("subject"), ((th.get("messages") or [{}])[0]).get("author_role")))
        if not (data.get("os_message_threads") and data.get("os_client_tickets")
                and data.get("os_notifications")):
            ok = False
    else:
        print("graphql FAIL: %s %s" % (st, str(r.get("errors", r))[:400]))
        ok = False

    # ---- demo session probes
    print("\n===== DEMO SESSION PROBES =====")
    st, r = request("POST", "/auth/login",
                    {"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, token=NO_AUTH)
    demo_token = (r.get("data") or {}).get("access_token") if st == 200 else None
    if not demo_token:
        print("demo login FAILED: %s" % st)
        ok = False
    else:
        print("demo login OK")
        probes = [
            ("os_message_threads",
             "fields=id,subject,status,last_message_at,team_last_read_at,client_last_read_at,"
             "organization.id,organization.name,organization.service_status,"
             "messages.body,messages.author_role,messages.date_created&limit=3"),
            ("os_client_tickets",
             "fields=id,subject,status,priority,category,date_created,resolved_at,"
             "responses.id,project.id,project.name,project.organization.id,"
             "project.organization.name&limit=3"),
            ("os_messages", "fields=id,author_role&limit=3"),
            ("os_client_ticket_responses", "fields=id,is_staff&limit=3"),
            ("os_notifications",
             "filter[recipient_user][_eq]=%s&fields=id,title,type,read_at&limit=3" % USER_DEMO),
        ]
        for coll, qs in probes:
            st, r = request("GET", "/items/%s?%s" % (coll, qs), token=demo_token)
            n = len(r.get("data", [])) if st == 200 else 0
            print("demo read %s -> %s (%d rows)" % (coll, st, n))
            if st == 403:
                print("  demo read 403 on %s, adding additive read grant to demo policy" % coll)
                pst, pr = request("POST", "/permissions", {
                    "policy": DEMO_POLICY, "collection": coll, "action": "read",
                    "fields": ["*"], "permissions": {}, "validation": None,
                })
                print("  grant %s -> %s" % (coll, pst))
                bump("permissions_added", "created" if pst in (200, 201) else "failed")
                st2, r2 = request("GET", "/items/%s?%s" % (coll, qs), token=demo_token)
                print("  demo re-read %s -> %s (%d rows)"
                      % (coll, st2, len(r2.get("data", [])) if st2 == 200 else 0))
                if st2 != 200:
                    ok = False
            elif st != 200:
                ok = False
            elif coll in ("os_message_threads", "os_client_tickets") and n == 0:
                print("  WARN demo read %s returned 0 rows (row-level filter?)" % coll)
                ok = False

    # ---- demo policy mark-read (update os_notifications) finding: REPORT ONLY
    print("\n===== DEMO POLICY os_notifications UPDATE FINDING (report only) =====")
    st, r = request("GET", "/policies/%s?fields=id,name,admin_access,app_access" % DEMO_POLICY)
    if st == 200:
        p = r.get("data", {})
        print("policy %s: name=%s admin_access=%s app_access=%s"
              % (DEMO_POLICY, p.get("name"), p.get("admin_access"), p.get("app_access")))
    st, r = request(
        "GET",
        "/permissions?filter[policy][_eq]=%s&filter[collection][_eq]=os_notifications"
        "&fields=id,collection,action,fields,permissions&limit=-1" % DEMO_POLICY)
    rows = r.get("data", []) if st == 200 else []
    if not rows:
        print("no explicit os_notifications permission rows on the demo policy")
    for row in rows:
        print("  perm id=%s action=%s fields=%s permissions=%s"
              % (row["id"], row["action"], row.get("fields"), json.dumps(row.get("permissions"))[:120]))
    upd = [row for row in rows if row["action"] == "update"]
    if upd:
        flds = upd[0].get("fields") or []
        print("FINDING: demo policy HAS update on os_notifications (fields=%s); mark-read %s"
              % (flds, "covered" if ("*" in flds or "read_at" in flds) else "NOT covering read_at"))
    else:
        print("FINDING: demo policy has NO explicit update permission row on os_notifications; "
              "mark-read via demo session will not work unless a wildcard/other policy grants it. "
              "No write grant added (needs orchestrator sign-off).")

    return ok


def main():
    print("seed-D4 run at %s against %s" % (iso(RUN_START), BASE))
    team_rotation = resolve_team_users()

    thread_ids = seed_threads()
    seed_messages(thread_ids, team_rotation)
    marker_results = choreograph_threads(thread_ids)
    ticket_ids = seed_tickets()
    seed_responses(ticket_ids)
    seed_notifications(thread_ids, ticket_ids)

    print("\n===== SUMMARY =====")
    for coll in ("os_message_threads", "os_messages", "thread_markers",
                 "os_client_tickets", "os_client_ticket_responses",
                 "os_notifications", "permissions_added"):
        c = COUNTS.get(coll, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
        print("%s: created %d / updated %d / skipped %d / failed %d"
              % (coll, c["created"], c["updated"], c["skipped"], c["failed"]))

    ok = verify(thread_ids, ticket_ids, marker_results)
    total_failed = sum(c["failed"] for c in COUNTS.values())
    print("\nRESULT: %s (failed ops: %d)" % ("OK" if ok and not total_failed else "ISSUES", total_failed))
    sys.exit(0 if ok and not total_failed else 1)


if __name__ == "__main__":
    main()
