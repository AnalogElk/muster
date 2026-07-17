#!/usr/bin/env python3
"""Run-2 final gap-fix: employee/projects residuals.

1. NULLFILL (authorized, FULL AUTO 2026-07-16): set organization=1 (Demo Co)
   on the six studio-flavored os_projects rows whose organization is null.
   Only-when-null guard; never overwrites a non-null org.
2. NULLFILL: set parent_project = Cedar & Co Care Plan Retainer id on the two
   existing Cedar deliverables (Loyalty Card Microsite, Spring Menu Launch).
   Only-when-null guard.
3. UPSERT one new active child deliverable under the retainer so the band
   shows in-flight work ("2 of 3 delivered"). Natural key: exact name.

Idempotent; safe to re-run. Prints counts and ids only.
"""
import json
import os
import urllib.request
import urllib.parse

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


def req(method, path, params=None, body=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.load(resp)


STUDIO_PROJECT_NAMES = [
    "Golden Hour Pier Series",
    "Muster Landing Illustrations",
    "Charcoal Figure Studies",
    "Client Case Study Covers",
    "Desert Road Trip Photo Essay",
    "Generative Poster Experiments",
]

projs = req("GET", "/items/os_projects", {
    "fields": "id,name,organization,kind,parent_project,status",
    "limit": "-1",
})["data"]
by_name = {p["name"]: p for p in projs}

# --- 1. org null-fill on the six studio projects ---
org_filled = org_skipped = 0
for name in STUDIO_PROJECT_NAMES:
    p = by_name.get(name)
    if not p:
        print(f"  WARN missing project: {name!r}")
        continue
    if p["organization"] is None:
        req("PATCH", f"/items/os_projects/{p['id']}", body={"organization": 1})
        org_filled += 1
    else:
        org_skipped += 1
print(f"os_projects.organization null-fill: filled {org_filled} / skipped {org_skipped}")

# --- 2. parent_project null-fill on Cedar deliverables ---
retainer = by_name.get("Cedar & Co - Care Plan Retainer")
assert retainer and retainer["kind"] == "retainer", "retainer row not found"
RET_ID = retainer["id"]
parent_filled = parent_skipped = 0
for name in ("Cedar & Co - Loyalty Card Microsite", "Cedar & Co - Spring Menu Launch"):
    p = by_name.get(name)
    if not p:
        print(f"  WARN missing project: {name!r}")
        continue
    if p.get("parent_project") is None:
        req("PATCH", f"/items/os_projects/{p['id']}", body={"parent_project": RET_ID})
        parent_filled += 1
    else:
        parent_skipped += 1
print(f"os_projects.parent_project null-fill: filled {parent_filled} / skipped {parent_skipped} (retainer {RET_ID})")

# --- 3. upsert one active child deliverable ---
CHILD_NAME = "Cedar & Co - Care Plan: July Site Maintenance"
created = 0
if CHILD_NAME in by_name:
    print(f"child deliverable: skipped (exists {by_name[CHILD_NAME]['id']})")
else:
    row = req("POST", "/items/os_projects", body={
        "name": CHILD_NAME,
        "organization": 2,
        "kind": "deliverable",
        "parent_project": RET_ID,
        "status": "in_progress",
        "project_type": "code",
        "start_date": "2026-07-01T09:00:00",
        "due_date": "2026-07-31T17:00:00",
        "description": "Monthly care plan cycle: dependency updates, uptime review, two content edits requested by the Cedar team, and a lighthouse pass on the menu pages.",
        "is_test_data": False,
    })["data"]
    created = 1
    print(f"child deliverable: created {row['id']}")

# --- verification probe (portal fragment shape) ---
q = {"query": """
query {
  os_projects(filter: {kind: {_eq: \"retainer\"}}, limit: 5) {
    id name kind status
    child_projects { id name status kind }
  }
}"""}
body = json.dumps(q).encode()
r = urllib.request.Request(BASE + "/graphql", data=body, method="POST", headers={
    "Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
with urllib.request.urlopen(r, timeout=30) as resp:
    out = json.load(resp)
if out.get("errors"):
    print("GRAPHQL ERRORS:", out["errors"])
else:
    for ret in out["data"]["os_projects"]:
        kids = ret.get("child_projects") or []
        print(f"VERIFY retainer {ret['name']!r}: {len(kids)} children -> {[k['name'] for k in kids]}")

nullorg = req("GET", "/items/os_projects", {
    "filter": json.dumps({"organization": {"_null": True}}),
    "fields": "id,name", "limit": "-1"})["data"]
print(f"VERIFY projects with null organization remaining: {len(nullorg)}")
for p in nullorg:
    print("   still null:", p["name"])
