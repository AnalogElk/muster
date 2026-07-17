#!/usr/bin/env python3
"""Drift + permissions audit against the LIVE Muster demo Directus.

READ-ONLY: only GET requests with the admin token, one POST /auth/login with
the public demo credentials, and POST /graphql queries (reads). No writes.

Job 1: for every GraphQL document the frozen portal ships (gql-docs.json,
parsed locally from lib/portal + app/api/portal), resolve relations against
live /relations and report every queried field missing from live
/fields/<collection>.

Job 2: identify the demo user's role/policy and list every portal-queried
collection the demo policy cannot read (both by /permissions reconstruction
and by empirical per-collection reads with a demo session token).

Output: one JSON blob between AUDIT_JSON_BEGIN / AUDIT_JSON_END markers.
Never prints the admin token or any env value.
"""
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


def req(path, token=None, method="GET", body=None):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = None
        return e.code, payload
    except Exception as e:  # noqa: BLE001
        return -1, {"error": str(e)}


SP = os.path.dirname(os.path.abspath(__file__))
DOCS = json.load(open(os.path.join(SP, "gql-docs.json")))["documents"]

REST_COLLECTIONS = [
    "contacts", "dam_assets", "dam_assets_collections", "dam_collections",
    "dam_guideline_blocks", "dam_guidelines", "dam_render_jobs",
    "dam_share_links", "help_articles", "help_collections", "infra_snapshots",
    "kb_pages", "kb_spaces", "organization_addresses", "organizations",
    "os_activities", "os_activity_log", "os_ai_commits", "os_client_assets",
    "os_client_ticket_responses", "os_client_tickets", "os_deal_stages",
    "os_deals", "os_deliverable_decisions", "os_deliverables", "os_expenses",
    "os_insights", "os_invoice_items", "os_invoices", "os_message_threads",
    "os_messages", "os_notifications", "os_payments", "os_products",
    "os_project_subscriptions", "os_project_updates", "os_projects",
    "os_proposals", "os_seo_snapshots", "os_settings", "os_sprint_snapshots",
    "os_sprints", "os_subscriptions", "os_task_files", "os_tasks",
    "os_token_usage", "os_view_as_sessions", "packages", "personal_inbox",
    "project_links", "releases", "reminders", "repositories", "services",
    "signage_devices", "studio_media_refs", "studio_projects",
    "studio_publish_targets", "tools",
]

# ---------------------------------------------------------------- relations

status, rel_payload = req("/relations", TOKEN)
assert status == 200, f"/relations -> {status}"
m2o = {}
o2m = {}
for rel in rel_payload["data"]:
    many_c = rel.get("collection")
    many_f = rel.get("field")
    one_c = rel.get("related_collection")
    meta = rel.get("meta") or {}
    if many_c and many_f and one_c:
        m2o[(many_c, many_f)] = one_c
    one_field = meta.get("one_field")
    if one_c and one_field and many_c:
        o2m[(one_c, one_field)] = many_c

status, coll_payload = req("/collections", TOKEN)
assert status == 200, f"/collections -> {status}"
live_collections = {c["collection"] for c in coll_payload["data"]}

# ------------------------------------------------------------ walk gql docs

AGG_FNS = {"count", "countDistinct", "sum", "sumDistinct", "avg",
           "avgDistinct", "min", "max"}
AGG_SKIP = {"group", "countAll", "__typename"}

queried = {}          # coll -> field -> set(sources)
unresolved_rel = []   # (coll, field, source)


def add(coll, field, source):
    queried.setdefault(coll, {}).setdefault(field, set()).add(source)


def walk(coll, node, source, agg=False):
    f = node["f"]
    if f == "__typename":
        return
    sel = node.get("sel")
    if agg:
        if f in AGG_SKIP:
            return
        if f in AGG_FNS:
            for c in sel or []:
                walk(coll, c, source, agg=False)
            return
    add(coll, f, source)
    if sel is None:
        return
    child = m2o.get((coll, f)) or o2m.get((coll, f))
    if child is None:
        unresolved_rel.append([coll, f, source])
        return
    for c in sel:
        walk(child, c, source)


def root_collection(name):
    if name.endswith("_aggregated"):
        return name[: -len("_aggregated")], True
    if name.endswith("_by_id"):
        return name[: -len("_by_id")], False
    return name, False


for doc in DOCS:
    for r in doc["roots"]:
        coll, agg = root_collection(r["f"])
        for c in r.get("sel", []):
            walk(coll, c, doc["source"], agg=agg)

# ------------------------------------------------------------- fields diff

live_fields = {}
missing_collections = []
for coll in sorted(queried):
    status, payload = req(f"/fields/{coll}", TOKEN)
    if status != 200:
        missing_collections.append({"collection": coll, "status": status})
        live_fields[coll] = None
        continue
    live_fields[coll] = {f["field"]: (f.get("type") or "")
                         for f in payload["data"]}

missing_fields = []
for coll in sorted(queried):
    fields = live_fields.get(coll)
    if fields is None:
        continue
    for f in sorted(queried[coll]):
        if f not in fields:
            missing_fields.append({
                "collection": coll,
                "field": f,
                "sources": sorted(queried[coll][f]),
            })

# ------------------------------------------- GraphQL fragment-shape probes


def serialize(nodes, indent=0):
    out = []
    pad = " " * indent
    for n in nodes:
        if n.get("sel"):
            out.append(pad + n["f"] + " {")
            out.append(serialize(n["sel"], indent + 2))
            out.append(pad + "}")
        else:
            out.append(pad + n["f"])
    return "\n".join(out)


fragment_probes = []
for doc in DOCS:
    if doc.get("op") != "fragment":
        continue
    coll = doc["fragment_collection"]
    body = serialize(doc["roots"][0].get("sel", []), 4)
    q = "query { %s(limit: 1) {\n%s\n} }" % (coll, body)
    status, payload = req("/graphql", TOKEN, method="POST", body={"query": q})
    errors = (payload or {}).get("errors")
    fragment_probes.append({
        "fragment": doc["source"].split("#")[-1],
        "collection": coll,
        "http": status,
        "ok": status == 200 and not errors,
        "errors": [e.get("message") for e in errors][:6] if errors else [],
    })

# ------------------------------------------------------------- permissions

status, users = req(
    "/users?filter[email][_eq]=demo@muster.dev&fields=id,email,status,role",
    TOKEN)
demo_user = (users or {}).get("data", [])
demo_user = demo_user[0] if demo_user else None
role_id = demo_user["role"] if demo_user else None
role_name = None
if role_id:
    status, role = req(f"/roles/{role_id}?fields=id,name", TOKEN)
    role_name = ((role or {}).get("data") or {}).get("name")

policies = {}
if demo_user:
    for flt in (f"filter[role][_eq]={role_id}",
                f"filter[user][_eq]={demo_user['id']}"):
        status, acc = req(
            f"/access?{flt}&fields=id,policy.id,policy.name,"
            "policy.admin_access,policy.app_access", TOKEN)
        for row in ((acc or {}).get("data") or []):
            p = row.get("policy") or {}
            if p.get("id"):
                policies[p["id"]] = p

perm_reads = {}   # collection -> list of policy names granting read
policy_perm_counts = {}
if policies:
    ids = ",".join(policies)
    status, perms = req(
        f"/permissions?filter[policy][_in]={ids}&limit=-1"
        "&fields=collection,action,policy", TOKEN)
    for row in ((perms or {}).get("data") or []):
        pol = row.get("policy")
        policy_perm_counts[pol] = policy_perm_counts.get(pol, 0) + 1
        if row.get("action") == "read":
            perm_reads.setdefault(row["collection"], []).append(pol)

# ---------------------------------------------- empirical demo-token reads

status, login = req("/auth/login", method="POST",
                    body={"email": "demo@muster.dev",
                          "password": "muster-demo"})
demo_token = ((login or {}).get("data") or {}).get("access_token")
demo_login_ok = status == 200 and bool(demo_token)

gql_collections = [c for c in sorted(queried)
                   if not c.startswith("directus_")]
all_portal_collections = sorted(set(REST_COLLECTIONS) | set(gql_collections))

empirical = {}
if demo_token:
    for coll in all_portal_collections:
        st, payload = req(f"/items/{coll}?limit=1&fields=id", demo_token)
        empirical[coll] = st
    for sysname, path in (("directus_users", "/users?limit=1&fields=id"),
                          ("directus_files", "/files?limit=1&fields=id")):
        st, payload = req(path, demo_token)
        empirical[sysname] = st

unreadable = []
for coll in all_portal_collections:
    has_policy_read = coll in perm_reads
    emp = empirical.get(coll)
    if not has_policy_read or (emp is not None and emp == 403):
        unreadable.append({
            "collection": coll,
            "policy_read": has_policy_read,
            "demo_get_status": emp,
            "exists_on_live": coll in live_collections,
            "queried_via": ("graphql" if coll in queried else "") +
                           ("+rest" if coll in REST_COLLECTIONS else ""),
        })

result = {
    "live_collection_count": len(live_collections),
    "gql_documents": len(DOCS),
    "queried_collections": {c: len(queried[c]) for c in sorted(queried)},
    "missing_collections": missing_collections,
    "missing_fields": missing_fields,
    "unresolved_relations": sorted({tuple(x[:2]) for x in unresolved_rel}),
    "fragment_probes": fragment_probes,
    "demo_user": {"found": bool(demo_user),
                  "id": demo_user["id"] if demo_user else None,
                  "status": demo_user.get("status") if demo_user else None},
    "demo_role": {"id": role_id, "name": role_name},
    "demo_policies": [{"id": pid, "name": p.get("name"),
                       "admin_access": p.get("admin_access"),
                       "app_access": p.get("app_access"),
                       "permission_rows": policy_perm_counts.get(pid, 0)}
                      for pid, p in policies.items()],
    "demo_login_ok": demo_login_ok,
    "empirical_reads": empirical,
    "unreadable_by_demo": unreadable,
}
print("AUDIT_JSON_BEGIN")
print(json.dumps(result, indent=1, default=list))
print("AUDIT_JSON_END")
