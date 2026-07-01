#!/usr/bin/env python3
"""
Re-create the Knowledge Base collections (kb_spaces + kb_pages) on a box whose
schema was pruned, seed real Muster content, and grant the demo read-only policy
READ access so demo@muster.dev can browse /employee-portal/kb.

Why this exists: the P2 schema prune dropped kb_spaces/kb_pages from the sellable
core, but the portal's /employee-portal/kb section queries them
(app/api/portal/kb/*). Without the collections the KB renders an error/empty
state. This restores them from a bundled snapshot (provision/seed/kb-schema.json,
extracted from the prod CMS) and seeds provision/seed/kb-pages.json.

Idempotent: safe to re-run. Collections/fields/relation are created only if
absent; pages are upserted by slug; permissions are reconciled.

Usage:
    DIRECTUS_ADMIN_TOKEN=... \\
    DIRECTUS_URL=https://cms.<box>.sslip.io \\
    POLICY_NAME="Demo Read-Only" \\
        python3 provision/re-add-kb.py
"""
import os, sys, json, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.environ.get("DIRECTUS_URL", "https://cms.34.220.64.149.sslip.io").rstrip("/")
TOKEN = os.environ["DIRECTUS_ADMIN_TOKEN"]
POLICY_NAME = os.environ.get("POLICY_NAME", "Demo Read-Only")


def req(method, path, body=None):
    url = B + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def collection_exists(name):
    s, _ = req("GET", "/collections/" + name)
    return s == 200


def create_collection(payload, skip_fields=()):
    name = payload["collection"]
    if collection_exists(name):
        print("  collection exists:", name)
        return
    fields = [f for f in payload["fields"] if f["field"] not in skip_fields]
    body = {
        "collection": name,
        "meta": payload.get("meta") or {},
        "schema": payload.get("schema") or {},
        "fields": fields,
    }
    s, r = req("POST", "/collections", body)
    if s >= 300:
        print("  COLLECTION CREATE FAIL", name, s, json.dumps(r)[:400])
        sys.exit(1)
    print("  collection created:", name, "with", len(fields), "fields")


def field_exists(coll, field):
    s, _ = req("GET", "/fields/%s/%s" % (coll, field))
    return s == 200


def add_field(coll, field_payload):
    field = field_payload["field"]
    if field_exists(coll, field):
        print("  field exists:", coll, field)
        return
    s, r = req("POST", "/fields/" + coll, field_payload)
    if s >= 300:
        print("  FIELD CREATE FAIL", coll, field, s, json.dumps(r)[:400])
        sys.exit(1)
    print("  field created:", coll, field)


def relation_exists(coll, field):
    s, r = req("GET", "/relations/%s/%s" % (coll, field))
    return s == 200


def add_relation(rel):
    coll, field = rel["collection"], rel["field"]
    if relation_exists(coll, field):
        print("  relation exists:", coll, field)
        return
    body = {
        "collection": coll,
        "field": field,
        "related_collection": rel["related_collection"],
        "meta": rel.get("meta") or {},
        "schema": rel.get("schema") or {"on_delete": "SET NULL"},
    }
    s, r = req("POST", "/relations", body)
    if s >= 300:
        print("  RELATION CREATE FAIL", coll, field, s, json.dumps(r)[:400])
        sys.exit(1)
    print("  relation created:", coll, "->", rel["related_collection"])


def upsert_by_slug(collection, row):
    slug = row["slug"]
    s, r = req("GET", "/items/%s?filter[slug][_eq]=%s&fields=id&limit=1" % (collection, slug))
    existing = (r.get("data") or []) if s == 200 else []
    if existing:
        rid = existing[0]["id"]
        req("PATCH", "/items/%s/%s" % (collection, rid), row)
        print("  updated %s: %s" % (collection, slug))
        return rid
    s, r = req("POST", "/items/" + collection, row)
    if s >= 300:
        print("  ITEM CREATE FAIL", collection, slug, s, json.dumps(r)[:400])
        sys.exit(1)
    rid = r["data"]["id"]
    print("  created %s: %s" % (collection, slug))
    return rid


def grant_read(policy_id, collection):
    s, r = req("GET", "/permissions?filter[policy][_eq]=%s&filter[collection][_eq]=%s&filter[action][_eq]=read&fields=id&limit=1" % (policy_id, collection))
    if s == 200 and (r.get("data") or []):
        print("  read perm exists:", collection)
        return
    s, r = req("POST", "/permissions", {
        "policy": policy_id, "collection": collection, "action": "read",
        "fields": ["*"], "permissions": {}, "validation": {},
    })
    if s >= 300:
        print("  PERM CREATE FAIL", collection, s, json.dumps(r)[:300])
        sys.exit(1)
    print("  read perm granted:", collection)


def main():
    schema = json.load(open(os.path.join(HERE, "seed", "kb-schema.json")))
    content = json.load(open(os.path.join(HERE, "seed", "kb-pages.json")))

    print("== 1. collections ==")
    create_collection(schema["kb_spaces"])
    # create kb_pages WITHOUT the m2o `space` field; add it + relation after.
    create_collection(schema["kb_pages"], skip_fields=("space",))

    print("== 2. space field + relation ==")
    space_field = next(f for f in schema["kb_pages"]["fields"] if f["field"] == "space")
    add_field("kb_pages", space_field)
    for rel in schema.get("_relations", []):
        add_relation(rel)

    print("== 3. seed content ==")
    space_id = upsert_by_slug("kb_spaces", content["space"])
    for page in content["pages"]:
        row = dict(page)
        row["space"] = space_id
        upsert_by_slug("kb_pages", row)

    print("== 4. grant demo read-only policy READ on KB ==")
    s, pols = req("GET", "/policies?fields=id,name&filter[name][_eq]=" + POLICY_NAME.replace(" ", "%20"))
    if s == 200 and (pols.get("data") or []):
        policy_id = pols["data"][0]["id"]
        grant_read(policy_id, "kb_spaces")
        grant_read(policy_id, "kb_pages")
    else:
        print("  WARN: policy %r not found; run demo-readonly-role.py to grant read." % POLICY_NAME)

    print("DONE")


if __name__ == "__main__":
    main()
