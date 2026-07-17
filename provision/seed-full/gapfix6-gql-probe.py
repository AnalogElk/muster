#!/usr/bin/env python3
"""GraphQL shape probe (admin token) for the gapfix6 rows. Token never renders."""
import json
import os
import urllib.request


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
q = """query {
  kb_spaces(filter:{slug:{_in:["cedar-project-docs","billing-and-payments"]}}) {
    slug name icon order min_role is_client_visible status
  }
  kb_pages(filter:{space:{slug:{_in:["cedar-project-docs","billing-and-payments"]}}}, sort:["order"], limit: 20) {
    slug title status min_role date_created
  }
  dam_assets(filter:{key:{_in:["dam/cedar-and-co-coffee/cedar-logo-cream.png","dam/cedar-and-co-coffee/cedar-wordmark-horizontal.png","dam/cedar-and-co-coffee/cedar-summer-web-banner.png"]}}) {
    key title status mime width height size_bytes date_created
    collections { dam_collections_id { slug } }
  }
}"""
r = urllib.request.Request(
    "https://cms.musterr.dev/graphql",
    data=json.dumps({"query": q}).encode(),
    headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
with urllib.request.urlopen(r, timeout=60) as resp:
    out = json.load(resp)
if out.get("errors"):
    print("ERRORS:", json.dumps(out["errors"])[:500])
    raise SystemExit(1)
d = out["data"]
print("kb_spaces:", json.dumps(d["kb_spaces"], indent=1))
print("kb_pages:", len(d["kb_pages"]), [p["slug"] for p in d["kb_pages"]])
for a in d["dam_assets"]:
    print("asset:", a["key"], a["status"], a["mime"], f'{a["width"]}x{a["height"]}',
          (a["date_created"] or "")[:10],
          "->", [c["dam_collections_id"]["slug"] for c in a["collections"]])
