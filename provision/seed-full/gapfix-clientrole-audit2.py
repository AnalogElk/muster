#!/usr/bin/env python3
"""Deep audit of client-portal wiring for client@muster.dev. Prints ids/names/counts only."""
import json
import os
import urllib.request
import urllib.parse

BASE = "https://cms.musterr.dev"
CLIENT_USER = "91fb50ea-5ead-4713-9c48-a32bb945932f"
EMP_USER = "257a4b75-deff-476d-953d-1898c57f6684"


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
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Authorization": "Bearer " + (token or TOKEN),
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:300]}


# 1. notifications by recipient
rows = req("/items/os_notifications?fields=id,recipient_user,title,type,read_at,dedupe_key&limit=200").get("data", [])
by = {}
for r in rows:
    by.setdefault(r["recipient_user"], []).append(r)
print("NOTIFICATIONS by recipient:")
for k, v in by.items():
    tag = "CLIENT" if k == CLIENT_USER else ("EMPLOYEE" if k == EMP_USER else "?")
    unread = sum(1 for x in v if not x["read_at"])
    print("  ", k, tag, "count=", len(v), "unread=", unread)
    for x in v[:3]:
        print("      ", x["type"], "|", x["title"][:60])

# 2. client user details
u = req("/users/%s?fields=id,email,first_name,last_name,title,location,avatar,status,role.name" % CLIENT_USER)
print("CLIENT USER:", json.dumps(u.get("data"), default=str))

# 3. contact link for client user
c = req("/items/contacts?filter[user][_eq]=%s&fields=id,email,first_name,last_name,organizations.organizations_id.id,organizations.organizations_id.name" % CLIENT_USER)
print("CONTACT by user FK:", json.dumps(c.get("data"), default=str))
c2 = req("/items/contacts?filter[email][_icontains]=" + urllib.parse.quote("client@muster.dev") + "&fields=id,email,organizations.organizations_id.id,organizations.organizations_id.name")
print("CONTACT by email:", json.dumps(c2.get("data"), default=str))

# 4. tickets: project -> org
t = req("/items/os_client_tickets?fields=id,subject,status,priority,submitted_by,project.name,project.organization.id,project.organization.name,responses.id&limit=50").get("data", [])
print("TICKETS:", len(t))
orgs = {}
for x in t:
    proj = x.get("project") or {}
    org = (proj.get("organization") or {})
    key = "%s %s" % (org.get("id"), org.get("name"))
    orgs.setdefault(key, 0)
    orgs[key] += 1
    print("  ", x["status"], x["priority"], "| org=", org.get("id"), "|", (x["subject"] or "")[:50], "| responses=", len(x.get("responses") or []), "| submitted_by=", (x.get("submitted_by") or "")[:8])
print("TICKETS per org:", orgs)

# 5. help rows
hc = req("/items/help_collections?fields=id,title,slug,icon,sort&limit=50").get("data", [])
print("HELP_COLLECTIONS:", len(hc))
for x in hc:
    print("  ", x["id"], x["slug"], "|", x["title"], "| icon=", x["icon"])
ha = req("/items/help_articles?fields=id,title,slug,status,audience,help_collection&limit=200").get("data", [])
print("HELP_ARTICLES:", len(ha))
agg = {}
for x in ha:
    agg.setdefault((str(x.get("help_collection")), x.get("status"), x.get("audience")), 0)
    agg[(str(x.get("help_collection")), x.get("status"), x.get("audience"))] += 1
for k, v in sorted(agg.items()):
    print("   coll=%s status=%s audience=%s -> %d" % (k[0], k[1], k[2], v))

# 6. help fields on live
for coll in ["help_collections", "help_articles"]:
    f = req("/fields/" + coll)
    names = sorted(x["field"] for x in f.get("data", []))
    print("FIELDS", coll, names)

# 7. login test as client user with candidate demo passwords (statuses only)
for pw in ["muster-demo", "muster-client", "Pass123!demo"]:
    body = {"email": "client@muster.dev", "password": pw}
    data = json.dumps(body).encode()
    r = urllib.request.Request(BASE + "/auth/login", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            j = json.load(resp)
            ok = bool(j.get("data", {}).get("access_token"))
            print("LOGIN client@muster.dev pw=%s -> OK access_token_present=%s" % (pw, ok))
            if ok:
                utok = j["data"]["access_token"]
                me = req("/users/me?fields=id,email,role.id,role.name", token=utok)
                print("   /users/me:", json.dumps(me.get("data"), default=str))
                # can the client token read its own notifications / tickets / help?
                for probe in [
                    "/items/os_notifications?filter[recipient_user][_eq]=%s&aggregate[count]=id" % CLIENT_USER,
                    "/items/os_client_tickets?aggregate[count]=id",
                    "/items/help_collections?aggregate[count]=id",
                    "/items/help_articles?aggregate[count]=id",
                    "/items/contacts?filter[user][_eq]=%s&fields=id&limit=1" % CLIENT_USER,
                ]:
                    res = req(probe, token=utok)
                    if "_error" in res:
                        print("   PROBE", probe.split("?")[0], "ERROR", res["_error"], res["_body"][:120])
                    else:
                        print("   PROBE", probe.split("?")[0], "->", json.dumps(res.get("data"))[:120])
            break
    except urllib.error.HTTPError as e:
        print("LOGIN client@muster.dev pw=%s -> HTTP %s" % (pw, e.code))
