#!/usr/bin/env python3
"""Gap-fix diagnostics for invoices/packages/services/personal. Prints counts and demo ids only."""
import json, os, urllib.request, urllib.error

def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

ENV = load_env()
BASE = "https://cms.musterr.dev"
TOKEN = ENV["DIRECTUS_ADMIN_TOKEN"]

def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, None

# 1. collection existence
st, data = req("/collections?limit=-1")
cols = {c["collection"] for c in data["data"]}
targets = ["packages", "services", "reminders", "personal_inbox", "studio_projects",
           "studio_publish_targets", "media_galleries", "os_invoices", "os_invoice_items"]
print("== collection existence ==")
for t in targets:
    print(f"  {t}: {'EXISTS' if t in cols else 'MISSING'}")

# 2. os_invoices state
st, data = req("/items/os_invoices?limit=-1&fields=id,invoice_number,billing_type,subscription_status,status,issue_date&sort=issue_date")
rows = data["data"]
print(f"\n== os_invoices ({len(rows)} rows) ==")
combos = {}
for r in rows:
    key = (r.get("billing_type"), r.get("subscription_status"), r.get("status"))
    combos[key] = combos.get(key, 0) + 1
for k, v in sorted(combos.items(), key=lambda x: str(x)):
    print(f"  billing_type={k[0]} sub_status={k[1]} status={k[2]}: {v}")

# recurring/fixed_term rows detail
rec = [r for r in rows if r.get("billing_type") in ("recurring", "fixed_term")]
print(f"  recurring/fixed_term rows: {len(rec)}")
for r in rec:
    print(f"    {r['id']} {r.get('invoice_number')} bt={r.get('billing_type')} ss={r.get('subscription_status')} st={r.get('status')}")

# 3. line item coverage
st, data = req("/items/os_invoice_items?limit=-1&fields=id,invoice")
items = data["data"]
by_inv = {}
for it in items:
    by_inv[it["invoice"]] = by_inv.get(it["invoice"], 0) + 1
no_items = [r["id"] for r in rows if r["id"] not in by_inv]
print(f"\n== os_invoice_items: {len(items)} rows across {len(by_inv)} invoices ==")
print(f"  invoices WITHOUT line items: {len(no_items)}")
for i in no_items:
    print(f"    {i}")

# 4. os_tasks fields + personal rows
st, data = req("/fields/os_tasks")
tf = [f["field"] for f in data["data"]]
print(f"\n== os_tasks has workspace: {'workspace' in tf} ==")
st, data = req("/items/os_tasks?limit=-1&fields=id,name,priority,due_date,status,workspace&filter[workspace][_eq]=personal")
if data and data.get("data") is not None:
    for r in data["data"]:
        print(f"  {r['id']} pr={r.get('priority')} due={r.get('due_date')} st={r.get('status')} | {r.get('name')}")
else:
    print("  personal filter failed:", st)

# 5. os_projects fields
st, data = req("/fields/os_projects")
pf = [f["field"] for f in data["data"]]
print(f"\n== os_projects has workspace: {'workspace' in pf} ==")

# 6. demo policy permissions
POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
st, data = req(f"/permissions?filter[policy][_eq]={POLICY}&limit=-1&fields=id,collection,action")
perms = data["data"]
reads = sorted(p["collection"] for p in perms if p["action"] == "read")
print(f"\n== demo policy read grants ({len(reads)}) ==")
print("  " + ", ".join(reads))

# 7. row counts in target collections if they exist
for t in ["packages", "services", "reminders", "personal_inbox", "studio_projects", "studio_publish_targets"]:
    if t in cols:
        st, data = req(f"/items/{t}?aggregate[count]=*")
        n = data["data"][0]["count"] if st == 200 else f"ERR {st}"
        print(f"  rows in {t}: {n}")
