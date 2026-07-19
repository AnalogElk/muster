#!/usr/bin/env python3
"""run2-P1-probe: live state probe for run 2 work package P1 (data patches + nullfill + polish).

Read-only. Prints counts/ids/names only; never prints the token.
"""
import json
import os
import urllib.parse
import urllib.request


def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


BASE = "https://cms.musterr.dev"
TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


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


def get(col, params):
    q = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()})
    st, out = req("GET", "/items/%s?%s" % (col, q))
    if st != 200:
        print("PROBE FAIL %s: %s %s" % (col, st, out))
        return []
    return out.get("data", [])


print("== os_settings singleton ==")
st, out = req("GET", "/items/os_settings")
print(st, json.dumps(out.get("data", out), default=str)[:300])

print("\n== invoice numbers (max) ==")
rows = get("os_invoices", {"fields": "invoice_number", "limit": -1})
nums = []
for r in rows:
    n = (r.get("invoice_number") or "")
    if n.startswith("INV-"):
        try:
            nums.append(int(n.rsplit("-", 1)[1]))
        except ValueError:
            pass
print("count=%d max_suffix=%s" % (len(rows), max(nums) if nums else None))

print("\n== os_proposals (all) ==")
rows = get("os_proposals", {"fields": "id,name,status,total,expiration_date,organization,deal,date_created", "limit": -1, "sort": "date_created"})
for r in rows:
    print(" ", r["id"][:8], r.get("status"), r.get("organization"), (r.get("name") or "")[:48], r.get("total"), r.get("expiration_date"))
print("proposal_count=%d" % len(rows))

print("\n== os_proposals status field choices ==")
st, out = req("GET", "/fields/os_proposals/status")
if st == 200:
    meta = out.get("data", {}).get("meta") or {}
    print(json.dumps((meta.get("options") or {}).get("choices"), default=str))

print("\n== one proposal line_items sample ==")
rows = get("os_proposals", {"fields": "id,name,line_items", "limit": 2, "filter": {"line_items": {"_nnull": True}}})
for r in rows:
    print(" ", r["id"][:8], json.dumps(r.get("line_items"), default=str)[:400])

print("\n== os_expenses status spread ==")
rows = get("os_expenses", {"fields": "status", "limit": -1})
spread = {}
for r in rows:
    spread[r.get("status")] = spread.get(r.get("status"), 0) + 1
print("count=%d spread=%s" % (len(rows), spread))
st, out = req("GET", "/fields/os_expenses/status")
if st == 200:
    meta = out.get("data", {}).get("meta") or {}
    print("choices:", json.dumps((meta.get("options") or {}).get("choices"), default=str))

print("\n== repositories (descriptions + bloom pointer) ==")
rows = get("repositories", {"fields": "id,name,description,project_id,status", "limit": -1})
for r in rows:
    print(" ", r["id"][:8], r["name"], "proj=%s" % (r.get("project_id") or "null")[:8], "desc=%s" % ("NULL" if not r.get("description") else "set"))

print("\n== os_projects (budget_cap, ids of interest) ==")
rows = get("os_projects", {"fields": "id,name,organization,budget_cap,status,kind,workspace", "limit": -1})
for r in rows:
    print(" ", r["id"][:8], "org=%s" % r.get("organization"), (r.get("name") or "")[:44], "cap=%s" % r.get("budget_cap"), r.get("status"), r.get("workspace"))

print("\n== organizations 1-8 (name, logo) ==")
rows = get("organizations", {"fields": "id,name,logo", "limit": -1, "sort": "id"})
for r in rows:
    print(" ", r["id"], r.get("name"), "logo=%s" % ("NULL" if not r.get("logo") else str(r.get("logo"))[:8]))

print("\n== contacts 1-11 nullfill state ==")
rows = get("contacts", {"fields": "id,first_name,last_name,job_title,phone,contact_notes", "limit": -1, "filter": {"id": {"_lte": 11}}, "sort": "id"})
for r in rows:
    print(" ", r["id"], r.get("first_name"), "title=%s" % ("NULL" if not r.get("job_title") else "set"), "phone=%s" % ("NULL" if not r.get("phone") else "set"), "notes=%s" % ("NULL" if not r.get("contact_notes") else "set"))

print("\n== releases: Website Relaunch row ==")
rows = get("releases", {"fields": "id,title,version,release_date,repository_id,status,is_test_data", "limit": -1, "filter": {"title": {"_contains": "Website Relaunch"}}})
for r in rows:
    print(" ", json.dumps(r, default=str))

print("\n== infra_snapshots stripe payload ==")
rows = get("infra_snapshots", {"fields": "id,collected_at,payload", "limit": -1, "sort": "collected_at"})
print("rows=%d" % len(rows))
for r in rows:
    p = r.get("payload")
    kind = "str" if isinstance(p, str) else type(p).__name__
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = {}
    stripe = (p or {}).get("stripe") or {}
    print(" ", r["id"][:8], r.get("collected_at"), "payload_type=%s" % kind, "mrrUsd=%s subs=%s" % (stripe.get("mrrUsd"), stripe.get("activeSubscriptionCount")))

print("\n== deals for orgs 3,4,5 ==")
rows = get("os_deals", {"fields": "id,name,organization,deal_value,deal_stage", "limit": -1, "filter": {"organization": {"_in": [3, 4, 5]}}})
for r in rows:
    print(" ", r["id"][:8], "org=%s" % r.get("organization"), (r.get("name") or "")[:48], r.get("deal_value"))

print("\n== contacts for orgs 3,4,5 (via organizations_contacts) ==")
rows = get("organizations_contacts", {"fields": "organizations_id,contacts_id.id,contacts_id.first_name,contacts_id.last_name", "limit": -1, "filter": {"organizations_id": {"_in": [3, 4, 5]}}})
for r in rows:
    c = r.get("contacts_id") or {}
    print(" ", "org=%s" % r.get("organizations_id"), c.get("id"), c.get("first_name"), c.get("last_name"))

print("\nPROBE DONE")
