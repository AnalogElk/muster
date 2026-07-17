#!/usr/bin/env python3
"""Pre-rebuild probe: services default_rate, invoices term_months, org2 website,
infra_snapshots shape, analytics_snapshots freshness. Prints demo content only."""
import json
import os
import urllib.request

BASE = "https://cms.musterr.dev"


def load_env():
    env = {}
    path = os.path.join(os.path.expanduser("~"), "elk-os", ".env")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def get(path):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# 1. services: name + default_rate + pricing_type
rows = get("/items/services?fields=name,default_rate,unit_cost,pricing_type,status&limit=20")["data"]
print("services:", len(rows))
for r in rows[:12]:
    print("  ", r["name"], "| default_rate:", r.get("default_rate"), "| pricing:", r.get("pricing_type"), "|", r.get("status"))

# 2. fixed_term invoices term_months
rows = get("/items/os_invoices?filter[billing_type][_eq]=fixed_term&fields=invoice_number,term_months&limit=25")["data"]
print("fixed_term invoices:", len(rows), "with term_months set:", sum(1 for r in rows if r.get("term_months")))

# 3. org 2 website
r = get("/items/organizations/2?fields=name,website,matomo_site_id")["data"]
print("org2:", r)

# 4. infra_snapshots newest row shape (keys only) + count
rows = get("/items/infra_snapshots?sort=-collected_at&limit=1")["data"]
allrows = get("/items/infra_snapshots?aggregate[count]=*")["data"]
print("infra_snapshots count:", allrows)
if rows:
    r0 = rows[0]
    print("infra_snapshot keys:", sorted(r0.keys()))
    print("  collected_at:", r0.get("collected_at"), "summary_date:", r0.get("summary_date") if "summary_date" in r0 else "(n/a)")

# 5. analytics_snapshots freshness
rows = get("/items/analytics_snapshots?sort=-collected_at&limit=3&fields=site_id,range_key,collected_at")["data"]
print("analytics_snapshots newest:", rows)

# 6. one org logo file id for the pixel proof
rows = get("/items/organizations?fields=id,name,logo&filter[logo][_nnull]=true&limit=3")["data"]
print("orgs with logo:", rows)
