#!/usr/bin/env python3
"""Gap-fix verification probes, run AS THE DEMO USER (public demo creds).

Replicates the portal's exact query shapes:
  1. GraphQL GetPortalInvoices with INVOICE_FIELDS; recompute the Active
     Subscriptions KPI exactly as the invoices page does.
  2. GraphQL GetPortalPackages with PACKAGE_FIELDS.
  3. GraphQL GetPortalServices with SERVICE_FIELDS.
  4. REST reminders / personal_inbox / studio_projects / os_tasks personal,
     same params as lib/personal services.
Prints counts, names, and bucket splits only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cms.musterr.dev"

# Public demo creds (shown on the landing page; not a secret)
body = json.dumps({"email": "demo@muster.dev", "password": "muster-demo"}).encode()
r = urllib.request.Request(BASE + "/auth/login", data=body, method="POST",
                           headers={"Content-Type": "application/json"})
with urllib.request.urlopen(r, timeout=30) as resp:
    TOKEN = json.load(resp)["data"]["access_token"]
print("demo login: OK")

def gql(query):
    data = json.dumps({"query": query}).encode()
    r = urllib.request.Request(BASE + "/graphql", data=data, method="POST",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return json.load(e)

def rest(path):
    r = urllib.request.Request(BASE + path,
        headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, None

# 1. invoices KPI
INVOICE_FIELDS = """
    id invoice_number status total amount_due amount_paid due_date issue_date
    billing_type billing_interval subscription_status stripe_subscription_id
    line_items { id item_name quantity unit_price line_amount }
    organization { id name }
"""
res = gql("query GetPortalInvoices { os_invoices(sort: [\"-issue_date\"], limit: 50) {" + INVOICE_FIELDS + "} }")
if res.get("errors"):
    print("INVOICES GQL ERRORS:", [e["message"] for e in res["errors"]][:3])
else:
    invs = res["data"]["os_invoices"]
    active = [i for i in invs if i.get("subscription_status") == "active"
              and i.get("billing_type") in ("recurring", "fixed_term")]
    no_items = [i["invoice_number"] for i in invs if not i.get("line_items")]
    print(f"invoices: {len(invs)} rows; Active Subscriptions KPI = {len(active)}")
    print(f"  active subs: {sorted(i['invoice_number'] for i in active)}")
    print(f"  invoices without line items: {no_items or 'none'}")

# 2. packages
res = gql("query GetPortalPackages { packages(limit: 100, sort: [\"name\"]) { id name description price status type billing_cycle hours_included overage_rate support_hours } }")
if res.get("errors"):
    print("PACKAGES GQL ERRORS:", [e["message"] for e in res["errors"]][:3])
else:
    rows = res["data"]["packages"]
    print(f"packages: {len(rows)} rows")
    for p in rows:
        print(f"  {p['name']}: ${p['price']} {p['status']} {p['billing_cycle']}")

# 3. services
res = gql("query GetPortalServices { services(limit: 100, sort: [\"sort\", \"name\"]) { id name title description default_rate unit_cost pricing_type category status sort } }")
if res.get("errors"):
    print("SERVICES GQL ERRORS:", [e["message"] for e in res["errors"]][:3])
else:
    rows = res["data"]["services"]
    print(f"services: {len(rows)} rows")
    for p in rows:
        print(f"  {p['name']}: rate {p['default_rate']} {p['pricing_type']} {p['status']}")

# 4. personal surfaces (REST, same params as lib/personal)
FIELDS_R = "id,caldav_uid,list_name,title,due_at,is_completed,priority,source,sync_state"
st, data = rest(f"/items/reminders?fields={FIELDS_R}&limit=200&sort=due_at"
                "&filter[sync_state][_neq]=orphaned&filter[is_completed][_eq]=false")
if st != 200:
    print(f"reminders REST: HTTP {st}")
else:
    rows = data["data"]
    today = "2026-07-16"
    buckets = {"overdue": 0, "today": 0, "upcoming": 0, "someday": 0}
    for r_ in rows:
        d = r_.get("due_at")
        if not d:
            buckets["someday"] += 1
        elif d[:10] < today:
            buckets["overdue"] += 1
        elif d[:10] == today:
            buckets["today"] += 1
        else:
            buckets["upcoming"] += 1
    print(f"reminders (demo REST): {len(rows)} rows, buckets ~ {buckets} (UTC approx of PT split)")

st, data = rest("/items/personal_inbox?fields=id,subject,source,triage_status&limit=100"
                "&sort=-date_created&filter[triage_status][_eq]=pending")
print(f"personal_inbox pending (demo REST): HTTP {st}, rows {len(data['data']) if st==200 else 'n/a'}")

SF = urllib.parse.quote("id,discipline,pipeline_stage,project.id,project.name,"
                        "publish_targets.id,publish_targets.target,publish_targets.status")
st, data = rest(f"/items/studio_projects?fields={SF}&limit=100")
if st != 200:
    print(f"studio_projects REST: HTTP {st}")
else:
    rows = data["data"]
    print(f"studio_projects (demo REST): {len(rows)} rows")
    for r_ in rows:
        pname = (r_.get("project") or {}).get("name")
        tgts = r_.get("publish_targets") or []
        print(f"  {pname}: {r_['discipline']}/{r_['pipeline_stage']} targets={len(tgts)}")

st, data = rest("/items/os_tasks?fields=id,name,priority,due_date,status&limit=200"
                "&sort=due_date&filter[workspace][_eq]=personal&filter[status][_neq]=completed")
if st != 200:
    print(f"personal tasks REST: HTTP {st}")
else:
    rows = data["data"]
    prios = {}
    for r_ in rows:
        prios[r_.get("priority")] = prios.get(r_.get("priority"), 0) + 1
    print(f"personal os_tasks (demo REST): {len(rows)} rows, priorities {prios}")
