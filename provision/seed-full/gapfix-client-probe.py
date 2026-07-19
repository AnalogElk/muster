#!/usr/bin/env python3
"""GraphQL + REST probes proving the four fixed client-portal sections return data.

Runs the portal's own query shapes as the CLIENT demo user token (PBAC-real),
plus the settings /users/me fetch that previously failed on the missing field.
Prints counts and small samples only; never prints tokens.
"""
import json
import os
import urllib.request
import urllib.parse

BASE = "https://cms.musterr.dev"
CLIENT_USER = "91fb50ea-5ead-4713-9c48-a32bb945932f"


def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def req(path, method="GET", body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:300]}


ADMIN = load_env()["DIRECTUS_ADMIN_TOKEN"]

# login as client demo user (public demo creds)
login_body = json.dumps({"email": "client@muster.dev", "password": "muster-demo"}).encode()
lr = urllib.request.Request(BASE + "/auth/login", data=login_body, method="POST",
                            headers={"Content-Type": "application/json"})
CLIENT = json.load(urllib.request.urlopen(lr))["data"]["access_token"]
print("login client@muster.dev: OK")

# 1. NOTIFICATIONS: exact fields the panel reads, caller token, recipient filter
p = urllib.parse.urlencode({
    "filter[recipient_user][_eq]": CLIENT_USER,
    "sort": "-date_created",
    "limit": "200",
    "fields": "id,title,body,type,href,date_created,read_at",
})
res = req("/items/os_notifications?" + p, token=CLIENT)
rows = res.get("data", [])
unread = sum(1 for r in rows if not r["read_at"])
print("NOTIFICATIONS: rows=%d unread=%d" % (len(rows), unread))
for r in rows[:3]:
    print("   ", r["type"], "|", r["title"][:55], "| read=", bool(r["read_at"]))

# GraphQL shape (verification standard)
gql = {"query": "query { os_notifications(filter: {recipient_user: {_eq: \"%s\"}}, limit: 3, sort: [\"-date_created\"]) { id title type href read_at } }" % CLIENT_USER}
g = req("/graphql", method="POST", body=gql, token=ADMIN)
print("GQL os_notifications:", "ERRORS" if g.get("errors") else "OK rows=%d" % len(g["data"]["os_notifications"]))

# 2. SUPPORT: ticket list shape (org-scoped like the route does for clients)
p = urllib.parse.urlencode({
    "sort": "-date_created", "limit": "200",
    "fields": "id,subject,status,priority,category,date_created,date_updated,resolved_at,submitted_by,responses.id,project.id,project.name,project.organization.id,project.organization.name",
    "filter[project][organization][_eq]": "2",
})
res = req("/items/os_client_tickets?" + p, token=CLIENT)
rows = res.get("data", [])
print("SUPPORT tickets (org 2, client token): rows=%d" % len(rows))
for r in rows[:5]:
    print("   ", r["status"], "|", r["subject"][:50], "| responses=", len(r.get("responses") or []))

gql = {"query": "query { os_client_tickets(limit: 3) { id subject status priority responses { id is_staff } } }"}
g = req("/graphql", method="POST", body=gql, token=ADMIN)
print("GQL os_client_tickets:", "ERRORS: " + json.dumps(g.get("errors"))[:150] if g.get("errors") else "OK rows=%d" % len(g["data"]["os_client_tickets"]))

# 3. HELP: collections + audience-scoped article counts (route shape, client token)
res = req("/items/help_collections?fields=id,title,slug,description,icon,sort&sort=sort,title&limit=100", token=CLIENT)
colls = res.get("data", [])
flt = json.dumps({"_and": [{"status": {"_eq": "published"}}, {"audience": {"_in": ["all", "client"]}}]})
res2 = req("/items/help_articles?aggregate[count]=id&groupBy[]=help_collection&filter=" + urllib.parse.quote(flt), token=CLIENT)
counts = {str(r["help_collection"]): int(r["count"]["id"]) for r in res2.get("data", [])}
print("HELP collections visible to client:")
for c in colls:
    n = counts.get(str(c["id"]), 0)
    if n > 0:
        print("   ", c["slug"], "articles=", n)

gql = {"query": "query { help_articles(filter: {status: {_eq: \"published\"}, audience: {_in: [\"all\",\"client\"]}}, limit: 3) { id title slug audience help_collection { slug } } }"}
g = req("/graphql", method="POST", body=gql, token=ADMIN)
print("GQL help_articles:", "ERRORS: " + json.dumps(g.get("errors"))[:150] if g.get("errors") else "OK rows=%d" % len(g["data"]["help_articles"]))

# 4. SETTINGS: the exact /users/me fetch that hydrates the settings page
res = req("/users/me?fields=notification_preferences,title,location,appearance,language", token=CLIENT)
if "_error" in res:
    print("SETTINGS /users/me: ERROR", res["_error"], res["_body"])
else:
    d = res["data"]
    print("SETTINGS /users/me: title=%r location=%r language=%r" % (d.get("title"), d.get("location"), d.get("language")))
res = req("/users/me?fields=id,email,first_name,last_name,avatar,role.id,role.name,is_test_data,test_only", token=CLIENT)
d = res.get("data", {})
print("SETTINGS session user: name=%s %s role=%s avatar=%s" % (
    d.get("first_name"), d.get("last_name"), (d.get("role") or {}).get("name"), d.get("avatar")))
