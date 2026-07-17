#!/usr/bin/env python3
"""Pre-fix probe for the 4 client-portal gap sections (tasks, invoices,
products, analytics). Prints counts/ids/names only, never secrets."""
import json, os, urllib.request, urllib.parse

def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env

ENV = load_env()
BASE = "https://cms.musterr.dev"
TOKEN = ENV["DIRECTUS_ADMIN_TOKEN"]

def req(path, method="GET", body=None):
    r = urllib.request.Request(
        BASE + path, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

out = {}

# 1. Client demo session plumbing
st, d = req("/roles?filter[name][_eq]=Client&fields=id,name")
out["client_role"] = d.get("data", [])
st, d = req("/users?filter[email][_eq]=client%40muster.dev&fields=id,role,status")
out["client_user"] = d.get("data", [])
st, d = req("/items/contacts?filter[email][_eq]=client%40muster.dev&fields=id,user,organizations")
out["client_contact"] = d.get("data", [])
st, d = req("/items/organizations/2?fields=id,name,matomo_site_id,client_portal_enabled,portal_feeds")
out["org2"] = d.get("data", {})

# 2. Tasks visible to the client (project.organization == 2)
st, d = req("/items/os_tasks?filter[project][organization][_eq]=2&filter[is_visible_to_client][_eq]=true"
            "&fields=id,name,status,priority,due_date,assigned_to,project.id,project.name&limit=-1")
rows = d.get("data", [])
out["org2_client_tasks_count"] = len(rows)
out["org2_client_tasks_status"] = {}
out["org2_client_tasks_priority"] = {}
out["org2_tasks_missing_due"] = 0
out["org2_tasks_missing_assignee"] = 0
ids = []
for t in rows:
    ids.append(t["id"])
    out["org2_client_tasks_status"][t.get("status")] = out["org2_client_tasks_status"].get(t.get("status"), 0) + 1
    out["org2_client_tasks_priority"][str(t.get("priority"))] = out["org2_client_tasks_priority"].get(str(t.get("priority")), 0) + 1
    if not t.get("due_date"): out["org2_tasks_missing_due"] += 1
    if not t.get("assigned_to"): out["org2_tasks_missing_assignee"] += 1
out["org2_task_sample"] = [{"id": t["id"], "name": t["name"], "status": t["status"], "prio": t["priority"]} for t in rows[:5]]

# detail extras on those tasks
if ids:
    idlist = ",".join(ids[:80])
    st, d = req(f"/comments?filter[collection][_eq]=os_tasks&filter[item][_in]={idlist}&aggregate[count]=*")
    out["comments_on_org2_tasks"] = d.get("data", [{}])[0].get("count") if st == 200 else f"HTTP {st}"
    st, d = req(f"/items/os_task_files?filter[os_tasks_id][_in]={idlist}&aggregate[count]=*")
    out["taskfiles_on_org2_tasks"] = d.get("data", [{}])[0].get("count") if st == 200 else f"HTTP {st}"
    st, d = req(f"/items/os_activity_log?filter[target_collection][_eq]=os_tasks&filter[target_id][_in]={idlist}&aggregate[count]=*")
    out["activity_on_org2_tasks"] = d.get("data", [{}])[0].get("count") if st == 200 else f"HTTP {st}"

# 3. Invoices: items per invoice, contact/project m2o, payments
st, d = req("/items/os_invoices?fields=id,invoice_number,status,total,amount_due,amount_paid,contact,project,organization&limit=-1")
invs = d.get("data", [])
out["invoices_total"] = len(invs)
out["invoices_missing_contact"] = sum(1 for i in invs if not i.get("contact"))
out["invoices_missing_project"] = sum(1 for i in invs if not i.get("project"))
out["invoices_status"] = {}
for i in invs:
    out["invoices_status"][i.get("status")] = out["invoices_status"].get(i.get("status"), 0) + 1
out["org2_invoices"] = [i["id"] for i in invs if str(i.get("organization")) == "2"]
st, d = req("/items/os_invoice_items?fields=invoice&limit=-1")
items = d.get("data", [])
per = {}
for it in items:
    per[str(it.get("invoice"))] = per.get(str(it.get("invoice")), 0) + 1
out["invoice_items_total"] = len(items)
out["invoices_with_zero_items"] = sum(1 for i in invs if str(i["id"]) not in per)
out["items_per_invoice_min_max"] = [min(per.values()) if per else 0, max(per.values()) if per else 0]
st, d = req("/items/os_payments?fields=id,invoice,amount,status,stripe_payment_id&limit=-1")
pays = d.get("data", [])
out["payments_total"] = len(pays)
paid_ids = {str(i["id"]) for i in invs if i.get("status") == "paid"}
out["paid_invoices"] = len(paid_ids)
out["paid_invoices_without_payment"] = len(paid_ids - {str(p.get("invoice")) for p in pays})

# 4. Products
st, d = req("/fields/os_products")
fields = [f["field"] for f in d.get("data", [])] if st == 200 else []
out["os_products_has_maintained_by"] = "maintained_by" in fields
st, d = req("/items/os_products?fields=id,name,status,organization,delivered_date,access_url,assets,description,source_project&limit=-1")
prods = d.get("data", [])
out["products_total"] = len(prods)
out["products_org2"] = sum(1 for p in prods if str(p.get("organization")) == "2")
out["products_sample"] = [{"id": p["id"], "name": p["name"], "status": p["status"], "org": p.get("organization"),
                           "has_assets": bool(p.get("assets")), "has_url": bool(p.get("access_url")),
                           "delivered": p.get("delivered_date")} for p in prods]

# 5. Analytics
st, d = req("/collections/analytics_snapshots")
out["analytics_snapshots_collection"] = ("exists" if st == 200 else f"HTTP {st}")
st, d = req("/items/analytics_snapshots?fields=id,matomo_site_id,range_key,collected_at,organization&limit=-1")
snaps = d.get("data", []) if st == 200 else []
out["analytics_snapshots_rows"] = [{"site": s["matomo_site_id"], "range": s["range_key"], "at": s["collected_at"]} for s in snaps]
st, d = req("/items/os_seo_snapshots?fields=id,organization,url,collected_at&limit=-1")
seos = d.get("data", []) if st == 200 else []
out["seo_snapshots_total"] = len(seos)
out["seo_snapshots_org2"] = sum(1 for s in seos if str(s.get("organization")) == "2")

# 6. Demo policy permissions on collections the client flows read
st, d = req("/roles?filter[name][_eq]=Client&fields=id")
role_id = d["data"][0]["id"] if d.get("data") else None
policy_ids = []
if role_id:
    st, d = req(f"/access?filter[role][_eq]={role_id}&fields=policy")
    policy_ids = [a["policy"] for a in d.get("data", [])]
out["client_policies"] = policy_ids
perm_colls = ["directus_comments", "os_tasks", "os_task_files", "os_activity_log", "os_invoices",
              "os_invoice_items", "os_payments", "os_products", "organizations", "organization_emails",
              "organizations_contacts", "contacts", "os_projects", "analytics_snapshots", "os_seo_snapshots"]
out["policy_read_grants"] = {}
for pid in policy_ids:
    st, d = req(f"/permissions?filter[policy][_eq]={pid}&filter[action][_eq]=read&fields=collection&limit=-1")
    got = sorted({p["collection"] for p in d.get("data", [])})
    out["policy_read_grants"][pid] = [c for c in perm_colls if c in got]
    out["policy_read_missing"] = [c for c in perm_colls if c not in got]

print(json.dumps(out, indent=1, default=str))
