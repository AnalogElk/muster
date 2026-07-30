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
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client.directus_client import call, load_env  # noqa: E402

BASE = "https://cms.musterr.dev"


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(method, path, params=None, body=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    st, raw, err = call(method, url, data=data, headers=headers, timeout=None)
    if err is not None:
        raise err
    return json.loads(raw)


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
