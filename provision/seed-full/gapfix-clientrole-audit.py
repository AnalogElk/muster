#!/usr/bin/env python3
"""Audit roles/policies/permissions on the Muster demo Directus.

Prints only ids, names, counts. Never prints the token.
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


def req(path, method="GET", body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:500]}


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
