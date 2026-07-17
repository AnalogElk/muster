#!/usr/bin/env python3
"""Probe for the 4 failing client-portal sections (brand-assets, email, kb,
messages). Read-only. Prints counts/ids/names only, never token values.

Checks, with the ADMIN token:
  1. Client role + client@muster.dev user + policy attachment
  2. contact + organizations_contacts link (org resolution path)
  3. demo policy read grants for the collections the 4 sections hit
  4. rows: org-2 message threads/messages, client-visible kb space + pages
  5. dam_* collections existence (brand-assets blocker)
  6. org 2 website (email domain derivation)
Then, with the CLIENT USER'S OWN session token (public demo creds):
  7. the exact REST/GraphQL shapes the pages issue, to prove policy-scoped
     reads return rows.
"""
import json
import os
import urllib.parse
import urllib.request

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
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
CLIENT_EMAIL = "client@muster.dev"
CLIENT_PASS = "muster-demo"  # public demo cred (landing-page tier), not a secret


def req(path, method="GET", body=None, token=TOKEN):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + token)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"errors": [{"message": "unreadable"}]}


print("== 1. role / user / access ==")
st, d = req("/roles?filter[name][_eq]=Client&fields=id,name")
roles = d.get("data") or []
client_role = roles[0]["id"] if roles else None
print("Client role:", client_role)

st, d = req("/users?filter[email][_eq]=" + urllib.parse.quote(CLIENT_EMAIL)
            + "&fields=id,email,role.id,role.name,status,is_test_data,test_only")
users = d.get("data") or []
if users:
    u = users[0]
    print("client user: id=%s role=%s status=%s is_test_data=%s test_only=%s"
          % (u["id"], (u.get("role") or {}).get("name"), u.get("status"),
             u.get("is_test_data"), u.get("test_only")))
    client_user = u["id"]
else:
    print("client user: MISSING")
    client_user = None

if client_role:
    st, d = req("/access?filter[role][_eq]=%s&fields=id,policy.id,policy.name,policy.app_access" % client_role)
    for row in d.get("data") or []:
        p = row.get("policy") or {}
        print("access: policy=%s name=%s app_access=%s" % (p.get("id"), p.get("name"), p.get("app_access")))

print("== 2. contact / org link ==")
st, d = req("/items/contacts?filter[email][_eq]=" + urllib.parse.quote(CLIENT_EMAIL)
            + "&fields=id,user,first_name,last_name,is_test_data")
cs = d.get("data") or []
print("contact:", cs[0] if cs else "MISSING")
if cs:
    st, d = req("/items/organizations_contacts?filter[contacts_id][_eq]=%s&fields=id,organizations_id" % cs[0]["id"])
    print("organizations_contacts:", d.get("data"))

print("== 3. demo policy read grants ==")
cols = "os_message_threads,os_messages,kb_spaces,kb_pages,organizations,contacts,organizations_contacts,os_projects"
st, d = req("/permissions?filter[policy][_eq]=%s&filter[collection][_in]=%s&fields=collection,action&limit=100"
            % (DEMO_POLICY, cols))
got = sorted({"%s:%s" % (r["collection"], r["action"]) for r in (d.get("data") or [])})
print("grants:", got)

print("== 4. rows ==")
st, d = req("/items/os_message_threads?filter[organization][_eq]=2&fields=id,subject,status,last_message_at,is_test_data&limit=20")
th = d.get("data") or []
print("org2 threads: %d" % len(th))
for t in th:
    print("  ", t["subject"], t["status"], t["last_message_at"], "test=", t["is_test_data"])
st, d = req("/items/os_messages?aggregate[count]=id")
print("os_messages total:", d.get("data"))

st, d = req("/items/kb_spaces?fields=id,name,slug,min_role,is_client_visible,status&limit=50")
for s in d.get("data") or []:
    print("kb_space:", s["slug"], "min_role=", s["min_role"], "client_visible=", s["is_client_visible"], "status=", s["status"])
st, d = req("/items/kb_pages?filter[min_role][_eq]=client&filter[status][_eq]=published&fields=id,title,space&limit=50")
kp = d.get("data") or []
print("client kb_pages published: %d" % len(kp))
for p in kp:
    print("  ", p["title"], "space=", p["space"])

print("== 5. dam_* collections ==")
st, d = req("/collections?limit=-1")
names = [c["collection"] for c in (d.get("data") or []) if c["collection"].startswith("dam")]
print("dam collections:", names or "NONE")

print("== 6. org 2 website ==")
st, d = req("/items/organizations/2?fields=id,name,website,service_status")
print(d.get("data"))

print("== 7. client-token probes ==")
st, d = req("/auth/login", "POST", {"email": CLIENT_EMAIL, "password": CLIENT_PASS}, token="")
ctok = ((d.get("data") or {}).get("access_token")) if st == 200 else None
print("client login:", st, "token=", "obtained" if ctok else "FAILED", d.get("errors"))
if ctok:
    st, d = req("/users/me?fields=id,email,role.name", token=ctok)
    print("/users/me:", st, (d.get("data") or {}).get("email"), ((d.get("data") or {}).get("role") or {}).get("name"))

    # messages list, exact route shape (threads route LIST_FIELDS)
    params = urllib.parse.urlencode({
        "sort": "-last_message_at", "limit": "200",
        "fields": ("id,subject,status,last_message_at,team_last_read_at,client_last_read_at,is_test_data,"
                   "organization.id,organization.name,organization.service_status,"
                   "messages.body,messages.author_role,messages.date_created"),
        "deep[messages][_sort]": "-date_created",
        "deep[messages][_limit]": "1",
        "filter[organization][_eq]": "2",
    })
    st, d = req("/items/os_message_threads?" + params, token=ctok)
    rows = d.get("data") or []
    print("client threads read: status=%s rows=%d errors=%s" % (st, len(rows), json.dumps(d.get("errors"))[:200]))
    for r in rows[:3]:
        lm = (r.get("messages") or [{}])[0]
        print("  ", r["subject"], "| last:", str(lm.get("body"))[:60])

    # kb spaces, exact route filter for clients
    flt = json.dumps({"_and": [{"status": {"_eq": "published"}},
                               {"min_role": {"_in": ["client"]}},
                               {"is_client_visible": {"_eq": True}}]})
    st, d = req("/items/kb_spaces?fields=id,name,slug,min_role,is_client_visible&filter=" + urllib.parse.quote(flt), token=ctok)
    print("client kb_spaces read: status=%s rows=%s" % (st, [r["slug"] for r in (d.get("data") or [])]))
    flt2 = json.dumps({"_and": [{"status": {"_eq": "published"}}, {"min_role": {"_in": ["client"]}}]})
    st, d = req("/items/kb_pages?aggregate[count]=id&groupBy[]=space&filter=" + urllib.parse.quote(flt2), token=ctok)
    print("client kb_pages counts: status=%s data=%s" % (st, json.dumps(d.get("data"))[:300]))

    # org website via GraphQL, email panel shape
    q = {"query": "query($id: GraphQLStringOrFloat!){ organizations(filter:{id:{_eq:$id}}, limit:1){ id website } }",
         "variables": {"id": 2}}
    st, d = req("/graphql", "POST", q, token=ctok)
    print("client org website gql:", st, json.dumps(d)[:200])

    # brand-assets: what the client token sees for dam_assets (expect missing-collection error)
    st, d = req("/items/dam_assets?limit=1", token=ctok)
    print("client dam_assets read: status=%s errors=%s" % (st, json.dumps(d.get("errors"))[:200]))
