#!/usr/bin/env python3
"""
Make a public demo user READ-ONLY while still resolving to the employee portal.

Context: a public demo login must NOT be an Administrator (admins bypass every
Directus policy and can always write). The portal's employee-vs-client check
(portal/.build/lib/portal/auth.ts -> resolveUserRole) treats any role whose
NAME lower-cases to "employee" as an employee, and unknown role names default
to "client". So the safe shape is a NON-admin role literally named "Employee"
carrying a read-only policy (app_access=true, admin_access=false, READ-only
permissions). This script creates that policy + role, links them, and reassigns
the demo user. Idempotent.

Usage:
    DIRECTUS_ADMIN_TOKEN=... \\
    DIRECTUS_URL=https://cms.<box>.sslip.io \\
    DEMO_EMAIL=demo@muster.dev \\
        python3 provision/demo-readonly-role.py
"""
import os, sys, json, urllib.request, urllib.error

B = os.environ.get("DIRECTUS_URL", "https://cms.34.220.64.149.sslip.io").rstrip("/")
TOKEN = os.environ["DIRECTUS_ADMIN_TOKEN"]
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@muster.dev")
ROLE_NAME = "Employee"
POLICY_NAME = "Demo Read-Only"

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

# 1. collections (non-system)
_, cols = req("GET", "/collections?limit=-1")
app_cols = sorted({c["collection"] for c in cols["data"]
                   if not c["collection"].startswith("directus_")
                   and c.get("schema") is not None})  # real tables only
print("APP COLLECTIONS:", len(app_cols))

# 2. find or create read-only policy
_, pols = req("GET", "/policies?fields=id,name&filter[name][_eq]=" + POLICY_NAME.replace(" ", "%20"))
if pols.get("data"):
    policy_id = pols["data"][0]["id"]
    print("Policy exists:", policy_id)
else:
    s, p = req("POST", "/policies", {
        "name": POLICY_NAME,
        "icon": "visibility",
        "description": "Public demo read-only access. No create/update/delete.",
        "admin_access": False,
        "app_access": True,
        "enforce_tfa": False,
    })
    if s >= 300:
        print("POLICY CREATE FAIL", s, p); sys.exit(1)
    policy_id = p["data"]["id"]
    print("Policy created:", policy_id)

# 3. find or create role "Employee"
_, roles = req("GET", "/roles?fields=id,name&filter[name][_eq]=" + ROLE_NAME)
if roles.get("data"):
    role_id = roles["data"][0]["id"]
    print("Role exists:", role_id)
else:
    s, r = req("POST", "/roles", {"name": ROLE_NAME, "icon": "badge",
                                  "description": "Demo employee (read-only)."})
    if s >= 300:
        print("ROLE CREATE FAIL", s, r); sys.exit(1)
    role_id = r["data"]["id"]
    print("Role created:", role_id)

# 4. link role <-> policy via directus_access
_, acc = req("GET", "/access?fields=id,role,policy&filter[role][_eq]=%s&filter[policy][_eq]=%s" % (role_id, policy_id))
if acc.get("data"):
    print("Access link exists")
else:
    s, a = req("POST", "/access", {"role": role_id, "policy": policy_id, "sort": 1})
    if s >= 300:
        print("ACCESS LINK FAIL", s, a); sys.exit(1)
    print("Access link created")

# 5. wipe any existing permissions for this policy, then create read-only ones
_, existing = req("GET", "/permissions?fields=id&filter[policy][_eq]=%s&limit=-1" % policy_id)
ids = [p["id"] for p in existing.get("data", [])]
if ids:
    req("DELETE", "/permissions", ids)
    print("Cleared", len(ids), "old permissions")

perms = []
for col in app_cols:
    perms.append({"policy": policy_id, "collection": col, "action": "read",
                  "fields": ["*"], "permissions": {}, "validation": {}})
# system collections the portal reads
perms.append({"policy": policy_id, "collection": "directus_users", "action": "read",
              "fields": ["*"], "permissions": {"id": {"_eq": "$CURRENT_USER"}}, "validation": {}})
perms.append({"policy": policy_id, "collection": "directus_roles", "action": "read",
              "fields": ["*"], "permissions": {}, "validation": {}})
perms.append({"policy": policy_id, "collection": "directus_files", "action": "read",
              "fields": ["*"], "permissions": {}, "validation": {}})
s, pr = req("POST", "/permissions", perms)
if s >= 300:
    print("PERMS CREATE FAIL", s, json.dumps(pr)[:500]); sys.exit(1)
print("Created", len(perms), "read permissions (read-only)")

# 6. reassign demo user to Employee role
_, u = req("GET", "/users?filter[email][_eq]=%s&fields=id,role.id,role.name" % DEMO_EMAIL)
demo = u["data"][0]
print("Demo user current role:", demo["role"])
s, _ = req("PATCH", "/users/%s" % demo["id"], {"role": role_id})
if s >= 300:
    print("USER REASSIGN FAIL", s); sys.exit(1)
print("Demo user reassigned to Employee role:", role_id)
print("DONE")
