#!/usr/bin/env python3
"""Post-fix probe run AS THE CLIENT DEMO USER (client@muster.dev, public demo
creds) replicating the exact query shapes the four portal sections fire.
Prints counts/names only."""
import json, os, urllib.request, urllib.parse

BASE = "https://cms.musterr.dev"

def call(path, token=None, method="GET", body=None, raw_body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = raw_body or (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(BASE + path, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

out = {}

# login as the public client demo user
st, d = call("/auth/login", method="POST", body={"email": "client@muster.dev", "password": "muster-demo"})
if st != 200:
    raise SystemExit(f"FATAL client login failed: {st}")
CT = d["data"]["access_token"]
out["client_login"] = "ok"

# ── tasks: board fragment shape via GraphQL under the client token ──────────
gql = {"query": """
query {
  os_tasks(limit: 200, filter: {
    is_visible_to_client: {_eq: true},
    project: {organization: {id: {_eq: 2}}}
  }) {
    id name status type priority due_date is_visible_to_client
    assigned_to { id first_name last_name email }
    project { id name status organization { id name } }
  }
}"""}
st, d = call("/graphql", token=CT, method="POST", body=gql)
rows = (d.get("data") or {}).get("os_tasks") or []
out["tasks_gql_status"] = st
out["tasks_gql_errors"] = d.get("errors")
out["tasks_count"] = len(rows)
sts, prios = {}, {}
missing_due = missing_asg = 0
for t in rows:
    sts[t["status"]] = sts.get(t["status"], 0) + 1
    prios[str(t["priority"])] = prios.get(str(t["priority"]), 0) + 1
    if not t.get("due_date") and t["status"] != "completed":
        missing_due += 1
    if not t.get("assigned_to"):
        missing_asg += 1
out["tasks_status_spread"] = sts
out["tasks_priority_spread"] = prios
out["tasks_missing_due_noncompleted"] = missing_due
out["tasks_missing_assignee"] = missing_asg

# detail extras as client: comments + activity for one task
if rows:
    tid = rows[0]["id"]
    st, d = call(f"/comments?filter[collection][_eq]=os_tasks&filter[item][_eq]={tid}"
                 "&fields=id,comment,user_created.first_name&limit=5", token=CT)
    out["client_comments_read"] = {"status": st, "rows": len(d.get("data", [])) if st == 200 else d.get("errors")}
    st, d = call(f"/items/os_activity_log?filter[target_collection][_eq]=os_tasks"
                 f"&filter[target_id][_eq]={tid}&fields=id,verb&limit=5", token=CT)
    out["client_activity_read"] = {"status": st, "rows": len(d.get("data", [])) if st == 200 else d.get("errors")}
# total comments across org2 tasks (admin-free: client token, no item filter)
st, d = call("/comments?filter[collection][_eq]=os_tasks&aggregate[count]=*", token=CT)
out["client_comments_total_visible"] = d.get("data", [{}])[0].get("count") if st == 200 else f"HTTP {st}"

# ── invoices: INVOICE_FIELDS_CLIENT fragment via GraphQL under client token ─
gql = {"query": """
query {
  os_invoices(limit: 200, sort: ["-issue_date"]) {
    id invoice_number status reference total subtotal total_tax amount_due amount_paid
    due_date issue_date billing_type allow_partial_payments
    contact { id first_name last_name email }
    organization { id name }
    project { id name }
  }
}"""}
st, d = call("/graphql", token=CT, method="POST", body=gql)
invs = (d.get("data") or {}).get("os_invoices") or []
out["invoices_gql_status"] = st
out["invoices_gql_errors"] = d.get("errors")
org2 = [i for i in invs if i.get("organization") and str(i["organization"]["id"]) == "2"]
out["invoices_visible_total"] = len(invs)
out["invoices_org2"] = len(org2)
out["invoices_org2_missing_contact"] = sum(1 for i in org2 if not i.get("contact"))
out["invoices_org2_missing_project"] = sum(1 for i in org2 if not i.get("project"))
out["invoices_org2_status"] = {}
for i in org2:
    out["invoices_org2_status"][i["status"]] = out["invoices_org2_status"].get(i["status"], 0) + 1

# admin check: items per invoice + paid/payment consistency (all orgs)
env = {}
with open(os.path.expanduser("~/elk-os/.env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
AT = env["DIRECTUS_ADMIN_TOKEN"]
st, d = call("/items/os_invoices?fields=id,status,total,organization,contact,project&limit=-1", token=AT)
ainvs = d["data"]
st, d = call("/items/os_invoice_items?fields=invoice&limit=-1", token=AT)
per = {}
for it in d["data"]:
    per[str(it["invoice"])] = per.get(str(it["invoice"]), 0) + 1
st, d = call("/items/os_payments?fields=invoice,stripe_payment_id&limit=-1", token=AT)
paysby = {str(p["invoice"]) for p in d["data"]}
out["admin_invoices_zero_items"] = [str(i["id"]) for i in ainvs if str(i["id"]) not in per]
out["admin_paid_without_payment"] = [str(i["id"]) for i in ainvs
                                     if i["status"] == "paid" and str(i["id"]) not in paysby]
out["admin_missing_contact_nonorg1"] = [str(i["id"]) for i in ainvs
                                        if not i.get("contact") and str(i.get("organization")) != "1"]
out["admin_missing_project_nonorg1"] = [str(i["id"]) for i in ainvs
                                        if not i.get("project") and str(i.get("organization")) != "1"]

# ── products: exact route REST shape under the client token ────────────────
flds = ("id,name,slug,status,description,delivered_date,contract_end_date,access_url,assets,"
        "organization.id,organization.name,source_project.id,source_project.name,"
        "maintained_by.id,maintained_by.name,date_created,date_updated")
st, d = call(f"/items/os_products?fields={urllib.parse.quote(flds)}"
             "&filter[organization][_eq]=2&filter[is_test_data][_neq]=true"
             "&sort=-delivered_date,-date_created&limit=200", token=CT)
prods = d.get("data", []) if st == 200 else []
out["products_route_status"] = st
out["products_route_errors"] = d.get("errors")
out["products_org2"] = [{"name": p["name"], "status": p["status"],
                         "assets": len(p.get("assets") or []),
                         "maintained_by": (p.get("maintained_by") or {}).get("name")}
                        for p in prods]

# ── analytics: org site id readable by client + snapshot freshness ───────────
st, d = call("/items/organizations/2?fields=id,name,matomo_site_id", token=CT)
out["client_org2_matomo_site_id"] = {"status": st, "value": (d.get("data") or {}).get("matomo_site_id")}
st, d = call("/items/analytics_snapshots?filter[matomo_site_id][_eq]=2"
             "&fields=range_key,collected_at&limit=-1", token=AT)
out["site2_snapshots"] = d.get("data", [])
st, d = call("/items/os_seo_snapshots?filter[organization][_eq]=2&aggregate[count]=*", token=AT)
out["org2_seo_snapshots"] = d.get("data", [{}])[0].get("count")

print(json.dumps(out, indent=1, default=str))
