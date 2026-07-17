#!/usr/bin/env python3
"""Print the newest infra_snapshots row's payload structure (keys and small
scalars only, demo data)."""
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


rows = get("/items/infra_snapshots?sort=-collected_at&limit=2")["data"]
for r in rows:
    print("id", r["id"], "collected_at", r["collected_at"], "aws_mtd", r["aws_mtd_cost_usd"],
          "neon_cost", r["neon_cost_usd"], "hc", r["hc_up"], "/", r["hc_total"])
p = rows[0].get("payload")
if isinstance(p, str):
    p = json.loads(p)


def walk(obj, prefix="", depth=0):
    if depth > 3:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}: {type(v).__name__}[{len(v)}]")
                walk(v, prefix + k + ".", depth + 1)
            else:
                sv = str(v)
                print(f"{prefix}{k} = {sv[:60]}")
    elif isinstance(obj, list) and obj:
        print(f"{prefix}[0]:")
        walk(obj[0], prefix + "[0].", depth + 1)


walk(p)
