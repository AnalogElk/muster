#!/usr/bin/env python3
"""Audit roles/policies/permissions on the Muster demo Directus.

Prints only ids, names, counts. Never prints the token.
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client.directus_client import call, load_env  # noqa: E402

BASE = "https://cms.musterr.dev"


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(path, method="GET", body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    st, raw, err = call(method, url, data=data, headers=headers, timeout=None)
    if err is not None:
        return {"_error": st, "_body": raw.decode()[:500]}
    return json.loads(raw)


roles = req("/roles?fields=id,name&limit=50").get("data", [])
print("ROLES:")
for r in roles:
    print("  ", r["id"], r["name"])

pols = req("/policies?fields=id,name,app_access,admin_access&limit=50").get("data", [])
print("POLICIES:")
for p in pols:
    print("  ", p["id"], p["name"], "app_access=", p["app_access"], "admin=", p["admin_access"])

acc = req("/access?fields=id,role,user,policy&limit=100").get("data", [])
print("ACCESS:")
for a in acc:
    print("  ", a)

# permissions per policy
for p in pols:
    if p["admin_access"]:
        continue
    perms = req("/permissions?filter[policy][_eq]=%s&fields=id,collection,action&limit=500" % p["id"]).get("data", [])
    cols = sorted(set((x["collection"], x["action"]) for x in perms))
    print("PERMS for policy", p["name"], p["id"], "count=", len(perms))
    for c, a in cols:
        print("   ", a, c)

# collections check
cols = req("/collections?limit=500").get("data", [])
names = sorted(c["collection"] for c in cols if not c["collection"].startswith("directus_"))
print("HELP COLLECTIONS EXIST:", [n for n in names if "help" in n])

# existing client user?
u = req("/users?filter[email][_eq]=" + urllib.parse.quote("client@muster.dev") + "&fields=id,email,role,status")
print("client@muster.dev:", u.get("data"))

for coll in ["os_notifications", "os_client_tickets", "os_client_ticket_responses",
             "organizations_contacts", "contacts"]:
    c = req("/items/%s?aggregate[count]=id" % coll)
    if "_error" in c:
        print("COUNT", coll, "ERROR", c["_error"])
    else:
        print("COUNT", coll, c["data"][0]["count"]["id"] if c.get("data") else "?")
