#!/usr/bin/env python3
"""Evidence probe for the 4 gap-fix sections, run AFTER seeding.
GraphQL, portal fragment shapes, under the CLIENT USER'S OWN token
(the same token class the pages use). Prints counts and names only.
"""
import json
import os
import urllib.error
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


def req(path, method="GET", body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
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


# client demo creds are public landing-page tier, not a secret
st, d = req("/auth/login", "POST", {"email": "client@muster.dev", "password": "muster-demo"})
tok = (d.get("data") or {}).get("access_token")
print("client login:", st, "ok" if tok else "FAILED")

GQL = [
    ("messages", """query { os_message_threads(
        filter: { organization: { id: { _eq: 2 } } },
        sort: ["-last_message_at"], limit: 10) {
      id subject status last_message_at team_last_read_at client_last_read_at
      organization { id name service_status }
      messages(sort: ["-date_created"], limit: 1) { body author_role date_created }
    } }"""),
    ("kb", """query { kb_spaces(
        filter: { _and: [ { status: { _eq: "published" } },
                          { min_role: { _in: ["client"] } },
                          { is_client_visible: { _eq: true } } ] },
        sort: ["order"], limit: 10) { id name slug description icon min_role is_client_visible }
      kb_pages(filter: { _and: [ { status: { _eq: "published" } },
                                 { min_role: { _in: ["client"] } } ] },
               sort: ["order"], limit: 20) { id title slug min_role space { id slug } }
    }"""),
    ("email-org", """query { organizations(filter: { id: { _eq: 2 } }, limit: 1) { id website } }"""),
]
for name, qtext in GQL:
    st, d = req("/graphql", "POST", {"query": qtext}, token=tok)
    errs = d.get("errors")
    data = d.get("data") or {}
    summary = {}
    for k, v in data.items():
        if isinstance(v, list):
            summary[k] = len(v)
    print("[%s] status=%s errors=%s counts=%s" % (name, st, json.dumps(errs)[:180] if errs else None, summary))
    if name == "messages":
        for t in data.get("os_message_threads") or []:
            lm = (t.get("messages") or [{}])[0]
            print("   %-38s %-6s last=%s by=%s" % (t["subject"][:38], t["status"],
                  (t.get("last_message_at") or "")[:10], lm.get("author_role")))
    if name == "kb":
        for s in data.get("kb_spaces") or []:
            print("   space:", s["slug"], s["name"])
        for p in data.get("kb_pages") or []:
            print("   page:", p["slug"], "->", (p.get("space") or {}).get("slug"))
    if name == "email-org":
        print("   website:", (data.get("organizations") or [{}])[0].get("website"))

# brand-assets block evidence: dam_guidelines + dam_assets absent for ANY token
adm = load_env()["DIRECTUS_ADMIN_TOKEN"]
for coll in ("dam_guidelines", "dam_assets", "dam_collections"):
    st, d = req("/items/%s?limit=1" % coll, token=adm)
    msg = (d.get("errors") or [{}])[0].get("message", "")[:80]
    print("[brand-assets] admin read %s -> %s %s" % (coll, st, msg))
