#!/usr/bin/env python3
"""seed-D3.py: domain-delivery seeding for the Muster demo (cms.musterr.dev).

Seeds: os_tasks (45 synthetic + 6 personal), os_sprints (7), os_sprint_snapshots,
os_deliverables (15), os_deliverable_decisions, os_project_updates (25),
os_project_contacts, os_task_files, directus_comments, repositories (5), releases (12).

Rules honored: add-only, idempotent upserts by natural key, is_test_data:false,
no em dashes, two-phase create-then-PATCH for backdated date_created/user_created,
never touches the Muster build board (project 0ef5827c) or existing rows,
zero new releases on bloom-shopify aba3e9b9 (repo mispointing workaround),
gated null-fills (existing repo descriptions, project budget_cap) SKIPPED unless
NULLFILL_APPROVED=1 is set in the environment (it is not, this run).

Usage: python3 seed-D3.py [--verify]
"""
import json
import os
import sys
import urllib.request
import urllib.parse
import hashlib
from datetime import date, datetime, timedelta

BASE = "https://cms.musterr.dev"
TODAY = date(2026, 7, 16)


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
NULLFILL = os.environ.get("NULLFILL_APPROVED") == "1"


def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def search(col, flt, fields="id,date_created,user_created", limit=3):
    q = urllib.parse.urlencode({"filter": json.dumps(flt), "fields": fields, "limit": str(limit)})
    st, out = req("GET", "/items/" + col + "?" + q)
    if st != 200:
        raise RuntimeError("search %s failed %s %s" % (col, st, out))
    return out["data"]


COUNTS = {}


def tally(col, kind):
    COUNTS.setdefault(col, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
    COUNTS[col][kind] += 1


def ts_match(stored, desired):
    """Compare a stored ISO timestamp against desired 'YYYY-MM-DDTHH:MM:SS' by minute prefix."""
    if not stored or not desired:
        return stored == desired
    return stored[:16] == desired[:16]


def upsert(col, flt, payload, backdate=None):
    """Search by natural key; create if absent; two-phase PATCH backdated
    date_created/user_created after create. If a row we created earlier exists but
    a prior run died between POST and PATCH, repair only the backdated fields.
    Returns (id, created_bool)."""
    fields = "id,date_created,user_created" if backdate else "id"
    rows = search(col, flt, fields=fields)
    if rows:
        row = rows[0]
        if backdate:
            need = {}
            if "date_created" in backdate and not ts_match(row.get("date_created"), backdate["date_created"]):
                need["date_created"] = backdate["date_created"]
            if "user_created" in backdate and row.get("user_created") != backdate["user_created"]:
                need["user_created"] = backdate["user_created"]
            if need:
                st, out = req("PATCH", "/items/%s/%s" % (col, row["id"]), need)
                if st == 200:
                    tally(col, "updated")
                else:
                    tally(col, "failed")
                    print("  PATCH-repair failed %s %s: %s %s" % (col, row["id"], st, out))
                return row["id"], False
        tally(col, "skipped")
        return row["id"], False
    st, out = req("POST", "/items/" + col, payload)
    if st not in (200, 204):
        tally(col, "failed")
        print("  CREATE failed %s: %s %s" % (col, st, str(out)[:300]))
        return None, False
    rid = out["data"]["id"]
    if backdate:
        st2, out2 = req("PATCH", "/items/%s/%s" % (col, rid), backdate)
        if st2 != 200:
            print("  backdate PATCH failed %s %s: %s %s" % (col, rid, st2, out2))
            tally(col, "failed")
            return rid, True
    tally(col, "created")
    return rid, True


# ---------------------------------------------------------------- constants
AISHA = "86f5c9cd-b6fb-4d43-bb5c-2050e66c7f40"
DEVON = "06fb5978-93dd-4a13-b02e-48f7271d7301"
ELENA = "1e7ce5df-3dea-4fd4-bd35-cfd9c32f8852"
FELIX = "78cf2976-e1da-4b8b-b238-822bcbe1b8fb"
MARA = "3f3b7c79-4c79-4865-8592-5a303db8b995"
TOM = "a043509e-00b1-4d4c-b613-fd0d30b878db"
ADMIN = "34d67d59-16c3-41c4-9efb-7fd51a216460"
DEMO = "257a4b75-deff-476d-953d-1898c57f6684"

MUSTER_PROJECT = "0ef5827c-924d-4c2a-a769-d9d7c84097e1"
CEDAR_WEB = "430df3e9-7f6d-4369-81cf-d9e5dc0fab00"      # org 2
CEDAR_WHOLESALE = "a42f4921-7747-4319-b09e-644f639e89c5"  # org 2
NORTH_BRAND = "91528c06-daee-41eb-b614-363afb1eb531"     # org 3
NORTH_SEO = "193e5bd8-e9b2-471e-91e9-7c19aa2a2c7a"       # org 3
VELLUM_PORT = "4ae1d3fa-92fb-443d-86c8-4636df95e41c"     # org 4
VELLUM_MOTION = "b9a8afa7-7138-4b3d-84cc-407e6d28f0dc"   # org 4
HARBOR_APP = "d16e4ef5-a11c-4165-8f5b-2a79fa1a1e51"      # org 5
BLOOM = "3d5677cf-af08-4df2-a29a-6a4925ab9268"           # org 6
STERLING = "cd1eae58-ec99-4444-bbe4-ae6ab9370cea"        # org 7
MERIDIAN = "c6581803-8fe8-43e7-bb56-4f1e758e2a25"        # org 8

PROJECT_ORG = {
    CEDAR_WEB: 2, CEDAR_WHOLESALE: 2, NORTH_BRAND: 3, NORTH_SEO: 3,
    VELLUM_PORT: 4, VELLUM_MOTION: 4, HARBOR_APP: 5, BLOOM: 6,
    STERLING: 7, MERIDIAN: 8,
}

CEDAR_S4 = "2d10cdef-0a40-49a1-9d90-74ca99cc3f09"
NORTH_S2 = "6d92f9da-1fb2-49a6-88b9-8020dcbead67"
HARBOR_S3 = "374819a3-668b-4286-899b-fdbde7d3e95d"

PHOTOS = [
    "0de6e142-c5d7-4ba4-a686-c66c91db9b30", "f82fed74-f2fd-4ae4-8e76-3ba3caa7fbff",
    "4ccc0388-111d-4a8a-96c8-ffc29674a41d", "7cc4963e-cdb9-4a26-b01e-4e6c966b51b6",
    "60f8488b-430d-487b-9361-aca3d0534881", "cf9847ee-6281-403a-b2e7-bf46684df53d",
    "ac56b9e1-1a41-4fad-8bc5-47f718bddc74", "24132b54-79cd-43d4-aaf8-e553dcf4465b",
    "b3bb2e16-8824-4049-b667-10da41a17312", "837c3ebf-44e3-42d7-afff-da031cb60b8c",
    "c2720258-817a-4f72-b214-21e075b3534f", "2cf34128-3566-41b6-acd3-a7e0e0d5149c",
    "65805960-25e2-4e94-8370-991a0d78fb19", "6a7f74fb-3d58-4f66-b213-94d340a8af6d",
    "83e09c92-42f9-43a1-a948-b6fac7083a86",
]
MOOD1 = "573b7d86-4931-4f8d-be00-c728d24c233b"
SITE1 = "454ed00f-3624-4499-afc5-cfb0a072ffd7"

# ---------------------------------------------------------------- sprints
NEW_SPRINTS = [
    dict(name="Cedar Sprint 3", project=CEDAR_WEB, status="completed",
         start_date="2026-06-01", end_date="2026-06-14", capacity_points=21, rank=1,
         goal="Ship the new menu and locations experience",
         review_notes="All menu and locations work shipped on schedule. Order tracking spiked but implementation slipped to Sprint 4.",
         retro_notes="Went well: clean design handoff and early CDN migration. Improve: lock client content earlier in the sprint."),
    dict(name="Harbor App S2", project=HARBOR_APP, status="completed",
         start_date="2026-05-11", end_date="2026-05-24", capacity_points=34, rank=1,
         goal="Member accounts and class schedule foundation",
         review_notes="Accounts, schedule API, and trainer profiles all landed. Push service is stood up and ready for S3 booking flows.",
         retro_notes="Went well: API contract agreed up front kept mobile unblocked. Improve: QA started too late in week two."),
    dict(name="Northlight Brand S1", project=NORTH_BRAND, status="completed",
         start_date="2026-04-06", end_date="2026-04-19", capacity_points=13, rank=1,
         goal="Discovery and logo concept directions",
         review_notes="Three concept directions presented. Client selected the serif wordmark direction with minor color reservations.",
         retro_notes="Went well: discovery workshop produced clear positioning. Improve: schedule the concept review earlier to leave revision room."),
    dict(name="Sterling Reservations S1", project=STERLING, status="completed",
         start_date="2026-03-02", end_date="2026-03-15", capacity_points=21, rank=1,
         goal="Reservation data model and availability engine",
         review_notes="Availability engine prototype validated against three months of booking data. Waitlist edge cases carried over.",
         retro_notes="Went well: load tests caught an indexing gap early. Improve: involve the restaurant floor manager sooner for seating rules."),
    dict(name="Vellum Platform S1", project=VELLUM_PORT, status="completed",
         start_date="2026-02-09", end_date="2026-02-22", capacity_points=21, rank=1,
         goal="Case study CMS and gallery grid",
         review_notes="Content model, gallery grid, and first case study template shipped. Analytics baseline is recording.",
         retro_notes="Went well: image pipeline reuse from earlier work saved days. Improve: wireframe review cycle had too many async gaps."),
    dict(name="Cedar Sprint 5", project=CEDAR_WEB, status="planned",
         start_date="2026-07-21", end_date="2026-08-03", capacity_points=21, rank=2,
         goal="Loyalty program and gift cards"),
    dict(name="Sterling Reservations S2", project=STERLING, status="active",
         start_date="2026-07-06", end_date="2026-07-19", capacity_points=21, rank=2,
         goal="Guest booking flow and v1.0 launch prep"),
]

# ---------------------------------------------------------------- tasks
# sprint refs by name for new sprints, by id for existing ones
T = []


def task(name, project, sprint, status, prio, pts, assigned, due, created,
         completed=None, ttype="task", cv=True, resp="team", rank=None,
         flagship=False, parent=None):
    T.append(dict(name=name, project=project, sprint=sprint, status=status,
                  priority=prio, points=pts, assigned=assigned, due=due,
                  created=created, completed=completed, ttype=ttype, cv=cv,
                  resp=resp, rank=rank, flagship=flagship, parent=parent))


# Cedar Sprint 3 (completed 2026-06-01..06-14) date_created 1-5 days before start
task("Build the locations map page", CEDAR_WEB, "Cedar Sprint 3", "completed", "P1", 5, AISHA,
     "2026-06-10T17:00:00", "2026-05-31T09:00:00", completed="2026-06-09T15:30:00")
task("Redesign the menu detail template", CEDAR_WEB, "Cedar Sprint 3", "completed", "P1", 5, DEVON,
     "2026-06-12T17:00:00", "2026-05-29T10:00:00", completed="2026-06-11T14:00:00", flagship=True)
task("Migrate product photography to CDN", CEDAR_WEB, "Cedar Sprint 3", "completed", "P2", 3, ELENA,
     "2026-06-08T17:00:00", "2026-05-28T11:00:00", completed="2026-06-05T16:45:00", cv=False)
task("Set up menu content model", CEDAR_WEB, "Cedar Sprint 3", "completed", "P2", 3, FELIX,
     "2026-06-06T17:00:00", "2026-05-27T09:30:00", completed="2026-06-04T12:00:00", cv=False)
task("Write launch announcement copy", CEDAR_WEB, "Cedar Sprint 3", "completed", "P3", 2, MARA,
     "2026-06-13T17:00:00", "2026-05-30T14:00:00", completed="2026-06-12T10:15:00", resp="both")
task("Order tracking spike", CEDAR_WEB, "Cedar Sprint 3", "in_review", "P2", 3, TOM,
     "2026-06-14T17:00:00", "2026-05-31T15:00:00", cv=False)

# Harbor App S2 (completed 2026-05-11..05-24)
task("Build member account screens", HARBOR_APP, "Harbor App S2", "completed", "P1", 8, DEVON,
     "2026-05-20T17:00:00", "2026-05-08T09:00:00", completed="2026-05-19T16:00:00", flagship=True)
task("Implement class schedule API", HARBOR_APP, "Harbor App S2", "completed", "P1", 8, TOM,
     "2026-05-18T17:00:00", "2026-05-07T10:00:00", completed="2026-05-16T13:30:00", cv=False)
task("Design trainer profile cards", HARBOR_APP, "Harbor App S2", "completed", "P2", 5, ELENA,
     "2026-05-15T17:00:00", "2026-05-06T11:00:00", completed="2026-05-14T15:00:00")
task("Set up push notification service", HARBOR_APP, "Harbor App S2", "completed", "P2", 5, AISHA,
     "2026-05-22T17:00:00", "2026-05-09T09:30:00", completed="2026-05-21T11:45:00", cv=False)
task("Class schedule QA pass", HARBOR_APP, "Harbor App S2", "completed", "P2", 3, MARA,
     "2026-05-24T17:00:00", "2026-05-10T14:00:00", completed="2026-05-23T17:20:00", cv=False)

# Northlight Brand S1 (completed 2026-04-06..04-19)
task("Run brand discovery workshop", NORTH_BRAND, "Northlight Brand S1", "completed", "P1", 3, ADMIN,
     "2026-04-08T17:00:00", "2026-04-03T09:00:00", completed="2026-04-07T16:00:00", resp="both")
task("Develop three logo concept directions", NORTH_BRAND, "Northlight Brand S1", "completed", "P0", 5, ELENA,
     "2026-04-15T17:00:00", "2026-04-01T10:00:00", completed="2026-04-14T15:30:00", flagship=True)
task("Competitive brand audit", NORTH_BRAND, "Northlight Brand S1", "completed", "P2", 2, MARA,
     "2026-04-10T17:00:00", "2026-04-02T11:00:00", completed="2026-04-09T12:00:00", cv=False)
task("Client concept review session", NORTH_BRAND, "Northlight Brand S1", "completed", "P1", 1, ADMIN,
     "2026-04-17T17:00:00", "2026-04-04T09:30:00", completed="2026-04-17T15:00:00",
     ttype="milestone", resp="both")
task("Compile discovery findings deck", NORTH_BRAND, "Northlight Brand S1", "completed", "P2", 2, FELIX,
     "2026-04-12T17:00:00", "2026-04-05T14:00:00", completed="2026-04-11T10:30:00", ttype="deliverable")

# Sterling Reservations S1 (completed 2026-03-02..03-15)
task("Design reservation data model", STERLING, "Sterling Reservations S1", "completed", "P1", 5, TOM,
     "2026-03-06T17:00:00", "2026-02-27T09:00:00", completed="2026-03-05T14:00:00", cv=False, flagship=True)
task("Build availability engine prototype", STERLING, "Sterling Reservations S1", "completed", "P0", 8, DEVON,
     "2026-03-12T17:00:00", "2026-02-25T10:00:00", completed="2026-03-11T16:30:00", cv=False)
task("Table inventory admin screen", STERLING, "Sterling Reservations S1", "completed", "P2", 3, AISHA,
     "2026-03-10T17:00:00", "2026-02-26T11:00:00", completed="2026-03-09T13:00:00", cv=False)
task("Reservation confirmation emails", STERLING, "Sterling Reservations S1", "completed", "P2", 2, MARA,
     "2026-03-13T17:00:00", "2026-02-28T09:30:00", completed="2026-03-13T11:00:00", resp="both")
task("Load test availability queries", STERLING, "Sterling Reservations S1", "completed", "P2", 2, TOM,
     "2026-03-14T17:00:00", "2026-03-01T14:00:00", completed="2026-03-14T15:45:00", cv=False,
     parent="Build availability engine prototype")
task("Waitlist edge case review", STERLING, "Sterling Reservations S1", "pending", "P3", 1, FELIX,
     "2026-03-15T17:00:00", "2026-03-01T15:00:00", cv=False)

# Vellum Platform S1 (completed 2026-02-09..02-22)
task("Model case study content types", VELLUM_PORT, "Vellum Platform S1", "completed", "P1", 5, FELIX,
     "2026-02-13T17:00:00", "2026-02-06T09:00:00", completed="2026-02-12T15:00:00", flagship=True)
task("Build gallery grid component", VELLUM_PORT, "Vellum Platform S1", "completed", "P1", 5, AISHA,
     "2026-02-17T17:00:00", "2026-02-04T10:00:00", completed="2026-02-16T14:30:00")
task("Image optimization pipeline", VELLUM_PORT, "Vellum Platform S1", "completed", "P2", 3, DEVON,
     "2026-02-15T17:00:00", "2026-02-05T11:00:00", completed="2026-02-14T12:00:00", cv=False,
     parent="Build gallery grid component")
task("Case study template first pass", VELLUM_PORT, "Vellum Platform S1", "completed", "P2", 5, ELENA,
     "2026-02-20T17:00:00", "2026-02-07T09:30:00", completed="2026-02-19T16:00:00")
task("Portfolio home wireframes", VELLUM_PORT, "Vellum Platform S1", "completed", "P2", 2, ELENA,
     "2026-02-11T17:00:00", "2026-02-08T14:00:00", completed="2026-02-10T11:30:00", ttype="deliverable")
task("Analytics baseline setup", VELLUM_PORT, "Vellum Platform S1", "completed", "P3", 1, TOM,
     "2026-02-21T17:00:00", "2026-02-08T15:00:00", completed="2026-02-21T10:00:00", cv=False)

# Cedar Sprint 4 (ACTIVE, 07-07..07-20): 2 before start, 1 scope-added after
task("Build order tracking page", CEDAR_WEB, CEDAR_S4, "in_progress", "P1", 5, DEVON,
     "2026-07-17T17:00:00", "2026-07-03T09:00:00", flagship=True)
task("Order tracking mobile QA pass", CEDAR_WEB, CEDAR_S4, "in_review", "P2", 2, MARA,
     "2026-07-15T17:00:00", "2026-07-04T10:00:00", parent="Build order tracking page")
task("Add gift card redemption", CEDAR_WEB, CEDAR_S4, "active", "P2", 1, AISHA,
     "2026-07-19T17:00:00", "2026-07-10T11:30:00")  # scope-added

# Northlight Brand S2 (ACTIVE, 07-09..07-22): 2 before, 1 scope-added
task("Refine logo lockup variants", NORTH_BRAND, NORTH_S2, "in_progress", "P1", 2, ELENA,
     "2026-07-18T17:00:00", "2026-07-06T09:00:00")
task("Assemble brand guidelines PDF", NORTH_BRAND, NORTH_S2, "active", "P1", 3, FELIX,
     "2026-07-21T17:00:00", "2026-07-07T10:00:00", ttype="deliverable")
task("Present stationery mockups", NORTH_BRAND, NORTH_S2, "in_review", "P2", 1, ELENA,
     "2026-07-14T17:00:00", "2026-07-11T14:00:00", resp="both")  # scope-added

# Harbor App S3 (ACTIVE, 07-05..07-18): 1 before, 1 scope-added
task("Build class waitlist flow", HARBOR_APP, HARBOR_S3, "in_progress", "P1", 8, TOM,
     "2026-07-17T17:00:00", "2026-07-01T09:00:00", flagship=True)
task("Push notification opt-in screen", HARBOR_APP, HARBOR_S3, "active", "P2", 5, AISHA,
     "2026-07-15T17:00:00", "2026-07-08T10:30:00")  # scope-added

# Sterling Reservations S2 (NEW ACTIVE, 07-06..07-19): 4 before, 1 scope-added
task("Guest booking flow polish", STERLING, "Sterling Reservations S2", "in_progress", "P1", 5, DEVON,
     "2026-07-16T17:00:00", "2026-07-02T09:00:00", flagship=True)
task("Reservations v1.0 launch checklist", STERLING, "Sterling Reservations S2", "active", "P0", 3, ADMIN,
     "2026-07-18T17:00:00", "2026-07-03T10:00:00", ttype="milestone", resp="both")
task("SMS reminder integration", STERLING, "Sterling Reservations S2", "in_review", "P1", 5, MARA,
     "2026-07-14T17:00:00", "2026-07-04T11:00:00", cv=False)
task("Host dashboard seating view", STERLING, "Sterling Reservations S2", "pending", "P2", 5, AISHA,
     "2026-07-19T17:00:00", "2026-07-05T09:30:00", cv=False)
task("Cancellation policy copy", STERLING, "Sterling Reservations S2", "completed", "P3", 3, MARA,
     "2026-07-10T17:00:00", "2026-07-07T14:00:00", completed="2026-07-09T15:00:00",
     resp="client")  # scope-added

# Cedar Sprint 5 (PLANNED, starts 07-21)
task("Loyalty program discovery", CEDAR_WEB, "Cedar Sprint 5", "pending", "P2", 3, FELIX,
     "2026-07-28T17:00:00", "2026-07-12T09:00:00")

# Backlog, no sprint (date_created spread over last 10 weeks, fractional ranks)
task("Grant application intake form", MERIDIAN, None, "in_progress", "P1", 8, DEVON,
     "2026-07-24T17:00:00", "2026-06-02T09:00:00", rank="a0", flagship=True)
task("Motion reel storyboard", VELLUM_MOTION, None, "pending", "P2", 5, ELENA,
     "2026-08-05T17:00:00", "2026-06-20T10:00:00", rank="a1", flagship=True)
task("Wholesale pricing tier matrix", CEDAR_WHOLESALE, None, "pending", "P2", 3, DEMO,
     "2026-07-22T17:00:00", "2026-07-01T11:00:00", rank="a2", resp="both")

assert len(T) == 45, "expected 45 synthetic tasks, got %d" % len(T)

# Personal workspace tasks (REV 2 mitigation: professional names, ranks at end)
PERSONAL = [
    dict(name="Prep Cedar retro notes", status="in_progress", due="2026-07-14T17:00:00",
         rank="z0", created="2026-07-08T09:00:00"),  # overdue
    dict(name="Review Harbor sprint burndown", status="pending", due="2026-07-16T17:00:00",
         rank="z1", created="2026-07-10T09:30:00"),  # today
    dict(name="Draft Northlight kickoff agenda", status="in_progress", due="2026-07-16T17:00:00",
         rank="z2", created="2026-07-11T10:00:00"),  # today
    dict(name="Update weekly status doc", status="pending", due="2026-07-17T17:00:00",
         rank="z3", created="2026-07-13T09:00:00"),
    dict(name="Plan Q3 capacity review", status="pending", due="2026-07-20T17:00:00",
         rank="z4", created="2026-07-14T11:00:00"),
    dict(name="Organize demo screenshot library", status="pending", due="2026-07-24T17:00:00",
         rank="z5", created="2026-07-15T09:00:00"),
]

FLAGSHIP_DETAIL = {
    "Redesign the menu detail template": (
        "Rebuild the menu detail template on the new design system. Each drink and blend page "
        "gets structured tasting notes, origin details, and a related-items rail sourced from "
        "the menu content model.",
        "- Template renders all menu item types without layout breaks\n"
        "- Tasting notes and origin block populated from CMS fields\n"
        "- Lighthouse performance stays above 90 on mobile\n"
        "- Related items rail shows 3 to 6 entries"),
    "Build member account screens": (
        "Design and build the member account area: profile, membership status, visit history, "
        "and payment method management. Uses the shared design tokens from the Harbor style guide.",
        "- Members can update profile and contact preferences\n"
        "- Visit history paginates past 50 entries\n"
        "- Payment method update flows pass QA on iOS and Android\n"
        "- All screens meet WCAG 2.1 AA"),
    "Develop three logo concept directions": (
        "Produce three distinct logo concept directions for Northlight Law: a serif wordmark, "
        "a monogram mark, and a lighthouse-derived symbol. Each direction includes primary "
        "lockup, reversed version, and small-size test.",
        "- Three directions presented as a single deck\n"
        "- Each direction shown in 1-color, reversed, and favicon sizes\n"
        "- Rationale paragraph per direction\n"
        "- Client review session scheduled before sprint end"),
    "Design reservation data model": (
        "Define the core reservation schema: tables, seatings, service periods, holds, and "
        "cancellation states. The model must support split seatings and private dining rooms.",
        "- ER diagram reviewed by engineering\n"
        "- Handles double seatings and buyouts\n"
        "- Migration scripts reviewed and merged\n"
        "- No breaking changes to the booking widget contract"),
    "Model case study content types": (
        "Model the case study content types for the Vellum portfolio platform: project, "
        "credit roles, media blocks, and pull quotes. Editors compose case studies from "
        "reusable blocks rather than fixed layouts.",
        "- Content types cover all 12 existing case studies\n"
        "- Block ordering is drag-and-drop in the CMS\n"
        "- Media blocks accept video and image galleries\n"
        "- Preview renders within 2 seconds"),
    "Build order tracking page": (
        "Build the customer-facing order tracking page for Cedar & Co online orders. Pulls "
        "fulfillment states from the commerce backend and shows a step timeline with "
        "estimated ready times.",
        "- Timeline reflects all five fulfillment states\n"
        "- Page updates without a manual refresh\n"
        "- Works from the order confirmation email link\n"
        "- Mobile layout passes QA"),
    "Build class waitlist flow": (
        "Add a waitlist flow to class booking: members join a waitlist on full classes, get "
        "push notified when a spot opens, and have a 15 minute claim window before the spot "
        "rolls to the next member.",
        "- Waitlist position visible to the member\n"
        "- Push notification fires within 30 seconds of an opening\n"
        "- Claim window expiry rolls to next in line\n"
        "- No double-booking under concurrent claims"),
    "Guest booking flow polish": (
        "Final polish pass on the Sterling guest booking flow before v1.0: inline validation, "
        "party size edge cases, and the confirmation screen with calendar links.",
        "- Validation errors resolve inline without page reloads\n"
        "- Party sizes 1 through 12 handled, larger routed to private dining\n"
        "- Confirmation screen offers Apple and Google calendar links\n"
        "- Flow completes in under 60 seconds in usability tests"),
    "Grant application intake form": (
        "Build the multi-step grant application intake form for Meridian Fund: applicant "
        "profile, project narrative, budget upload, and declaration. Supports save-and-resume "
        "for applicants.",
        "- Four steps with progress indicator\n"
        "- Save-and-resume works across sessions\n"
        "- Budget upload accepts PDF and XLSX up to 20 MB\n"
        "- Submissions land in the review queue with status pending"),
    "Motion reel storyboard": (
        "Storyboard the 60 second Vellum motion reel: shot list, timing map, and music "
        "direction. The reel pulls from the best case study footage of the last two years.",
        "- Shot list covers 12 to 16 scenes\n"
        "- Timing map fits 60 seconds at 24 fps\n"
        "- Two music directions proposed\n"
        "- Client sign-off recorded before production starts"),
}

FLAGSHIP_COMMENTS = {
    "Redesign the menu detail template": [
        "First pass is on staging, tasting notes block still needs the origin map.",
        "Origin map is in. Ready for content review against the new menu model.",
        "Reviewed with Cedar marketing, they love the related-items rail."],
    "Build member account screens": [
        "Profile and visit history screens are done, payment methods next.",
        "Stripe test cards passing on both platforms, moving to accessibility pass.",
        "AA audit clean. Shipping with the S2 release."],
    "Develop three logo concept directions": [
        "Serif wordmark and monogram directions are drafted, symbol direction in progress.",
        "All three directions in the deck, small-size tests hold up well.",
        "Client leaned serif wordmark in the review, minor color reservations noted."],
    "Design reservation data model": [
        "Split seatings forced a seating-instance table, diagram updated.",
        "Engineering review done, two index changes requested and applied."],
    "Model case study content types": [
        "Block library covers 11 of 12 case studies, the film project needs a video-first block.",
        "Video-first block added, all 12 map cleanly now."],
    "Build order tracking page": [
        "Blocked briefly on the courier API sandbox, key arrived this morning.",
        "Timeline component wired to live fulfillment states on staging.",
        "QA found a polling gap after 10 minutes idle, fix in review."],
    "Build class waitlist flow": [
        "Waitlist join and position display are working end to end.",
        "Claim window expiry logic done, load testing the concurrent claim path now."],
    "Guest booking flow polish": [
        "Inline validation is in, party size 12 plus now routes to private dining.",
        "Calendar links verified on iOS and Android, usability run scheduled Friday."],
    "Grant application intake form": [
        "Steps 1 and 2 built, save-and-resume token flow working.",
        "Budget upload validation done, 20 MB limit enforced with a clear error.",
        "Declaration step and review queue handoff remain."],
    "Motion reel storyboard": [
        "Pulled candidate footage from six case studies, shot list at 14 scenes.",
        "Timing map drafted, both music directions attached for review."],
}

# ---------------------------------------------------------------- deliverables
DELIVERABLES = [
    # (project, name, status, file, url, description, sort, base_date, submitter)
    (CEDAR_WEB, "Homepage design comps", "approved", MOOD1, None,
     "Final homepage comps for the Cedar & Co redesign, desktop and mobile.", 1, "2026-06-03", ELENA),
    (CEDAR_WEB, "Menu photography set", "pending_review", SITE1, None,
     "Retouched photography set for the new menu detail pages.", 2, "2026-07-10", MARA),
    (CEDAR_WHOLESALE, "Wholesale portal wireframes", "approved", None,
     "https://www.figma.com/file/demo-cedar-wholesale/wireframes",
     "Annotated wireframes for the B2B wholesale ordering portal.", 1, "2026-06-18", FELIX),
    (NORTH_BRAND, "Logo concept directions", "approved", PHOTOS[0], None,
     "Three logo concept directions with rationale and small-size tests.", 1, "2026-04-15", ELENA),
    (NORTH_BRAND, "Brand guidelines draft", "revision_requested", None,
     "https://www.figma.com/file/demo-northlight-brand/guidelines",
     "Draft brand guidelines covering logo use, color, and typography.", 2, "2026-07-08", FELIX),
    (NORTH_BRAND, "Stationery mockups", "pending_review", PHOTOS[1], None,
     "Letterhead, business card, and envelope mockups in the selected direction.", 3, "2026-07-06", ELENA),
    (NORTH_SEO, "Q3 content calendar", "approved", None,
     "https://docs.google.com/spreadsheets/d/demo-northlight-seo-q3",
     "Approved content calendar for Q3 with target keywords per piece.", 1, "2026-06-25", MARA),
    (NORTH_SEO, "Technical SEO audit report", "pending_review", None,
     "https://docs.google.com/document/d/demo-northlight-tech-audit",
     "Full technical audit: crawl budget, schema coverage, and Core Web Vitals.", 2, "2026-07-12", TOM),
    (VELLUM_PORT, "Case study template designs", "approved", PHOTOS[2], None,
     "High fidelity case study template designs across three layout variants.", 1, "2026-02-19", ELENA),
    (VELLUM_PORT, "Gallery grid prototype", "revision_requested", None,
     "https://vellum-portfolio-demo.netlify.app/gallery",
     "Interactive gallery grid prototype with hover reels.", 2, "2026-07-02", AISHA),
    (HARBOR_APP, "Booking flow prototype", "approved", None,
     "https://www.figma.com/proto/demo-harbor-booking",
     "Clickable prototype of the class booking and waitlist flow.", 1, "2026-06-28", DEVON),
    (HARBOR_APP, "App icon and splash screens", "revision_requested", PHOTOS[3], None,
     "App icon set and splash screens for iOS and Android.", 2, "2026-07-09", ELENA),
    (STERLING, "Reservation widget embed demo", "pending_review", None,
     "https://sterling-reservations-demo.netlify.app/embed",
     "Embeddable reservation widget demo for the Sterling website.", 1, "2026-07-05", DEVON),
    (STERLING, "Email template designs", "revision_requested", PHOTOS[4], None,
     "Confirmation, reminder, and cancellation email template designs.", 2, "2026-07-11", MARA),
    (MERIDIAN, "Grant portal wireframe pack", "pending_review", PHOTOS[5], None,
     "Wireframe pack for the applicant intake and reviewer scoring screens.", 1, "2026-07-13", FELIX),
]

# resubmitted-trail deliverables (pending_review with a longer history)
RESUBMITTED = {"Stationery mockups", "Reservation widget embed demo"}

# ---------------------------------------------------------------- project updates
UPDATES = [
    # (project, message, cv, created, author)
    (CEDAR_WEB, "## Sprint 3 wrap\nMenu and locations experience shipped on schedule. Order tracking moved to Sprint 4 with design already approved.", True, "2026-06-15T10:00:00", ADMIN),
    (CEDAR_WEB, "Order tracking page is on staging and wired to live fulfillment states. QA pass runs this week.", True, "2026-07-10T09:30:00", DEVON),
    (CEDAR_WEB, "Gift card redemption was pulled into Sprint 4 at Cedar's request. Capacity still fits with the QA slot we reserved.", False, "2026-07-11T14:00:00", ADMIN),
    (CEDAR_WEB, "Photography CDN migration cut page weight on menu pages by 38 percent. Mobile LCP is now under 2 seconds.", True, "2026-06-06T11:00:00", ELENA),
    (CEDAR_WHOLESALE, "Wholesale portal wireframes approved by Cedar's ops team. Build starts after the website Sprint 5.", True, "2026-06-20T10:00:00", FELIX),
    (CEDAR_WHOLESALE, "Pricing tier matrix drafted with three volume bands. Waiting on Cedar finance for margin sign-off.", True, "2026-07-08T15:00:00", ADMIN),
    (CEDAR_WHOLESALE, "Repository scaffolded and CI configured. First build milestone targets late July.", False, "2026-06-24T09:00:00", TOM),
    (NORTH_BRAND, "## Concept review outcome\nNorthlight selected the serif wordmark direction. Color palette revisions land in the guidelines draft next week.", True, "2026-04-20T10:00:00", ADMIN),
    (NORTH_BRAND, "Brand guidelines draft is with the client. Stationery mockups resubmitted after the paper stock change.", True, "2026-07-09T11:30:00", FELIX),
    (NORTH_BRAND, "Logo lockup refinements in progress: tightened letterspacing and a new compact lockup for social avatars.", True, "2026-07-13T09:00:00", ELENA),
    (NORTH_SEO, "Q3 content calendar approved. Eight briefs queued, first two drafts due end of July.", True, "2026-06-26T10:00:00", MARA),
    (NORTH_SEO, "Technical audit complete: schema coverage gaps on practice pages and one crawl trap in the news archive. Report is in review.", True, "2026-07-12T16:00:00", TOM),
    (NORTH_SEO, "Organic clicks up 22 percent quarter over quarter on the practice area pages tracked in the retainer.", True, "2026-07-01T09:00:00", MARA),
    (VELLUM_PORT, "Case study CMS is live for editors. All 12 legacy case studies migrated and rendering on the new templates.", True, "2026-03-02T10:00:00", FELIX),
    (VELLUM_PORT, "Gallery grid prototype feedback received: Vellum wants slower hover reels and larger type in captions. Revision underway.", True, "2026-07-03T14:00:00", AISHA),
    (VELLUM_PORT, "Rate limiter and API hardening queued behind the onboarding fix currently in review.", False, "2026-07-14T09:30:00", TOM),
    (HARBOR_APP, "## S2 review\nMember accounts and the class schedule foundation shipped. Push service is live in test.", True, "2026-05-25T10:00:00", ADMIN),
    (HARBOR_APP, "Waitlist flow is working end to end in staging. Load testing the concurrent claim path before release.", True, "2026-07-13T11:00:00", TOM),
    (HARBOR_APP, "v2.2.0 shipped with class booking improvements. v2.3.0 with waitlist and push opt-in is staged for next week.", True, "2026-07-12T15:30:00", AISHA),
    (STERLING, "Availability engine validated against three months of historical bookings with zero conflicts.", True, "2026-03-16T10:00:00", DEVON),
    (STERLING, "Reservations v1.0 launch checklist is underway. SMS reminders in review, seating view starts this week.", True, "2026-07-13T10:00:00", ADMIN),
    (STERLING, "v1.0.1 hotfix shipped for the double-submit on slow connections. Monitoring shows the error rate at zero since.", True, "2026-07-09T09:00:00", MARA),
    (MERIDIAN, "Intake sprint underway: applicant form steps 1 and 2 are built with save-and-resume working.", True, "2026-07-07T10:00:00", DEVON),
    (MERIDIAN, "Grant portal wireframe pack delivered for review, covering intake and reviewer scoring screens.", True, "2026-07-13T14:00:00", FELIX),
    (MERIDIAN, "Reviewer scoring rubric discussion scheduled with the Meridian program team for next Tuesday.", False, "2026-07-15T09:00:00", ADMIN),
]

# ---------------------------------------------------------------- project contacts
PROJECT_CONTACTS = [
    (CEDAR_WEB, 7), (CEDAR_WEB, 12),
    (CEDAR_WHOLESALE, 7), (CEDAR_WHOLESALE, 13),
    (NORTH_BRAND, 8), (NORTH_BRAND, 14),
    (NORTH_SEO, 8), (NORTH_SEO, 15),
    (VELLUM_PORT, 4), (VELLUM_PORT, 16),
    (VELLUM_MOTION, 17),
    (HARBOR_APP, 5), (HARBOR_APP, 18),
    (BLOOM, 6), (BLOOM, 20),
    (STERLING, 9), (STERLING, 22),
    (MERIDIAN, 10), (MERIDIAN, 25),
]

# ---------------------------------------------------------------- repositories
NEW_REPOS = [
    dict(name="vellum-portfolio", platform="gitlab", project_id=VELLUM_PORT,
         url="https://gitlab.com/analogelk/vellum-portfolio", default_branch="main",
         status="active", is_private=True,
         description="Portfolio platform for Vellum Studio with case study CMS, gallery pipeline, and preview builds."),
    dict(name="cedar-wholesale", platform="github", project_id=CEDAR_WHOLESALE,
         url="https://github.com/analogelk/cedar-wholesale", default_branch="main",
         status="active", is_private=True,
         description="B2B wholesale ordering portal for Cedar & Co Coffee: tiered pricing, standing orders, and invoicing hooks."),
    dict(name="northlight-seo", platform="github", project_id=NORTH_SEO,
         url="https://github.com/analogelk/northlight-seo", default_branch="main",
         status="active", is_private=True,
         description="Content tooling and technical SEO automation for the Northlight Law retainer."),
    dict(name="meridian-grant-portal", platform="bitbucket", project_id=MERIDIAN,
         url="https://bitbucket.org/analogelk/meridian-grant-portal", default_branch="main",
         status="active", is_private=True,
         description="Grant application intake and reviewer scoring portal for Meridian Fund."),
    dict(name="bloom-archive", platform="github", project_id=BLOOM,
         url="https://github.com/analogelk/bloom-archive", default_branch="main",
         status="archived", is_private=False,
         description="Archived history of the Bloom Botanicals Shopify storefront build, retained for reference."),
]

# ---------------------------------------------------------------- releases
def chash(repo, version):
    return hashlib.sha1(("muster-demo:%s:%s" % (repo, version)).encode()).hexdigest()


NEW_RELEASES = [
    # (repo_name, version, title, rtype, status, date, summary, added, changed, fixed, client_notes)
    ("cedar-web", "v1.5.0", "Order tracking", "minor", "published", "2026-07-03",
     "Customer order tracking page with a live fulfillment timeline.",
     ["Order tracking page with five-state fulfillment timeline", "Ready-time estimates on confirmation"],
     ["Menu detail template moved to the new design system"],
     ["Locations map pin drift on Safari"], None),
    ("harbor-app", "v2.2.0", "Member accounts", "minor", "published", "2026-06-26",
     "Member account area with profiles, visit history, and payment methods.",
     ["Member profile and preferences screens", "Visit history with pagination", "Payment method management"],
     ["Class schedule API v2 with service period support"],
     ["Trainer card avatar cropping on Android"], None),
    ("harbor-app", "v2.3.0", "Waitlist and push opt-in", "minor", "shared", "2026-07-12",
     "Class waitlist with push notifications and a 15 minute claim window.",
     ["Waitlist join and position display", "Push notification opt-in screen"],
     ["Booking flow copy tightened after usability testing"],
     ["Double-booking race under concurrent claims"],
     "Waitlist goes live for members next week. Push notifications require members to opt in on first launch."),
    ("sterling-reservations", "v1.0.0", "Reservations launch", "major", "published", "2026-07-01",
     "First production release of the Sterling & Vine reservation system.",
     ["Guest booking flow", "Availability engine", "Table inventory admin", "Confirmation emails"],
     ["Reservation data model finalized for split seatings"],
     ["Timezone handling for holiday service periods"], None),
    ("sterling-reservations", "v1.0.1", "Booking double-submit hotfix", "hotfix", "published", "2026-07-08",
     "Hotfix for duplicate reservations created by double-submit on slow connections.",
     [],
     ["Submit button disabled during in-flight booking requests"],
     ["Duplicate reservations on slow connections", "Confirmation email sent twice for retried bookings"], None),
    ("northlight-brand", "v1.2.0", "Guidelines and stationery", "minor", "shared", "2026-07-10",
     "Brand guidelines draft and stationery assets in the selected direction.",
     ["Brand guidelines PDF draft", "Stationery print files"],
     ["Logo lockup letterspacing refined", "Compact lockup added for social avatars"],
     [],
     "The guidelines draft is ready for your review. Stationery files reflect the updated paper stock."),
    ("vellum-portfolio", "v0.1.0", "Platform foundation", "minor", "published", "2026-05-15",
     "Foundation release: case study CMS, gallery grid, and image pipeline.",
     ["Case study content types with reusable blocks", "Gallery grid component", "Image optimization pipeline"],
     [], ["Case study preview rendering slowdown over 30 images"], None),
    ("vellum-portfolio", "v0.2.0", "Editor experience", "minor", "draft", "2026-07-14",
     "Editor experience improvements ahead of the public portfolio launch.",
     ["Drag-and-drop block ordering", "Pull quote block"],
     ["Gallery hover reels slowed per client feedback", "Caption type scale increased"],
     ["Onboarding redirect loop for invited editors"], None),
    ("cedar-wholesale", "v0.1.0", "Portal scaffold", "minor", "published", "2026-06-20",
     "Initial scaffold of the wholesale ordering portal with CI and preview deploys.",
     ["Project scaffold with CI pipeline", "Auth skeleton against the Cedar account system"],
     [], [], None),
    ("northlight-seo", "v1.0.0", "Retainer tooling", "major", "shared", "2026-04-17",
     "First release of the SEO retainer tooling: audits, briefs, and rank tracking.",
     ["Automated technical audit runner", "Content brief generator", "Rank tracking snapshots"],
     [], [],
     "This tooling powers the monthly retainer reports you receive. No action needed on your side."),
    ("meridian-grant-portal", "v0.1.0", "Intake foundation", "minor", "draft", "2026-07-15",
     "Foundation for the grant intake portal: applicant form and save-and-resume.",
     ["Applicant intake form steps 1 and 2", "Save-and-resume sessions"],
     [], [], None),
    ("bloom-archive", "v1.1.0", "Bloom storefront maintenance wrap", "patch", "published", "2026-02-20",
     "Final maintenance release of the Bloom Botanicals storefront before archive.",
     [],
     ["Seasonal collection templates archived", "Theme settings documented for handoff"],
     ["Checkout banner overlap on tablet breakpoints", "Newsletter signup double opt-in loop"], None),
]

# sprint snapshot shaping: name/id -> (total, target_remaining_at_end_or_today)
SNAPSHOT_SHAPE = {
    "Cedar Sprint 3": (21, 3),
    "Harbor App S2": (29, 0),
    "Northlight Brand S1": (13, 0),
    "Sterling Reservations S1": (21, 1),
    "Vellum Platform S1": (21, 0),
    "Sterling Reservations S2": (21, 18),
    CEDAR_S4: (22, 13),
    NORTH_S2: (13, 6),
    HARBOR_S3: (31, 25),
}


def daterange(d0, d1):
    days = []
    d = d0
    while d <= d1:
        days.append(d)
        d += timedelta(days=1)
    return days


def main():
    print("== seed-D3 run (NULLFILL_APPROVED=%s) ==" % NULLFILL)

    # 0. pre-flight: workspace field must exist (F1)
    st, _ = req("GET", "/fields/os_tasks/workspace")
    if st != 200:
        print("FATAL: os_tasks.workspace missing (F1 not landed), aborting personal seeding")
        sys.exit(1)

    # baseline Muster count (printed for the report)
    st, out = req("GET", "/items/os_tasks?filter[project][_eq]=%s&aggregate[count]=id" % MUSTER_PROJECT)
    muster_before = out["data"][0]["count"]["id"] if st == 200 else "?"
    print("muster board baseline count: %s" % muster_before)

    # 1+2. sprints (upsert by name)
    sprint_ids = {CEDAR_S4: CEDAR_S4, NORTH_S2: NORTH_S2, HARBOR_S3: HARBOR_S3}
    sprint_meta = {}  # id -> (start_date, end_date, status)
    for s in NEW_SPRINTS:
        payload = dict(s)
        payload["is_test_data"] = False
        sid, _ = upsert("os_sprints", {"name": {"_eq": s["name"]}}, payload)
        sprint_ids[s["name"]] = sid
        sprint_meta[sid] = (s["start_date"], s["end_date"], s["status"])
    # existing active sprint windows
    sprint_meta[CEDAR_S4] = ("2026-07-07", "2026-07-20", "active")
    sprint_meta[NORTH_S2] = ("2026-07-09", "2026-07-22", "active")
    sprint_meta[HARBOR_S3] = ("2026-07-05", "2026-07-18", "active")

    # 3. tasks (create parents first so parent_task can resolve)
    task_ids = {}  # (project, name) -> id
    ordered = [t for t in T if not t["parent"]] + [t for t in T if t["parent"]]
    for t in ordered:
        sprint_ref = t["sprint"]
        sid = sprint_ids.get(sprint_ref) if sprint_ref else None
        payload = {
            "name": t["name"], "project": t["project"], "status": t["status"],
            "priority": t["priority"], "type": t["ttype"], "points": t["points"],
            "hours_estimate": round(t["points"] * 2.5, 1),
            "assigned_to": t["assigned"], "due_date": t["due"],
            "is_visible_to_client": t["cv"], "responsibility": t["resp"],
            "organization": PROJECT_ORG[t["project"]],
            "is_test_data": False,
        }
        if sid:
            payload["sprint"] = sid
        if t["rank"]:
            payload["backlog_rank"] = t["rank"]
        if t["completed"]:
            payload["date_completed"] = t["completed"]
        if t["flagship"] and t["name"] in FLAGSHIP_DETAIL:
            desc, ac = FLAGSHIP_DETAIL[t["name"]]
            payload["description"] = desc
            payload["acceptance_criteria"] = ac
        if t["parent"]:
            pid = task_ids.get((t["project"], t["parent"]))
            if pid:
                payload["parent_task"] = pid
        backdate = {"date_created": t["created"], "user_created": t["assigned"]}
        flt = {"_and": [{"project": {"_eq": t["project"]}}, {"name": {"_eq": t["name"]}}]}
        tid, _ = upsert("os_tasks", flt, payload, backdate=backdate)
        task_ids[(t["project"], t["name"])] = tid

    # 12. personal tasks
    for p in PERSONAL:
        payload = {
            "name": p["name"], "workspace": "personal", "project": None,
            "status": p["status"], "priority": "P2", "type": "task",
            "assigned_to": DEMO, "due_date": p["due"], "backlog_rank": p["rank"],
            "is_visible_to_client": False, "responsibility": "team",
            "is_test_data": False,
        }
        flt = {"_and": [{"name": {"_eq": p["name"]}}, {"workspace": {"_eq": "personal"}}]}
        backdate = {"date_created": p["created"], "user_created": DEMO}
        upsert("os_tasks", flt, payload, backdate=backdate)

    # 4. sprint snapshots (bulk diff per sprint)
    for ref, (total, target) in SNAPSHOT_SHAPE.items():
        sid = sprint_ids.get(ref, ref)
        start_s, end_s, status = sprint_meta[sid]
        d0 = date.fromisoformat(start_s)
        d1 = date.fromisoformat(end_s)
        if status == "active":
            d1 = min(d1, TODAY)
        days = daterange(d0, d1)
        n = max(len(days) - 1, 1)
        existing = search("os_sprint_snapshots", {"sprint": {"_eq": sid}},
                          fields="id,snapshot_date", limit=200)
        have = {r["snapshot_date"] for r in existing}
        batch = []
        for i, d in enumerate(days):
            ds = d.isoformat()
            remaining = round(total - (total - target) * (i / n))
            if ds in have:
                tally("os_sprint_snapshots", "skipped")
                continue
            batch.append({"sprint": sid, "snapshot_date": ds,
                          "remaining_points": remaining,
                          "completed_points": total - remaining})
        if batch:
            st, out = req("POST", "/items/os_sprint_snapshots", batch)
            if st in (200, 204):
                for _ in batch:
                    tally("os_sprint_snapshots", "created")
            else:
                for _ in batch:
                    tally("os_sprint_snapshots", "failed")
                print("  snapshot batch failed for %s: %s %s" % (sid, st, str(out)[:200]))

    # 5+6. deliverables and decisions
    for (proj, name, status, fid, url, desc, sort, base, submitter) in DELIVERABLES:
        payload = {"project": proj, "name": name, "status": status,
                   "description": desc, "sort": sort, "is_test_data": False}
        if fid:
            payload["file"] = fid
        if url:
            payload["url"] = url
        d0 = date.fromisoformat(base)
        backdate = {"date_created": d0.isoformat() + "T10:00:00", "user_created": submitter}
        flt = {"_and": [{"project": {"_eq": proj}}, {"name": {"_eq": name}}]}
        did, _ = upsert("os_deliverables", flt, payload, backdate=backdate)
        if not did:
            continue
        # decision trail derived from status
        if status == "approved":
            trail = [("submitted", submitter, 0, "Uploaded for client review."),
                     ("approved", ADMIN, 3, "Approved on behalf of the client after the review call.")]
        elif status == "revision_requested":
            trail = [("submitted", submitter, 0, "Uploaded for client review."),
                     ("revision_requested", ADMIN, 2, "Client requested revisions, notes shared in the project thread.")]
        elif name in RESUBMITTED:
            trail = [("submitted", submitter, 0, "Uploaded for client review."),
                     ("revision_requested", ADMIN, 2, "Client asked for adjustments before sign-off."),
                     ("resubmitted", submitter, 5, "Revised version uploaded addressing all notes.")]
        else:
            trail = [("submitted", submitter, 0, "Uploaded for client review.")]
        for (action, actor, offset, comment) in trail:
            dpayload = {"deliverable": did, "action": action, "comment": comment}
            dts = (d0 + timedelta(days=offset)).isoformat() + "T11:00:00"
            dflt = {"_and": [{"deliverable": {"_eq": did}}, {"action": {"_eq": action}}]}
            upsert("os_deliverable_decisions", dflt, dpayload,
                   backdate={"date_created": dts, "user_created": actor})

    # 7. project updates
    for (proj, message, cv, created, author) in UPDATES:
        key40 = message[:40]
        flt = {"_and": [{"project": {"_eq": proj}}, {"message": {"_starts_with": key40}}]}
        payload = {"project": proj, "message": message, "is_client_visible": cv,
                   "is_test_data": False}
        upsert("os_project_updates", flt, payload,
               backdate={"date_created": created, "user_created": author})

    # 8. project contacts
    for (proj, cid) in PROJECT_CONTACTS:
        flt = {"_and": [{"os_projects_id": {"_eq": proj}}, {"contacts_id": {"_eq": cid}}]}
        upsert("os_project_contacts", flt, {"os_projects_id": proj, "contacts_id": cid})

    # 9. task files + comments on flagship tasks
    flagships = [t for t in T if t["flagship"]]
    for i, t in enumerate(flagships):
        tid = task_ids.get((t["project"], t["name"]))
        if not tid:
            continue
        files = [PHOTOS[i]] + ([PHOTOS[i + 10] if i + 10 < len(PHOTOS) else None] if i < 5 else [None])
        for fid in [f for f in files if f]:
            flt = {"_and": [{"os_tasks_id": {"_eq": tid}}, {"directus_files_id": {"_eq": fid}}]}
            upsert("os_task_files", flt, {"os_tasks_id": tid, "directus_files_id": fid})
        # comments (run-day timestamps accepted per plan)
        q = urllib.parse.urlencode({
            "filter": json.dumps({"_and": [{"collection": {"_eq": "os_tasks"}},
                                           {"item": {"_eq": tid}}]}),
            "fields": "id,comment", "limit": "50"})
        st, out = req("GET", "/comments?" + q)
        have = {c["comment"] for c in out.get("data", [])} if st == 200 else set()
        for text in FLAGSHIP_COMMENTS.get(t["name"], []):
            if text in have:
                tally("directus_comments", "skipped")
                continue
            st, out = req("POST", "/comments",
                          {"collection": "os_tasks", "item": tid, "comment": text})
            tally("directus_comments", "created" if st in (200, 204) else "failed")

    # 10. repositories (new only; gated null-fill of existing descriptions skipped)
    repo_ids = {}
    for r in NEW_REPOS:
        payload = dict(r)
        payload["is_test_data"] = False
        rid, _ = upsert("repositories", {"name": {"_eq": r["name"]}}, payload)
        repo_ids[r["name"]] = rid
    # existing repos for release routing
    for name in ["cedar-web", "harbor-app", "sterling-reservations", "northlight-brand"]:
        rows = search("repositories", {"name": {"_eq": name}}, fields="id")
        repo_ids[name] = rows[0]["id"]
    if NULLFILL:
        print("NULLFILL branch not implemented this run (token absent at build time)")
    else:
        print("GATED SKIPPED: descriptions on 5 existing repos (needs NULLFILL_APPROVED)")
        print("GATED SKIPPED: budget_cap on synthetic projects (needs NULLFILL_APPROVED)")

    # 11. releases (skip-if-exists ONLY; never patch matched rows)
    for (repo, version, title, rtype, status, rdate, summary, added, changed, fixed, cnotes) in NEW_RELEASES:
        rid = repo_ids[repo]
        if rid == "aba3e9b9-91ea-410d-9f84-9d445eb9d7a7":
            raise RuntimeError("routing bug: attempted release on bloom-shopify")
        rows = search("releases", {"_and": [{"repository_id": {"_eq": rid}},
                                            {"version": {"_eq": version}}]}, fields="id")
        if rows:
            tally("releases", "skipped")
            continue
        parts = []
        if added:
            parts.append("### Added\n" + "\n".join("- " + a for a in added))
        if changed:
            parts.append("### Changed\n" + "\n".join("- " + c for c in changed))
        if fixed:
            parts.append("### Fixed\n" + "\n".join("- " + f for f in fixed))
        payload = {
            "repository_id": rid, "version": version, "title": title,
            "release_type": rtype, "status": status,
            "release_date": rdate + "T12:00:00", "summary": summary,
            "changelog": "\n\n".join(parts) if parts else summary,
            "commit_hash": chash(repo, version),
            "is_client_visible": status in ("published", "shared"),
            "is_test_data": False,
        }
        if cnotes:
            payload["client_notes"] = cnotes
        st, out = req("POST", "/items/releases", payload)
        tally("releases", "created" if st in (200, 204) else "failed")
        if st not in (200, 204):
            print("  release create failed %s %s: %s" % (repo, version, str(out)[:200]))

    # summary
    print("\n-- run summary --")
    for col in sorted(COUNTS):
        c = COUNTS[col]
        print("%s: created %d / updated %d / skipped %d / failed %d"
              % (col, c["created"], c["updated"], c["skipped"], c["failed"]))
    st, out = req("GET", "/items/os_tasks?filter[project][_eq]=%s&aggregate[count]=id" % MUSTER_PROJECT)
    print("muster board count after run: %s" % out["data"][0]["count"]["id"])


def gql(query):
    st, out = req("POST", "/graphql", {"query": query})
    return st, out


def verify():
    print("== seed-D3 verify ==")
    ok = True

    st, out = gql('query { os_tasks(filter: { project: { id: { _neq: "%s" } } }, limit: 5, sort:["-date_updated"]) '
                  '{ id name status type priority due_date points backlog_rank is_visible_to_client '
                  'assigned_to { first_name last_name } project { id name organization { id name service_status } } '
                  'sprint { id name } } }' % MUSTER_PROJECT)
    good = st == 200 and isinstance(out, dict) and not out.get("errors") and out["data"]["os_tasks"]
    print("PROBE tasks: %s rows=%s" % (st, len(out["data"]["os_tasks"]) if good else out))
    ok = ok and bool(good)

    st, out = gql('query { os_sprints(limit:5, sort:["-status","rank"]) { id name status start_date end_date '
                  'capacity_points goal review_notes tasks { points status } '
                  'snapshots { snapshot_date remaining_points completed_points } } }')
    good = st == 200 and isinstance(out, dict) and not out.get("errors") and out["data"]["os_sprints"]
    if good:
        withsnaps = [s for s in out["data"]["os_sprints"] if s["snapshots"]]
        print("PROBE sprints: 200 rows=%d with_snapshots=%d" % (len(out["data"]["os_sprints"]), len(withsnaps)))
    else:
        print("PROBE sprints FAILED: %s %s" % (st, str(out)[:300]))
    ok = ok and bool(good)

    st, out = gql('query { releases(limit:5, sort:["-release_date"]) { id title version status release_date '
                  'release_type summary changelog is_client_visible repository_id { id name project_id { id name } } } }')
    good = st == 200 and isinstance(out, dict) and not out.get("errors") and out["data"]["releases"]
    print("PROBE releases: %s rows=%s" % (st, len(out["data"]["releases"]) if good else str(out)[:300]))
    ok = ok and bool(good)

    rows = search("repositories", {"name": {"_eq": "vellum-portfolio"}}, fields="id")
    rid = rows[0]["id"] if rows else None
    st, out = gql('query { repositories_by_id(id:"%s") { id name url platform default_branch status '
                  'date_created date_updated project_id { id name } } }' % rid)
    good = st == 200 and isinstance(out, dict) and not out.get("errors") and out["data"]["repositories_by_id"]
    print("PROBE repo detail (%s): %s %s" % (rid, st, "OK" if good else str(out)[:300]))
    ok = ok and bool(good)

    st, out = req("GET", "/items/releases?filter=%s&aggregate[count]=id"
                  % urllib.parse.quote(json.dumps({"repository_id": {"_eq": "aba3e9b9-91ea-410d-9f84-9d445eb9d7a7"}})))
    n = out["data"][0]["count"]["id"]
    print("CHECK bloom-shopify release count (must be 1): %s" % n)
    ok = ok and str(n) == "1"

    st, out = req("GET", "/items/os_tasks?filter[project][_eq]=%s&aggregate[count]=id" % MUSTER_PROJECT)
    n = out["data"][0]["count"]["id"]
    print("CHECK muster board count (must be 25): %s" % n)
    ok = ok and str(n) == "25"

    # spot-check: completed-sprint task backdating
    rows = search("os_tasks", {"_and": [{"project": {"_eq": CEDAR_WEB}},
                                        {"name": {"_eq": "Build the locations map page"}}]},
                  fields="id,date_created,date_completed,sprint")
    r = rows[0]
    dc = r["date_created"][:10]
    good = dc < "2026-06-01" and r["date_created"] < r["date_completed"]
    print("CHECK completed-sprint task backdate: date_created=%s (< sprint start 2026-06-01 and < date_completed %s): %s"
          % (r["date_created"], r["date_completed"], "PASS" if good else "FAIL"))
    ok = ok and good

    # spot-check: non-admin user_created on a project update
    rows = search("os_project_updates", {"message": {"_starts_with": "Order tracking page is on staging"}},
                  fields="id,user_created,date_created")
    r = rows[0]
    good = r["user_created"] != ADMIN
    print("CHECK project update non-admin author: user_created=%s date_created=%s: %s"
          % (r["user_created"], r["date_created"], "PASS" if good else "FAIL"))
    ok = ok and good

    # personal tasks present
    rows = search("os_tasks", {"workspace": {"_eq": "personal"}}, fields="id,name", limit=20)
    print("CHECK personal tasks (expect 6): %d" % len(rows))
    ok = ok and len(rows) == 6

    print("VERIFY RESULT: %s" % ("PASS" if ok else "FAIL"))


if __name__ == "__main__":
    if "--verify" in sys.argv:
        verify()
    else:
        main()
