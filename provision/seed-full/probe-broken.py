#!/usr/bin/env python3
"""Read-only GraphQL probes proving each missing-field finding breaks the
portal's exact query shape on the live demo Directus. Admin token, no writes,
no secret output."""
import json
import os
import urllib.request
import urllib.error

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


def gql(query):
    body = json.dumps({"query": query}).encode()
    r = urllib.request.Request(
        BASE + "/graphql", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + TOKEN})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, None


PROBES = {
    "sprints_burndown (lib/portal/services/sprints.ts:180)": """
      query { os_sprints(limit: 1) {
        start_date end_date
        tasks { points }
        snapshots(sort: ["snapshot_date"]) { snapshot_date remaining_points }
      } }""",
    "invoice_checkout (app/api/portal/invoices/checkout/route.ts:46)": """
      query { os_invoices(limit: 1) {
        id invoice_number status total amount_due payment_deadline
      } }""",
    "invoice_subscribe (app/api/portal/invoices/subscribe/route.ts:51)": """
      query { os_invoices(limit: 1) {
        id invoice_number billing_type term_months
      } }""",
    "repository_detail (app/api/portal/repositories/[id]/route.ts:69)": """
      query { repositories(limit: 1) {
        id name url platform default_branch description is_private status
        date_created date_updated
        project_id { id name }
      } }""",
    "control_sprints_without_aliases": """
      query { os_sprints(limit: 1) { id name status start_date end_date } }""",
    "control_invoices_without_new_fields": """
      query { os_invoices(limit: 1) { id invoice_number status total } }""",
    "control_repositories_without_dates": """
      query { repositories(limit: 1) {
        id name url platform default_branch description is_private status
        project_id { id name }
      } }""",
}

out = {}
for name, q in PROBES.items():
    status, payload = gql(q)
    errors = (payload or {}).get("errors") or []
    out[name] = {
        "http": status,
        "ok": status == 200 and not errors,
        "errors": [e.get("message") for e in errors][:4],
        "rows": (len(next(iter(((payload or {}).get("data") or {}).values()), []))
                 if status == 200 and not errors and (payload or {}).get("data")
                 else None),
    }
print("PROBE_JSON_BEGIN")
print(json.dumps(out, indent=1))
print("PROBE_JSON_END")
