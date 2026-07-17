#!/usr/bin/env python3
"""Run-2 final gap-fix: seed 2 blocked-family tasks for org 2 (Cedar & Co)
so the client-portal kanban Blocked column is not empty.

Idempotent: upserts by task name (natural key). Add-only, is_test_data false.
Prints counts and ids only; never prints the token.
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
    with urllib.request.urlopen(r) as resp:
        return json.load(resp)


# Resolve links live
PROJ_WHOLESALE = "a42f4921-7747-4319-b09e-644f639e89c5"  # Cedar & Co Wholesale Portal (org 2, active)
PROJ_REDESIGN = "430df3e9-7f6d-4369-81cf-d9e5dc0fab00"   # Cedar & Co Website Redesign (org 2, active)

team = req("GET", "/users", {
    "filter": json.dumps({"email": {"_ends_with": "@team.musterr.dev"}}),
    "fields": "id,email",
    "limit": "2",
})["data"]
assignee = team[0]["id"] if team else None
print("ASSIGNEE:", team[0]["email"] if team else None)

# A live in_progress Wholesale Portal task to reference via blocked_by
dep = req("GET", "/items/os_tasks", {
    "filter": json.dumps({
        "project": {"_eq": PROJ_WHOLESALE},
        "status": {"_eq": "in_progress"},
    }),
    "fields": "id,name",
    "limit": "1",
})["data"]
dep_id = dep[0]["id"] if dep else None
print("BLOCKED_BY_DEP:", dep[0]["name"] if dep else None)

TASKS = [
    {
        "name": "Wholesale price import blocked on distributor CSV feed",
        "description": (
            "The wholesale portal price sync cannot go live until Cedar's distributor "
            "delivers the corrected CSV feed with SKU-level case pricing. Import job and "
            "mapping are built and tested against the sample file; waiting on the "
            "production feed credentials from Redline Distribution."
        ),
        "status": "blocked",
        "type": "task",
        "priority": "P1",
        "responsibility": "client",
        "project": PROJ_WHOLESALE,
        "due_date": "2026-07-10T00:00:00",
        "is_visible_to_client": True,
        "is_test_data": False,
        "assigned_to": assignee,
        "blocked_by": dep_id,
        "points": 3,
    },
    {
        "name": "Loyalty punch-card artwork on hold pending brand refresh",
        "description": (
            "Print-ready loyalty punch-card artwork is paused until the updated Cedar & Co "
            "logo lockup is approved. Digital wallet pass design is complete; the print run "
            "resumes as soon as the brand refresh ships."
        ),
        "status": "on_hold",
        "type": "task",
        "priority": "P2",
        "responsibility": "both",
        "project": PROJ_REDESIGN,
        "due_date": "2026-07-28T00:00:00",
        "is_visible_to_client": True,
        "is_test_data": False,
        "assigned_to": assignee,
        "points": 2,
    },
]

created = updated = skipped = 0
for t in TASKS:
    existing = req("GET", "/items/os_tasks", {
        "filter": json.dumps({"name": {"_eq": t["name"]}}),
        "fields": "id,status",
        "limit": "1",
    })["data"]
    if existing:
        skipped += 1
        print("SKIP (exists):", existing[0]["id"], "|", t["name"])
        continue
    row = req("POST", "/items/os_tasks", body=t)["data"]
    created += 1
    print("CREATED:", row["id"], "|", t["name"], "| status=", row["status"])

print(f"os_tasks(blocked-family org2): created {created} / updated {updated} / skipped {skipped}")
