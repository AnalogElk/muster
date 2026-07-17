#!/usr/bin/env python3
"""Second pre-probe: products route shape, retainer projects, enum choices,
invoice amount consistency, org-2 contacts/projects, files for attachments."""
import json, os, urllib.request, urllib.parse

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

# products route exact field list (employee/client shape)
flds = ("id,name,slug,status,description,delivered_date,contract_end_date,access_url,assets,"
        "organization.id,organization.name,source_project.id,source_project.name,"
        "maintained_by.id,maintained_by.name,date_created,date_updated")
st, d = req(f"/items/os_products?fields={urllib.parse.quote(flds)}&filter[organization][_eq]=2&limit=5")
out["products_route_shape"] = st
out["products_org2_rows"] = [
    {"name": p["name"], "status": p["status"], "maintained_by": p.get("maintained_by")}
    for p in d.get("data", [])] if st == 200 else d.get("errors")

# relation check
st, d = req("/relations/os_products/maintained_by")
out["maintained_by_relation"] = d.get("data", {}).get("related_collection") if st == 200 else f"HTTP {st}"

# retainer projects
st, d = req("/items/os_projects?filter[kind][_eq]=retainer&fields=id,name,organization&limit=-1")
out["retainer_projects"] = d.get("data", []) if st == 200 else f"HTTP {st}"

# org-2 projects + contacts (live)
st, d = req("/items/os_projects?filter[organization][_eq]=2&fields=id,name,status,kind&limit=-1")
out["org2_projects"] = d.get("data", [])
st, d = req("/items/organizations_contacts?filter[organizations_id][_eq]=2&fields=contacts_id&limit=-1")
cids = [str(r["contacts_id"]) for r in d.get("data", [])]
out["org2_contact_ids"] = cids
if cids:
    st, d = req(f"/items/contacts?filter[id][_in]={','.join(cids)}&fields=id,first_name,last_name,email")
    out["org2_contacts"] = d.get("data", [])

# enum choices
for coll, fld in [("os_invoice_items", "type"), ("os_payments", "status"),
                  ("os_payments", "payment_method_type"), ("os_tasks", "responsibility"),
                  ("os_tasks", "type"), ("os_products", "status")]:
    st, d = req(f"/fields/{coll}/{fld}")
    ch = ((d.get("data", {}).get("meta") or {}).get("options") or {}).get("choices")
    out[f"choices_{coll}_{fld}"] = [c.get("value") for c in ch] if ch else None

# invoice amount consistency + per-invoice item sums
st, d = req("/items/os_invoices?fields=id,invoice_number,status,subtotal,total,total_tax,amount_due,amount_paid,organization,contact,project&limit=-1")
invs = d.get("data", [])
st, d = req("/items/os_invoice_items?fields=invoice,line_amount&limit=-1")
sums = {}
for it in d.get("data", []):
    k = str(it.get("invoice"))
    sums[k] = sums.get(k, 0.0) + float(it.get("line_amount") or 0)
bad = []
for i in invs:
    total = float(i.get("total") or 0)
    paid = i.get("amount_paid")
    due = i.get("amount_due")
    isum = round(sums.get(str(i["id"]), 0.0), 2)
    row = {"id": i["id"], "num": i.get("invoice_number"), "status": i["status"],
           "total": total, "paid": paid, "due": due, "item_sum": isum,
           "subtotal": i.get("subtotal"), "tax": i.get("total_tax"),
           "contact": bool(i.get("contact")), "project": bool(i.get("project")), "org": i.get("organization")}
    issues = []
    if i["status"] == "paid" and (paid is None or float(paid or 0) != total or float(due or 0) != 0):
        issues.append("paid_inconsistent")
    if i["status"] != "paid" and due is None:
        issues.append("due_null")
    if isum == 0:
        issues.append("no_items")
    sub = i.get("subtotal")
    if sub is not None and abs(isum - float(sub)) > 0.01 and isum > 0:
        issues.append("items_ne_subtotal")
    if not i.get("contact"): issues.append("no_contact")
    if not i.get("project"): issues.append("no_project")
    if issues:
        row["issues"] = issues
        bad.append(row)
out["invoice_issues_count"] = len(bad)
out["invoice_issues"] = bad

# files available for task attachments
st, d = req("/files?fields=id,title,type&limit=-1")
out["files"] = [{"id": f["id"], "title": f.get("title"), "type": f.get("type")} for f in d.get("data", [])][:40]

# comments existing on org2 tasks (dedupe key check)
st, d = req("/comments?filter[collection][_eq]=os_tasks&fields=id,item,comment&limit=-1")
out["comments_total"] = len(d.get("data", [])) if st == 200 else f"HTTP {st}"

print(json.dumps(out, indent=1, default=str))
