#!/usr/bin/env python3
"""Probe for run-2 final gap-fix: client/tasks + client/invoices residuals.

Prints ONLY demo-content ids/names/counts. Never prints the token.
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client.directus_client import call, load_env  # noqa: E402

BASE = "https://cms.musterr.dev"


# load_env imported from _client.directus_client


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    st, raw, err = call("GET", url, headers={"Authorization": "Bearer " + TOKEN}, timeout=None)
    if err is not None:
        raise err
    return json.loads(raw)


# 1. Demo users and their avatars
users = req("/users", {
    "filter": json.dumps({"email": {"_in": ["client@muster.dev", "demo@muster.dev"]}}),
    "fields": "id,email,first_name,last_name,avatar",
})["data"]
for u in users:
    print("USER:", u["email"], "id=", u["id"], "name=", u["first_name"], u["last_name"], "avatar=", u["avatar"])
    if u.get("avatar"):
        try:
            f = req("/files/" + u["avatar"])["data"]
            print("  AVATAR_FILE:", f["id"], f.get("type"), f.get("filesize"), f.get("title"))
        except Exception as e:
            print("  AVATAR_FILE_ERROR:", e)

# 2. Org 2 projects
projs = req("/items/os_projects", {
    "filter": json.dumps({"organization": {"_eq": 2}}),
    "fields": "id,name,status",
    "limit": "-1",
})["data"]
for p in projs:
    print("ORG2_PROJECT:", p["id"], "|", p["name"], "|", p["status"])

proj_ids = [p["id"] for p in projs]

# 3. Org2 client-visible tasks by status
tasks = req("/items/os_tasks", {
    "filter": json.dumps({
        "project": {"_in": proj_ids},
        "is_visible_to_client": {"_eq": True},
    }),
    "fields": "id,name,status,priority,due_date,project",
    "limit": "-1",
})["data"]
from collections import Counter
c = Counter(t["status"] for t in tasks)
print("ORG2_CLIENT_VISIBLE_TASKS_TOTAL:", len(tasks))
print("ORG2_STATUS_COUNTS:", dict(c))
blocked = [t for t in tasks if (t["status"] or "").lower().replace("_", "") in ("blocked", "stuck", "waiting", "onhold", "paused")]
print("ORG2_BLOCKED_FAMILY:", len(blocked), [t["name"] for t in blocked])

# 4. Check existing blocked-family tasks anywhere (for employee board context)
all_blocked = req("/items/os_tasks", {
    "filter": json.dumps({"status": {"_in": ["blocked", "on_hold", "paused", "waiting"]}}),
    "fields": "id,name,status,project,is_visible_to_client",
    "limit": "-1",
})["data"]
print("GLOBAL_BLOCKED_FAMILY:", len(all_blocked))
for t in all_blocked:
    print("  BLOCKED_TASK:", t["id"], "|", t["name"], "|", t["status"], "| visible=", t["is_visible_to_client"])

# 5. Sample invoice status/billing_type mapping for org 2 (context only)
invs = req("/items/os_invoices", {
    "filter": json.dumps({"organization": {"_eq": 2}}),
    "fields": "id,invoice_number,status,billing_type,stripe_subscription_id,due_date",
    "limit": "-1",
})["data"]
print("ORG2_INVOICES:", len(invs))
for i in invs:
    print("  INV:", i.get("invoice_number"), "| status=", i.get("status"), "| billing=", i.get("billing_type"), "| sub=", ("set" if i.get("stripe_subscription_id") else "null"), "| due=", i.get("due_date"))
