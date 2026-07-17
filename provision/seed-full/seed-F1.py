#!/usr/bin/env python3
"""seed-F1.py - foundation schema patches for the Muster demo (cms.musterr.dev).

Additive ONLY: POST /fields for missing fields, POST /relations for two new m2o
relations, one optional additive PATCH to a single demo-policy permission row
(fields append, logged before/after). Never deletes, never changes types.
Idempotent: every POST is preceded by an existence GET; re-running is safe.

Run on the box: python3 ~/elk-os/provision/seed-full/seed-F1.py
Reads DIRECTUS_ADMIN_TOKEN from ~/elk-os/.env inside this script; never prints it.
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://cms.musterr.dev"
DEMO_POLICY = "c69b84d1-8957-4687-a6dd-b049b3e890b9"
DEMO_EMAIL = "demo@muster.dev"       # public demo creds shown on the landing page
DEMO_PASSWORD = "muster-demo"        # NOT a secret


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


def req(method, path, payload=None, token=TOKEN, raw_url=None):
    """Return (status, parsed_json_or_None). Never raises on HTTP errors."""
    url = raw_url or (BASE + path)
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=45) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = None
        return e.code, parsed
    except Exception as e:
        return 0, {"errors": [{"message": f"transport: {e.__class__.__name__}: {e}"}]}


report = {"fields": [], "relations": [], "permission_patches": [],
          "relation_one_field_checks": [], "demo_probes": [], "graphql": []}


# ---------------------------------------------------------------- field specs
def fld(field, ftype, interface=None, special=None, schema="default", note=""):
    meta = {}
    if interface:
        meta["interface"] = interface
    if special:
        meta["special"] = special
    payload = {"field": field, "type": ftype, "meta": meta or None}
    if schema == "default":
        payload["schema"] = {"is_nullable": True}
    elif schema is not None:
        payload["schema"] = schema
    else:
        payload["schema"] = None
    return payload


FIELD_SPECS = [
    # (1)(2) os_invoices
    ("os_invoices", fld("payment_deadline", "date", "datetime")),
    ("os_invoices", fld("term_months", "integer", "input")),
    # (3)(4) os_sprints o2m alias rows (relations already exist with one_field set)
    ("os_sprints", fld("tasks", "alias", "list-o2m", ["o2m"], schema=None)),
    ("os_sprints", fld("snapshots", "alias", "list-o2m", ["o2m"], schema=None)),
    # (5)(6) repositories timestamps
    ("repositories", fld("date_created", "timestamp", "datetime", ["date-created"])),
    ("repositories", fld("date_updated", "timestamp", "datetime", ["date-updated"])),
    # (7) os_token_usage nine fields
    ("os_token_usage", fld("project_label", "string", "input")),
    ("os_token_usage", fld("input_tokens", "bigInteger", "input")),
    ("os_token_usage", fld("output_tokens", "bigInteger", "input")),
    ("os_token_usage", fld("cache_write_tokens", "bigInteger", "input")),
    ("os_token_usage", fld("cache_read_tokens", "bigInteger", "input")),
    ("os_token_usage", fld("total_tokens", "bigInteger", "input")),
    ("os_token_usage", fld("est_cost_usd", "decimal", "input",
                           schema={"is_nullable": True,
                                   "numeric_precision": 10, "numeric_scale": 4})),
    ("os_token_usage", fld("model_breakdown", "json", "input-code")),
    ("os_token_usage", fld("last_synced", "timestamp", "datetime")),
    # (8) os_activity_log.organization (org PK is INT)
    ("os_activity_log", fld("organization", "integer",
                            "select-dropdown-m2o", ["m2o"])),
    # (9) os_products.maintained_by m2o -> os_projects
    ("os_products", fld("maintained_by", "uuid",
                        "select-dropdown-m2o", ["m2o"])),
    # (10) os_tasks.workspace
    ("os_tasks", fld("workspace", "string", "input")),
]

RELATION_SPECS = [
    {"collection": "os_activity_log", "field": "organization",
     "related_collection": "organizations",
     "schema": {"on_delete": "SET NULL"}},
    {"collection": "os_products", "field": "maintained_by",
     "related_collection": "os_projects",
     "schema": {"on_delete": "SET NULL"}},
]

# o2m alias sanity checks: relation must already carry meta.one_field
ONE_FIELD_EXPECT = [
    ("os_tasks", "sprint", "tasks"),
    ("os_sprint_snapshots", "sprint", "snapshots"),
]


def main():
    created = skipped = failed = 0

    # 0. verify the o2m relations really carry one_field as the plan asserts
    for coll, field, expect in ONE_FIELD_EXPECT:
        st, body = req("GET", f"/relations/{coll}/{field}")
        one_field = None
        if st == 200 and body and body.get("data"):
            one_field = (body["data"].get("meta") or {}).get("one_field")
        entry = {"relation": f"{coll}.{field}", "expected_one_field": expect,
                 "actual_one_field": one_field, "status": st}
        if one_field == expect:
            entry["result"] = "ok"
        else:
            entry["result"] = "MISMATCH: alias field will not resolve; not patching relations"
        report["relation_one_field_checks"].append(entry)
        print(f"relation-check {coll}.{field}: one_field={one_field!r} "
              f"(expected {expect!r}) -> {entry['result']}")

    # 1. additive fields
    for coll, payload in FIELD_SPECS:
        name = payload["field"]
        st, _ = req("GET", f"/fields/{coll}/{name}")
        if st == 200:
            skipped += 1
            report["fields"].append({"collection": coll, "field": name,
                                     "result": "skipped (exists)"})
            print(f"field {coll}.{name}: skipped (exists)")
            continue
        st, body = req("POST", f"/fields/{coll}", payload)
        if st in (200, 201):
            created += 1
            report["fields"].append({"collection": coll, "field": name,
                                     "result": "created"})
            print(f"field {coll}.{name}: created")
        else:
            failed += 1
            err = json.dumps((body or {}).get("errors", body))[:300]
            report["fields"].append({"collection": coll, "field": name,
                                     "result": f"FAILED {st}", "error": err})
            print(f"field {coll}.{name}: FAILED {st} {err}")
    print(f"fields: created {created} / updated 0 / skipped {skipped} / failed {failed}")

    # 2. relations for the two new m2o fields
    r_created = r_skipped = r_failed = 0
    for spec in RELATION_SPECS:
        coll, name = spec["collection"], spec["field"]
        st, _ = req("GET", f"/relations/{coll}/{name}")
        if st == 200:
            r_skipped += 1
            report["relations"].append({"relation": f"{coll}.{name}",
                                        "result": "skipped (exists)"})
            print(f"relation {coll}.{name}: skipped (exists)")
            continue
        st, body = req("POST", "/relations", spec)
        if st in (200, 201):
            r_created += 1
            report["relations"].append({"relation": f"{coll}.{name}",
                                        "result": "created"})
            print(f"relation {coll}.{name}: created")
        else:
            r_failed += 1
            err = json.dumps((body or {}).get("errors", body))[:300]
            report["relations"].append({"relation": f"{coll}.{name}",
                                        "result": f"FAILED {st}", "error": err})
            print(f"relation {coll}.{name}: FAILED {st} {err}")
    print(f"relations: created {r_created} / updated 0 / skipped {r_skipped} / failed {r_failed}")

    # 3. demo-policy read verification of the NEW fields
    st, body = req("POST", "/auth/login",
                   {"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, token=None)
    demo_token = None
    if st == 200 and body:
        demo_token = body["data"]["access_token"]
        print("demo login: ok")
    else:
        print(f"demo login: FAILED {st}")
        report["demo_probes"].append({"probe": "auth/login", "status": st,
                                      "result": "FAILED"})

    probes = [
        ("os_token_usage", "/items/os_token_usage?fields=project_label,est_cost_usd&limit=1",
         ["project_label", "est_cost_usd"]),
        ("os_activity_log", "/items/os_activity_log?fields=organization.id&limit=1",
         ["organization"]),
        ("os_products", "/items/os_products?fields=maintained_by.id&limit=1",
         ["maintained_by"]),
        ("os_tasks", "/items/os_tasks?fields=workspace&limit=1", ["workspace"]),
        ("repositories", "/items/repositories?fields=date_created&limit=1",
         ["date_created"]),
    ]

    def run_probe(path):
        return req("GET", path, token=demo_token)

    if demo_token:
        for coll, path, new_fields in probes:
            st, body = run_probe(path)
            entry = {"collection": coll, "probe": path, "status": st}
            if st == 200:
                entry["result"] = "ok"
                report["demo_probes"].append(entry)
                print(f"demo probe {coll}: 200 ok")
                continue
            if st != 403:
                entry["result"] = f"FAILED {st} (not a permission shape, not patching)"
                entry["error"] = json.dumps((body or {}).get("errors", body))[:300]
                report["demo_probes"].append(entry)
                print(f"demo probe {coll}: FAILED {st}")
                continue
            # 403: inspect the ONE demo-policy read permission row for this collection
            pst, pbody = req("GET",
                             "/permissions?filter[policy][_eq]=" + DEMO_POLICY +
                             f"&filter[collection][_eq]={coll}"
                             "&filter[action][_eq]=read&limit=5")
            rows = (pbody or {}).get("data") or []
            if pst != 200 or len(rows) != 1:
                entry["result"] = (f"403 but permission lookup returned {len(rows)} rows "
                                   f"(status {pst}); not patching")
                report["demo_probes"].append(entry)
                print(f"demo probe {coll}: 403, ambiguous permission rows, not patched")
                continue
            row = rows[0]
            before = row.get("fields")
            patch_entry = {"permission_id": row["id"], "collection": coll,
                           "before_fields": before}
            if before is None or before == "*" or before == ["*"] or (
                    isinstance(before, list) and "*" in before):
                patch_entry["after_fields"] = before
                patch_entry["result"] = "no-op (fields is wildcard, nothing to append)"
                report["permission_patches"].append(patch_entry)
                entry["result"] = "403 with wildcard fields; no-op, see permission_patches"
                report["demo_probes"].append(entry)
                print(f"demo probe {coll}: 403 but permission fields is wildcard; no-op")
                continue
            after = list(before) + [f for f in new_fields if f not in before]
            if after == list(before):
                patch_entry["after_fields"] = before
                patch_entry["result"] = "no-op (fields already listed)"
                report["permission_patches"].append(patch_entry)
                entry["result"] = "403 but fields already listed; not a fields problem"
                report["demo_probes"].append(entry)
                print(f"demo probe {coll}: 403, fields already present, not patched")
                continue
            ust, ubody = req("PATCH", f"/permissions/{row['id']}", {"fields": after})
            patch_entry["after_fields"] = after
            patch_entry["result"] = f"PATCH {ust}"
            report["permission_patches"].append(patch_entry)
            print(f"permission row {row['id']} ({coll}): BEFORE fields={json.dumps(before)} "
                  f"AFTER fields={json.dumps(after)} (PATCH {ust})")
            st2, _ = run_probe(path)
            entry["result"] = f"retry after permission append: {st2}"
            report["demo_probes"].append(entry)
            print(f"demo probe {coll}: retry -> {st2}")

    # 4. GraphQL verification (admin token) with a short retry for schema cache
    queries = [
        ("sprints_o2m",
         "query { os_sprints(limit:2){ id name tasks { points } "
         "snapshots { snapshot_date remaining_points } } }"),
        ("new_scalars",
         "query { os_invoices(limit:1){ id term_months payment_deadline } "
         "repositories(limit:1){ id date_created date_updated } "
         "os_token_usage(limit:1){ id est_cost_usd } }"),
    ]
    for name, q in queries:
        ok = False
        last = None
        for attempt in range(4):
            st, body = req("POST", "/graphql", {"query": q})
            last = {"status": st, "errors": (body or {}).get("errors"),
                    "data": (body or {}).get("data")}
            if st == 200 and body and not body.get("errors"):
                ok = True
                break
            time.sleep(5)
        report["graphql"].append({"probe": name, "ok": ok, **(last or {})})
        print(f"graphql {name}: {'OK' if ok else 'FAILED'} "
              f"{json.dumps(last)[:500]}")

    print("=== F1 REPORT ===")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
