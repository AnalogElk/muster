#!/usr/bin/env python3
"""Run-2 final gap-fix: null-fill os_invoices.billing_interval='month' on
recurring invoices where it is null, so the client invoices TYPE column reads
'Monthly' instead of blank (client-invoices-list.tsx getIntervalLabel).

NULLFILL authorized by Mike 2026-07-16 (RUN 2 ADDENDUM full auto).
Only-when-null guard: never overwrites a non-null billing_interval.
Idempotent: second run finds nothing to fill. Never prints the token.
"""
import json
import os
import urllib.request
import urllib.parse

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


def req(method, path, params=None, body=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(r) as resp:
        return json.load(resp)


rows = req("GET", "/items/os_invoices", {
    "filter": json.dumps({
        "billing_type": {"_eq": "recurring"},
        "billing_interval": {"_null": True},
    }),
    "fields": "id,invoice_number,status,billing_interval",
    "limit": "-1",
})["data"]

patched = 0
for inv in rows:
    req("PATCH", "/items/os_invoices/" + inv["id"], body={"billing_interval": "month"})
    patched += 1
    print("NULLFILLED:", inv.get("invoice_number"), "billing_interval -> month")

print(f"os_invoices.billing_interval null-fill: patched {patched} / candidates {len(rows)}")
