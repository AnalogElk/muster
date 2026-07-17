#!/usr/bin/env python3
"""D1 domain-crm seeder for the Muster demo (cms.musterr.dev).

Seeds: os_deals (11 new, total 15 across all 8 orgs and all 5 stages),
os_deal_contacts (1-2 per deal incl. the 4 existing deals),
os_activities (30 new, total 33, last 6 months plus coming 2 weeks),
os_activity_contacts (1-2 per activity incl. the 3 existing ones),
os_proposals (5 new, total 6: draft/submitted/approved/voided mix),
os_proposal_contacts (1-2 per proposal), and
os_proposal_approvals (one published row per approved proposal).

Rules honored: add-only, idempotent upsert by natural key, is_test_data false
on every row that has the field, enum values only, no em dashes anywhere,
existing rows never edited, token loaded inside this script and never printed.
Run-day date_created is left alone (no backdating; timelines use due_date,
close_date, next_contact_date, expiration_date plain fields).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("DIRECTUS_URL", "https://cms.musterr.dev").rstrip("/")
TODAY = "2026-07-16"

STAGE_LEAD = "81fdea8c-ffd0-48b0-8816-ee76bbc28f04"
STAGE_QUALIFIED = "cc8f1d39-cc6e-4e76-b83c-04caa601eec0"
STAGE_PROPOSAL = "0ba6c5e9-1b90-450a-8033-a996224aa54b"
STAGE_NEGOTIATION = "58707423-12f0-42a4-9d9f-9051816a5bd1"
STAGE_WON = "01668fb5-ecbb-4ad6-8518-bfc06fd25887"
ALL_STAGE_IDS = {STAGE_LEAD, STAGE_QUALIFIED, STAGE_PROPOSAL, STAGE_NEGOTIATION, STAGE_WON}

USER_DEMO = "257a4b75-deff-476d-953d-1898c57f6684"
USER_ADMIN = "34d67d59-16c3-41c4-9efb-7fd51a216460"
F3_FALLBACK = {
    "mara.lindqvist@team.musterr.dev": "3f3b7c79-4c79-4865-8592-5a303db8b995",
    "devon.okafor@team.musterr.dev": "06fb5978-93dd-4a13-b02e-48f7271d7301",
    "elena.vasquez@team.musterr.dev": "1e7ce5df-3dea-4fd4-bd35-cfd9c32f8852",
}
# F3 output contract fallback (used only if live junction table is unreadable)
CONTRACT_CONTACT_TO_ORG = {
    1: 1, 2: 1, 3: 1, 4: 4, 5: 5, 6: 6, 7: 2, 8: 3, 9: 7, 10: 8, 11: 8,
    12: 2, 13: 2, 14: 3, 15: 3, 16: 4, 17: 4, 18: 5, 19: 5, 20: 6, 21: 6,
    22: 7, 23: 7, 24: 7, 25: 8, 26: 8,
}
ORG_NAMES = {
    1: "Demo Co", 2: "Cedar & Co Coffee", 3: "Northlight Law", 4: "Vellum Studio",
    5: "Harbor Fitness", 6: "Bloom Botanicals", 7: "Sterling & Vine", 8: "Meridian Fund",
}
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"


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
            return e.code, {"_raw": body}
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    return 0, {}


COUNTS = {}


def bump(coll, key):
    COUNTS.setdefault(coll, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
    COUNTS[coll][key] += 1


def q(v):
    return urllib.parse.quote(str(v), safe="")


def find_one(coll, filters):
    parts = ["filter[%s][_eq]=%s" % (f, q(v)) for f, v in filters.items()]
    st, r = request("GET", "/items/%s?%s&fields=id&limit=1" % (coll, "&".join(parts)))
    if st == 200 and r.get("data"):
        return r["data"][0]["id"]
    return None


def upsert(coll, filters, payload):
    existing = find_one(coll, filters)
    if existing is not None:
        bump(coll, "skipped")
        return existing, False
    st, r = request("POST", "/items/" + coll, payload)
    if st in (200, 201):
        bump(coll, "created")
        return r["data"]["id"], True
    bump(coll, "failed")
    print("  FAIL %s %s -> %s %s" % (coll, filters, st, str(r)[:200]))
    return None, False


# ---------------------------------------------------------------- resolve refs
def resolve_users():
    emails = ",".join(F3_FALLBACK.keys())
    st, r = request("GET", "/users?filter[email][_in]=%s&fields=id,email&limit=-1" % q(emails).replace("%2C", ","))
    users = {}
    if st == 200:
        for u in r.get("data", []):
            users[u["email"]] = u["id"]
    for e, uid in F3_FALLBACK.items():
        users.setdefault(e, uid)
    return {
        "demo": USER_DEMO,
        "admin": USER_ADMIN,
        "mara": users["mara.lindqvist@team.musterr.dev"],
        "devon": users["devon.okafor@team.musterr.dev"],
        "elena": users["elena.vasquez@team.musterr.dev"],
    }


def resolve_membership():
    st, r = request("GET", "/items/organizations_contacts?limit=-1&fields=organizations_id,contacts_id")
    members = {}
    if st == 200 and r.get("data"):
        for row in r["data"]:
            o = row.get("organizations_id")
            c = row.get("contacts_id")
            if isinstance(o, dict):
                o = o.get("id")
            if isinstance(c, dict):
                c = c.get("id")
            if o is not None and c is not None:
                members.setdefault(int(o), set()).add(int(c))
    if not members:
        for c, o in CONTRACT_CONTACT_TO_ORG.items():
            members.setdefault(o, set()).add(c)
    primary = {o: min(cs) for o, cs in members.items()}
    return members, primary


def resolve_contacts():
    st, r = request("GET", "/items/contacts?limit=-1&fields=id,first_name,last_name,email")
    out = {}
    if st == 200:
        for c in r.get("data", []):
            out[int(c["id"])] = c
    return out


# ------------------------------------------------------------------- seed data
EX = "__existing__:"  # prefix marks a lookup of a pre-existing row by exact name

NEW_DEALS = [
    dict(key="cedar_loyalty", name="Cedar & Co Loyalty App Discovery", org=2,
         stage=STAGE_LEAD, value=6500, close="2026-09-30",
         next_contact="2026-07-21T10:00:00", owner="mara",
         notes="Cedar wants a punch-card style loyalty app for their two cafe locations. Discovery is scoped as a two week sprint."),
    dict(key="cedar_wholesale", name="Cedar & Co Wholesale Portal Phase 2", org=2,
         stage=STAGE_WON, value=28000, close="2026-06-12",
         next_contact="2026-07-24T15:00:00", owner="admin",
         notes="Phase 2 adds wholesale ordering workflows and inventory sync. Signed after the phase 1 portal shipped on time."),
    dict(key="northlight_intake", name="Northlight Law Client Intake Automation", org=3,
         stage=STAGE_NEGOTIATION, value=42000, close="2026-08-14",
         next_contact="2026-07-20T14:00:00", owner="devon",
         notes="Automating intake forms, conflict checks and engagement letters. Legal review of the MSA is the last open item."),
    dict(key="vellum_portfolio", name="Vellum Studio Portfolio Refresh", org=4,
         stage=STAGE_QUALIFIED, value=12500, close="2026-09-11",
         next_contact="2026-07-28T16:00:00", owner="elena",
         notes="Refresh of the studio portfolio with a CMS-driven case study format. Budget confirmed by the founder."),
    dict(key="harbor_member_app", name="Harbor Fitness Member App", org=5,
         stage=STAGE_NEGOTIATION, value=64000, close="2026-08-28",
         next_contact="2026-07-22T17:00:00", owner="admin",
         notes="Member app with class booking, waitlists and push reminders. Negotiating the payment schedule across two gym locations."),
    dict(key="harbor_schedule", name="Harbor Fitness Class Schedule Integration", org=5,
         stage=STAGE_LEAD, value=9000, close="2026-10-09",
         next_contact="2026-08-03T15:00:00", owner="elena",
         notes="Inbound request to sync the class schedule onto the marketing site. Waiting on API credentials to size the work."),
    dict(key="bloom_subscription", name="Bloom Botanicals Subscription Storefront", org=6,
         stage=STAGE_PROPOSAL, value=31000, close="2026-08-21",
         next_contact="2026-07-27T14:30:00", owner="mara",
         notes="Monthly plant subscription storefront with recurring billing. Proposal delivered and walkthrough completed."),
    dict(key="sterling_reservations", name="Sterling & Vine Reservations Platform", org=7,
         stage=STAGE_NEGOTIATION, value=48500, close="2026-08-07",
         next_contact="2026-07-17T18:00:00", owner="admin",
         notes="Tasting room reservations platform with POS integration. Scope v2 replaced the original proposal after the demo."),
    dict(key="sterling_events", name="Sterling & Vine Private Events Microsite", org=7,
         stage=STAGE_QUALIFIED, value=14000, close="2026-09-18",
         next_contact="2026-07-30T16:00:00", owner="elena",
         notes="Microsite for private event bookings at the vineyard. Qualified after the discovery call with the events team."),
    dict(key="meridian_report", name="Meridian Annual Report Microsite", org=8,
         stage=STAGE_PROPOSAL, value=22000, close="2026-08-31",
         next_contact="2026-07-23T15:00:00", owner="devon",
         notes="Interactive annual report microsite for the 2026 giving cycle. Proposal is in front of the program director."),
    dict(key="meridian_crm", name="Meridian Fund Donor CRM Rollout", org=8,
         stage=STAGE_WON, value=56000, close="2026-05-22",
         next_contact="2026-07-29T15:00:00", owner="admin",
         notes="Donor CRM implementation with migration from legacy spreadsheets. Won in May and now in delivery."),
]

# (deal ref, [(contact_id, primary)]) ; EX-prefixed refs are pre-existing deals
DEAL_CONTACTS = [
    (EX + "Demo Co \u2014 Muster Self-Host License", [(1, True), (2, False)]),
    (EX + "Acme Retail \u2014 Portal Rebuild", [(2, True), (3, False)]),
    (EX + "Bluebird Media \u2014 CRM Migration", [(3, True)]),
    (EX + "Cedar & Co \u2014 Discovery Engagement", [(1, True)]),
    ("cedar_loyalty", [(7, True), (12, False)]),
    ("cedar_wholesale", [(7, True), (13, False)]),
    ("northlight_intake", [(8, True), (14, False)]),
    ("vellum_portfolio", [(4, True), (16, False)]),
    ("harbor_member_app", [(5, True), (18, False)]),
    ("harbor_schedule", [(19, True)]),
    ("bloom_subscription", [(6, True), (20, False)]),
    ("sterling_reservations", [(9, True), (22, False)]),
    ("sterling_events", [(24, True)]),
    ("meridian_report", [(10, True), (25, False)]),
    ("meridian_crm", [(11, True), (26, False)]),
]

# (name, type, status, due, minutes|None, org, deal ref|None, assignee, note, [contacts])
NEW_ACTIVITIES = [
    ("Cedar & Co loyalty discovery call", "call", "completed", "2026-07-08T16:00:00Z", 45, 2, "cedar_loyalty", "mara",
     "Walked through the loyalty concept and current POS setup with the owner.", [7, 12]),
    ("Cedar & Co loyalty scope review meeting", "meeting", "open", "2026-07-21T17:00:00Z", 60, 2, "cedar_loyalty", "mara",
     "Review the draft scope and sprint plan for the loyalty app discovery.", [7]),
    ("Cedar wholesale portal phase 2 kickoff", "meeting", "completed", "2026-06-18T15:00:00Z", 60, 2, "cedar_wholesale", "admin",
     "Kickoff covering ordering workflows, inventory sync and the rollout plan.", [12, 13]),
    ("Send Cedar staff training recap email", "email", "completed", "2026-06-25T14:00:00Z", None, 2, None, "mara",
     "Recap of the wholesale portal training session with links to the guides.", [13]),
    ("Northlight intake automation demo call", "call", "completed", "2026-06-30T18:00:00Z", 45, 3, "northlight_intake", "devon",
     "Demoed the intake form builder and conflict check workflow to the partners.", [8, 14]),
    ("Northlight contract redlines review", "meeting", "open", "2026-07-20T16:00:00Z", 60, 3, "northlight_intake", "devon",
     "Walk through the MSA redlines with their counsel before signature.", [8]),
    ("Northlight quarterly account review email", "email", "completed", "2026-07-10T13:00:00Z", None, 3, None, "admin",
     "Quarterly summary of support hours and upcoming maintenance windows.", [8]),
    ("Northlight security questionnaire deadline", "deadline", "open", "2026-07-24T20:00:00Z", None, 3, "northlight_intake", "devon",
     "Vendor security questionnaire due back to their IT committee.", [15]),
    ("Vellum portfolio requirements call", "call", "completed", "2026-07-02T17:30:00Z", 30, 4, "vellum_portfolio", "elena",
     "Confirmed the case study structure and the migration list for the refresh.", [4, 16]),
    ("Vellum moodboard review meeting", "meeting", "open", "2026-07-28T16:00:00Z", 45, 4, "vellum_portfolio", "elena",
     "Present two art directions for the refreshed portfolio.", [4]),
    ("Vellum studio quarterly check-in", "call", "completed", "2026-04-14T16:00:00Z", 30, 4, None, "demo",
     "Quarterly relationship check-in and roadmap chat with the founder.", [17]),
    ("Harbor member app pricing call", "call", "completed", "2026-07-09T15:00:00Z", 45, 5, "harbor_member_app", "admin",
     "Discussed the phased payment schedule across both gym locations.", [5, 18]),
    ("Harbor member app contract review", "meeting", "open", "2026-07-22T17:00:00Z", 60, 5, "harbor_member_app", "admin",
     "Final contract review with the ops lead before countersignature.", [5]),
    ("Harbor schedule integration intro email", "email", "completed", "2026-07-13T14:30:00Z", None, 5, "harbor_schedule", "elena",
     "Sent the integration overview and the API credential checklist.", [19]),
    ("Harbor Fitness site audit follow-up", "email", "completed", "2026-01-28T15:00:00Z", None, 5, None, "demo",
     "Followed up on the winter site audit findings and quick wins.", [18]),
    ("Bloom subscription storefront walkthrough", "meeting", "completed", "2026-07-07T16:00:00Z", 60, 6, "bloom_subscription", "mara",
     "Walked the marketing director through the proposal and demo storefront.", [6, 20]),
    ("Send Bloom proposal follow-up email", "email", "open", "2026-07-17T14:00:00Z", None, 6, "bloom_subscription", "mara",
     "Follow up on open questions about recurring billing fees.", [6]),
    ("Bloom proposal decision deadline", "deadline", "open", "2026-07-27T20:00:00Z", None, 6, "bloom_subscription", "mara",
     "Bloom committed to a go or no-go decision by the end of the month.", [6]),
    ("Bloom spring campaign retro call", "call", "completed", "2026-03-24T15:00:00Z", 30, 6, None, "elena",
     "Retro on the spring campaign landing pages and conversion numbers.", [21]),
    ("Sterling reservations platform demo", "meeting", "completed", "2026-06-26T17:00:00Z", 60, 7, "sterling_reservations", "admin",
     "Live demo of the reservations flow and POS handoff for the tasting room.", [9, 22]),
    ("Sterling reservations legal review call", "call", "open", "2026-07-17T18:00:00Z", 45, 7, "sterling_reservations", "admin",
     "Review liability language in the platform agreement with their counsel.", [9, 23]),
    ("Sterling private events discovery call", "call", "completed", "2026-07-06T16:30:00Z", 30, 7, "sterling_events", "elena",
     "Scoped the private events microsite with the events coordinator.", [24]),
    ("Sterling tasting room photo shoot deadline", "deadline", "completed", "2026-05-15T19:00:00Z", None, 7, None, "demo",
     "Final date for the tasting room photo assets used across the site.", [22]),
    ("Meridian annual report scope meeting", "meeting", "completed", "2026-06-24T15:00:00Z", 45, 8, "meridian_report", "devon",
     "Scoped the interactive annual report sections with the program team.", [10, 25]),
    ("Email Meridian microsite proposal", "email", "completed", "2026-07-01T13:30:00Z", None, 8, "meridian_report", "devon",
     "Delivered the annual report microsite proposal and timeline.", [10]),
    ("Meridian board presentation deadline", "deadline", "open", "2026-07-23T16:00:00Z", None, 8, None, "devon",
     "Board reviews the digital program budget including the microsite.", [10]),
    ("Meridian donor CRM go-live review", "meeting", "completed", "2026-05-28T16:00:00Z", 60, 8, "meridian_crm", "admin",
     "Go-live readiness review for the donor CRM rollout.", [11, 26]),
    ("Meridian donor data migration check-in call", "call", "completed", "2026-05-06T15:00:00Z", 30, 8, None, "devon",
     "Checked the migration mapping for the legacy donor spreadsheets.", [25]),
    ("Acme portal rebuild status call", "call", "completed", "2026-07-03T16:00:00Z", 30, 1, EX + "Acme Retail \u2014 Portal Rebuild", "demo",
     "Status call on the portal rebuild pipeline and next milestones.", [2]),
    ("Bluebird CRM migration data audit", "deadline", "completed", "2026-06-05T17:00:00Z", None, 1, EX + "Bluebird Media \u2014 CRM Migration", "demo",
     "Deadline for the source CRM data audit before migration planning.", [3]),
]

# contacts for the 3 pre-existing activities (junction table is empty today)
EXISTING_ACTIVITY_CONTACTS = [
    ("Kickoff call with Demo Co", [1, 2]),
    ("Portal walkthrough demo", [1, 3]),
    ("Send SOW follow-up email", [1]),
]

NEW_PROPOSALS = [
    dict(name="Bloom Botanicals Subscription Storefront Proposal", deal="bloom_subscription", org=6,
         status="submitted", expiration="2026-08-10T00:00:00Z", total="31000.00",
         items=[("Subscription storefront build", 1, 18500),
                ("Recurring billing integration", 1, 7500),
                ("Content migration and launch QA", 1, 5000)],
         notes="<p>Monthly plant subscription storefront with recurring billing and a member portal.</p><p>Timeline is eight weeks from kickoff with a soft launch to the existing newsletter list.</p>",
         contacts=[6, 20]),
    dict(name="Meridian Annual Report Microsite Proposal", deal="meridian_report", org=8,
         status="draft", expiration="2026-08-30T00:00:00Z", total="22000.00",
         items=[("Design and art direction", 1, 9000),
                ("Microsite development", 1, 10000),
                ("Accessibility and launch support", 1, 3000)],
         notes="<p>Interactive annual report microsite for the 2026 giving cycle.</p><p>Draft pending the final section list from the program team.</p>",
         contacts=[10]),
    dict(name="Cedar & Co Wholesale Portal Phase 2 SOW", deal="cedar_wholesale", org=2,
         status="approved", expiration="2026-06-05T00:00:00Z", total="28000.00",
         items=[("Wholesale ordering workflows", 1, 16000),
                ("Inventory sync integration", 1, 8000),
                ("Staff training and rollout", 1, 4000)],
         notes="<p>Phase 2 statement of work covering wholesale ordering, inventory sync and staff rollout.</p><p>Approved by the owner ahead of the June kickoff.</p>",
         contacts=[7, 13]),
    dict(name="Meridian Fund Donor CRM Rollout SOW", deal="meridian_crm", org=8,
         status="approved", expiration="2026-05-15T00:00:00Z", total="56000.00",
         items=[("CRM implementation and configuration", 1, 32000),
                ("Donor data migration", 1, 14000),
                ("Reporting dashboards", 2, 3500),
                ("Team onboarding sessions", 3, 1000)],
         notes="<p>Implementation of the donor CRM with migration from legacy spreadsheets.</p><p>Includes reporting dashboards and onboarding for the development team.</p>",
         contacts=[10, 11]),
    dict(name="Sterling & Vine Reservations Platform Proposal v1", deal="sterling_reservations", org=7,
         status="voided", expiration="2026-06-30T00:00:00Z", total="45000.00",
         items=[("Reservations platform build", 1, 30000),
                ("POS integration", 1, 9000),
                ("Launch support retainer", 3, 2000)],
         notes="<p>Original reservations platform proposal for the tasting room.</p><p>Voided and superseded by the revised scope agreed during negotiation.</p>",
         contacts=[9]),
]

EXISTING_PROPOSAL_CONTACTS = [
    ("Muster Self-Host \u2014 Statement of Work", [1, 2]),
]

APPROVAL_IPS = {"Cedar & Co Wholesale Portal Phase 2 SOW": "203.0.113.24",
                "Meridian Fund Donor CRM Rollout SOW": "203.0.113.87"}


def add_minutes(iso_z, minutes):
    import datetime
    dt = datetime.datetime.strptime(iso_z, "%Y-%m-%dT%H:%M:%SZ")
    return (dt + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    users = resolve_users()
    members, primary_by_org = resolve_membership()
    contacts = resolve_contacts()

    def check_member(cid, org, ctx):
        if org in members and cid not in members[org]:
            print("  WARN %s: contact %s not in org %s membership" % (ctx, cid, org))

    # -------------------------------------------------------- 1) os_deals
    deal_ids = {}
    for d in NEW_DEALS:
        payload = {
            "name": d["name"], "organization": d["org"], "deal_stage": d["stage"],
            "deal_value": d["value"], "close_date": d["close"],
            "next_contact_date": d["next_contact"], "deal_notes": d["notes"],
            "owner": users[d["owner"]], "is_test_data": False,
        }
        did, _ = upsert("os_deals", {"name": d["name"]}, payload)
        if did:
            deal_ids[d["key"]] = did

    # map of every deal name -> id (covers pre-existing rows too)
    st, r = request("GET", "/items/os_deals?limit=-1&fields=id,name")
    name_to_deal = {row["name"]: row["id"] for row in r.get("data", [])} if st == 200 else {}

    def deal_ref_to_id(ref):
        if ref is None:
            return None
        if ref.startswith(EX):
            return name_to_deal.get(ref[len(EX):])
        return deal_ids.get(ref) or name_to_deal.get(ref)

    # ------------------------------------------------ 2) os_deal_contacts
    for ref, pairs in DEAL_CONTACTS:
        did = deal_ref_to_id(ref)
        if not did:
            print("  WARN os_deal_contacts: deal not found for ref %s" % ref)
            bump("os_deal_contacts", "failed")
            continue
        for cid, is_primary in pairs:
            upsert("os_deal_contacts",
                   {"os_deals_id": did, "contacts_id": cid},
                   {"os_deals_id": did, "contacts_id": cid, "primary": is_primary})

    # --------------------------------------------------- 3) os_activities
    activity_ids = {}
    for (name, atype, status, due, minutes, org, dref, assignee, note, _c) in NEW_ACTIVITIES:
        payload = {
            "name": name, "activity_type": atype, "status": status,
            "due_date": due, "organization": org,
            "assigned_to": users[assignee], "activity_notes": note,
            "is_test_data": False,
        }
        if minutes:
            payload["start_time"] = due
            payload["end_time"] = add_minutes(due, minutes)
        did = deal_ref_to_id(dref)
        if did:
            payload["deal"] = did
        aid, _ = upsert("os_activities", {"name": name}, payload)
        if aid:
            activity_ids[name] = aid

    st, r = request("GET", "/items/os_activities?limit=-1&fields=id,name")
    name_to_activity = {row["name"]: row["id"] for row in r.get("data", [])} if st == 200 else {}

    # -------------------------------------------- 4) os_activity_contacts
    junction_specs = [(name, cids) for (name, _t, _s, _d, _m, _o, _dr, _a, _n, cids) in NEW_ACTIVITIES]
    junction_specs += EXISTING_ACTIVITY_CONTACTS
    for name, cids in junction_specs:
        aid = name_to_activity.get(name)
        if not aid:
            print("  WARN os_activity_contacts: activity not found: %s" % name)
            bump("os_activity_contacts", "failed")
            continue
        for cid in cids:
            upsert("os_activity_contacts",
                   {"os_activities_id": aid, "contacts_id": cid},
                   {"os_activities_id": aid, "contacts_id": cid})

    # ---------------------------------------------------- 5) os_proposals
    proposal_ids = {}
    approved_ids = []
    for p in NEW_PROPOSALS:
        items = [{"description": d, "quantity": qty, "unit_price": up, "amount": qty * up}
                 for (d, qty, up) in p["items"]]
        payload = {
            "name": p["name"], "deal": deal_ref_to_id(p["deal"]), "organization": p["org"],
            "status": p["status"], "expiration_date": p["expiration"],
            "total": p["total"], "line_items": items,
            "proposal_notes": p["notes"], "is_test_data": False,
        }
        pid, _ = upsert("os_proposals", {"name": p["name"]}, payload)
        if pid:
            proposal_ids[p["name"]] = pid
            if p["status"] == "approved":
                approved_ids.append((p["name"], pid, p["org"]))

    st, r = request("GET", "/items/os_proposals?limit=-1&fields=id,name")
    name_to_proposal = {row["name"]: row["id"] for row in r.get("data", [])} if st == 200 else {}

    # -------------------------------------------- 6) os_proposal_contacts
    prop_junctions = [(p["name"], p["contacts"]) for p in NEW_PROPOSALS] + EXISTING_PROPOSAL_CONTACTS
    for name, cids in prop_junctions:
        pid = name_to_proposal.get(name)
        if not pid:
            print("  WARN os_proposal_contacts: proposal not found: %s" % name)
            bump("os_proposal_contacts", "failed")
            continue
        for cid in cids:
            upsert("os_proposal_contacts",
                   {"os_proposals_id": pid, "contacts_id": cid},
                   {"os_proposals_id": pid, "contacts_id": cid})

    # ------------------------------------------- 7) os_proposal_approvals
    for pname, pid, org in approved_ids:
        primary_cid = primary_by_org.get(org)
        c = contacts.get(primary_cid, {})
        email = c.get("email") or ("contact%s@example.com" % primary_cid)
        fname = c.get("first_name") or "Primary"
        lname = c.get("last_name") or "Contact"
        upsert("os_proposal_approvals",
               {"proposal": pid, "email": email},
               {"proposal": pid, "contact": primary_cid, "email": email,
                "first_name": fname, "last_name": lname,
                "signature_type": "typed",
                "signature_text": (fname + " " + lname).strip(),
                "esignature_agreement": True,
                "ip_address": APPROVAL_IPS.get(pname, "203.0.113.10"),
                "organization": ORG_NAMES.get(org, str(org)),
                "status": "published", "is_test_data": False})

    # membership sanity warnings (report-only)
    for ref, pairs in DEAL_CONTACTS:
        did = deal_ref_to_id(ref)
        if not did:
            continue
        org = None
        for d in NEW_DEALS:
            if d["key"] == (ref if not ref.startswith(EX) else None):
                org = d["org"]
        if org:
            for cid, _p in pairs:
                check_member(cid, org, "deal " + ref)

    # ---------------------------------------------------------- summary
    print("")
    for coll in ["os_deals", "os_deal_contacts", "os_activities", "os_activity_contacts",
                 "os_proposals", "os_proposal_contacts", "os_proposal_approvals"]:
        c = COUNTS.get(coll, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
        print("%s: created %d / updated %d / skipped %d / failed %d"
              % (coll, c["created"], c["updated"], c["skipped"], c["failed"]))
    for coll in ["os_deals", "os_activities", "os_proposals", "os_deal_contacts",
                 "os_activity_contacts", "os_proposal_contacts", "os_proposal_approvals"]:
        st, r = request("GET", "/items/%s?limit=0&meta=filter_count" % coll)
        total = r.get("meta", {}).get("filter_count") if st == 200 else "?"
        print("TOTAL %s = %s" % (coll, total))

    if approved_ids:
        print("APPROVED_PROPOSAL_ID=" + approved_ids[0][1])


def verify():
    print("--- VERIFY (admin GraphQL, portal fragment shapes) ---")
    q1 = ('query { os_activities(limit:3, sort:["-date_created"]) { id name activity_type status '
          'due_date start_time end_time activity_notes assigned_to { id first_name last_name } '
          'deal { id name } organization { id name service_status } } }')
    st, r = request("POST", "/graphql", {"query": q1})
    ok1 = st == 200 and not r.get("errors") and r.get("data", {}).get("os_activities")
    print("activities probe: HTTP %s errors=%s rows=%s" % (st, bool(r.get("errors")),
          len(r.get("data", {}).get("os_activities") or [])))
    if r.get("errors"):
        print(json.dumps(r["errors"])[:400])
    else:
        print(json.dumps(r["data"]["os_activities"], indent=1)[:1200])

    q2 = ('query { os_deals(limit:5, sort:["-date_updated"]) { id name deal_value close_date '
          'next_contact_date deal_stage { id name } organization { id name service_status } '
          'owner { id first_name last_name } } }')
    st, r = request("POST", "/graphql", {"query": q2})
    ok2 = st == 200 and not r.get("errors") and r.get("data", {}).get("os_deals")
    print("deals probe: HTTP %s errors=%s rows=%s" % (st, bool(r.get("errors")),
          len(r.get("data", {}).get("os_deals") or [])))
    if r.get("errors"):
        print(json.dumps(r["errors"])[:400])
    else:
        print(json.dumps(r["data"]["os_deals"], indent=1)[:1200])

    q3 = 'query { os_deals(limit:-1) { deal_stage { id } } }'
    st, r = request("POST", "/graphql", {"query": q3})
    seen = set()
    for row in (r.get("data", {}).get("os_deals") or []):
        if row.get("deal_stage"):
            seen.add(row["deal_stage"]["id"])
    ok3 = ALL_STAGE_IDS.issubset(seen)
    print("stage coverage: %d/5 stage ids present -> %s" % (len(ALL_STAGE_IDS & seen),
          "ALL PRESENT" if ok3 else "MISSING " + str(ALL_STAGE_IDS - seen)))

    # REST detail probe on one approved proposal
    st, r = request("GET", "/items/os_proposals?filter[status][_eq]=approved&fields=id,name&limit=1")
    ok4 = False
    if st == 200 and r.get("data"):
        pid = r["data"][0]["id"]
        st2, r2 = request("GET", "/items/os_proposals/%s?fields=*,contacts.contacts_id.first_name,approvals.status" % pid)
        d = r2.get("data", {})
        ok4 = (st2 == 200 and d.get("contacts") and
               any(a.get("status") == "published" for a in d.get("approvals", [])))
        print("approved proposal probe: HTTP %s id=%s contacts=%s approvals=%s"
              % (st2, pid, json.dumps(d.get("contacts"))[:200], json.dumps(d.get("approvals"))[:200]))
    else:
        print("approved proposal probe: no approved proposal found (HTTP %s)" % st)

    # demo-session junction reads (fail-loud lesson)
    st, r = request("POST", "/auth/login", {"email": "demo@muster.dev", "password": "muster-demo"}, token=NO_AUTH)
    demo_token = r.get("data", {}).get("access_token") if st == 200 else None
    ok5 = False
    if demo_token:
        results = {}
        for coll in ["os_activity_contacts", "os_deal_contacts"]:
            st2, r2 = request("GET", "/items/%s?limit=1" % coll, token=demo_token)
            results[coll] = st2
            if st2 == 403:
                print("demo read %s -> 403, adding additive read grant on policy %s" % (coll, DEMO_POLICY))
                request("POST", "/permissions", {"policy": DEMO_POLICY, "collection": coll,
                                                 "action": "read", "fields": ["*"], "permissions": {}})
                st3, _ = request("GET", "/items/%s?limit=1" % coll, token=demo_token)
                results[coll] = st3
        ok5 = all(v == 200 for v in results.values())
        print("demo junction reads: %s" % results)
    else:
        print("demo login failed: HTTP %s" % st)

    print("VERIFY RESULT: activities=%s deals=%s stages=%s proposal=%s demo_reads=%s"
          % (bool(ok1), bool(ok2), ok3, ok4, ok5))


if __name__ == "__main__":
    main()
    if "--no-verify" not in sys.argv:
        verify()
