#!/usr/bin/env python3
"""
Make a public demo user READ-ONLY while still resolving to the employee portal.

Context: a public demo login must NOT be an Administrator (admins bypass every
Directus policy and can always write). The portal's employee-vs-client check
(portal/.build/lib/portal/auth.ts -> resolveUserRole) treats any role whose
NAME lower-cases to "employee" as an employee, and unknown role names default
to "client". So the safe shape is a NON-admin role literally named "Employee"
carrying a read-only policy (app_access=FALSE, admin_access=false, READ-only
permissions). app_access must stay off: it grants Directus's built-in minimum
permissions, which include self-update of password/email/TFA — with the demo
credentials public, that is a one-request demo lockout. API login (which the
portal uses) does not require app access. This script creates that policy +
role, links them, and reassigns the demo user. Idempotent; re-runs also
reconcile the flags on an existing policy.

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
    # Reconcile flags on re-runs: earlier versions created this policy with
    # app_access=True, which lets the public demo user change their own
    # password/TFA via the built-in app-access minimum permissions. Force it off.
    req("PATCH", "/policies/" + policy_id,
        {"admin_access": False, "app_access": False})
    print("Policy exists (flags reconciled):", policy_id)
else:
    s, p = req("POST", "/policies", {
        "name": POLICY_NAME,
        "icon": "visibility",
        "description": "Public demo read-only access. No create/update/delete.",
        "admin_access": False,
        # app_access MUST stay False for a public demo: app access grants
        # Directus's built-in minimum permissions, which include UPDATE on the
        # user's own directus_users row (password, email, tfa_secret, ...).
        # With the demo credentials printed on the public site, app_access=True
        # would let any visitor change the demo password / enable TFA and lock
        # everyone else out. API login (/auth/login, used by the portal) does
        # not require app access — only the Data Studio does, and the Studio is
        # blocked at Caddy anyway. All reads the portal needs are granted
        # explicitly below.
        "app_access": False,
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
