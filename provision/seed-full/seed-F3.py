#!/usr/bin/env python3
"""seed-F3: foundation-people for the Muster demo.

  1. Upsert 6 fictional team directus_users by email (role Employee, status active).
     Passwords generated in-process with secrets.token_urlsafe(24); never printed or stored.
     NOTE: spec asked for @muster.example emails; Directus user email validation (Joi,
     IANA TLD list) rejects the reserved .example TLD, so team users use @team.musterr.dev.
  2. Initials-SVG avatars into the Avatars folder (name-upsert), PATCH user.avatar.
  3. [GATED: NULLFILL_APPROVED] null-fill enrichment of existing contacts 1-11.
     Default: SKIP and report each skipped item.
  4. Upsert ~15 new contacts by email on the real org domains.
  5. Upsert organizations_contacts junction rows by (organizations_id, contacts_id).
  6. Ensure demo policy has read-only grants on contacts/organizations_contacts/organizations
     (additive only; creates nothing if grants exist).

Add-only, idempotent, is_test_data false on every content row. Never touches the
demo user 257a4b75-deff-476d-953d-1898c57f6684 or admin 34d67d59-16c3-41c4-9efb-7fd51a216460.
"""
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import uuid

def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

ENV = load_env()
BASE = os.environ.get("DIRECTUS_URL", "https://cms.musterr.dev").rstrip("/")
TOKEN = ENV["DIRECTUS_ADMIN_TOKEN"]

EMPLOYEE_ROLE = "d5ddc27a-f6e7-4102-a885-1faa4ea1f40e"
PROTECTED_USERS = {"257a4b75-deff-476d-953d-1898c57f6684",
                   "34d67d59-16c3-41c4-9efb-7fd51a216460"}

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Authorization": "Bearer " + TOKEN,
                                        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        raise RuntimeError("%s %s -> HTTP %s: %s" % (method, path, e.code, detail))

def get(path):
    return req("GET", path)

def multipart_upload(title, filename, svg_text, folder_id):
    boundary = "----seedF3" + uuid.uuid4().hex
    parts = []
    def field(name, value):
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, name, value)).encode())
    field("title", title)
    field("folder", folder_id)
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: image/svg+xml\r\n\r\n" % (boundary, filename)).encode())
    parts.append(svg_text.encode())
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    body = b"".join(parts)
    r = urllib.request.Request(BASE + "/files", data=body, method="POST",
                               headers={"Authorization": "Bearer " + TOKEN,
                                        "Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read())["data"]["id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError("POST /files -> HTTP %s: %s" % (e.code, e.read().decode()[:500]))

def avatar_svg(initials, color):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
            'viewBox="0 0 256 256"><rect width="256" height="256" fill="%s"/>'
            '<text x="128" y="138" font-family="Arial, Helvetica, sans-serif" '
            'font-size="104" font-weight="700" fill="#FFFFFF" text-anchor="middle" '
            'dominant-baseline="middle">%s</text></svg>' % (color, initials))

# ------------------------------------------------------------------ step 1: users
TEAM = [
    {"first_name": "Mara",  "last_name": "Lindqvist", "email": "mara.lindqvist@team.musterr.dev",
     "title": "Design Lead",       "location": "Portland, OR", "initials": "ML", "color": "#D1495B"},
    {"first_name": "Devon", "last_name": "Okafor",    "email": "devon.okafor@team.musterr.dev",
     "title": "Senior Engineer",   "location": "Austin, TX",   "initials": "DO", "color": "#00798C"},
    {"first_name": "Elena", "last_name": "Vasquez",   "email": "elena.vasquez@team.musterr.dev",
     "title": "Project Manager",   "location": "Chicago, IL",  "initials": "EV", "color": "#6A4C93"},
    {"first_name": "Tom",   "last_name": "Beckett",   "email": "tom.beckett@team.musterr.dev",
     "title": "Frontend Engineer", "location": "Denver, CO",   "initials": "TB", "color": "#1982C4"},
    {"first_name": "Aisha", "last_name": "Karim",     "email": "aisha.karim@team.musterr.dev",
     "title": "SEO Strategist",    "location": "Seattle, WA",  "initials": "AK", "color": "#C05299"},
    {"first_name": "Felix", "last_name": "Anders",    "email": "felix.anders@team.musterr.dev",
     "title": "Account Manager",   "location": "Brooklyn, NY", "initials": "FA", "color": "#388659"},
]

user_fields = {f["field"] for f in get("/fields/directus_users")["data"]}
HAS_TITLE = "title" in user_fields
HAS_LOCATION = "location" in user_fields
print("directus_users field probe: title=%s location=%s" % (HAS_TITLE, HAS_LOCATION))

email_to_id = {}
u_created = u_updated = u_skipped = 0
for m in TEAM:
    q = urllib.parse.quote(m["email"])
    rows = get("/users?filter[email][_eq]=" + q + "&limit=1&fields=id,email,avatar,role"
               + (",title" if HAS_TITLE else "") + (",location" if HAS_LOCATION else ""))["data"]
    if rows:
        u = rows[0]
        if u["id"] in PROTECTED_USERS:
            u_skipped += 1
            continue
        email_to_id[m["email"]] = u["id"]
        m["_avatar"] = u.get("avatar")
        patch = {}
        if HAS_TITLE and not u.get("title"):
            patch["title"] = m["title"]
        if HAS_LOCATION and not u.get("location"):
            patch["location"] = m["location"]
        if patch:
            req("PATCH", "/users/" + u["id"], patch)
            u_updated += 1
        else:
            u_skipped += 1
    else:
        body = {"first_name": m["first_name"], "last_name": m["last_name"],
                "email": m["email"], "password": secrets.token_urlsafe(24),
                "role": EMPLOYEE_ROLE, "status": "active"}
        if HAS_TITLE:
            body["title"] = m["title"]
        if HAS_LOCATION:
            body["location"] = m["location"]
        new = req("POST", "/users", body)["data"]
        email_to_id[m["email"]] = new["id"]
        m["_avatar"] = None
        u_created += 1
print("directus_users: created %d / updated %d / skipped %d" % (u_created, u_updated, u_skipped))

# ------------------------------------------------------------------ step 2: avatars
rows = get("/folders?filter[name][_eq]=Avatars&limit=1")["data"]
if rows:
    avatars_folder = rows[0]["id"]
    print("directus_folders: created 0 / updated 0 / skipped 1 (Avatars exists)")
else:
    avatars_folder = req("POST", "/folders", {"name": "Avatars"})["data"]["id"]
    print("directus_folders: created 1 / updated 0 / skipped 0 (Avatars)")

f_created = f_skipped = a_patched = a_skipped = 0
for m in TEAM:
    uid = email_to_id.get(m["email"])
    if not uid:
        continue
    if m.get("_avatar"):
        a_skipped += 1
        continue
    title = "Avatar %s %s" % (m["first_name"], m["last_name"])
    q = urllib.parse.quote(title)
    frows = get("/files?filter[title][_eq]=" + q + "&limit=1&fields=id")["data"]
    if frows:
        fid = frows[0]["id"]
        f_skipped += 1
    else:
        fname = "avatar-%s-%s.svg" % (m["first_name"].lower(), m["last_name"].lower())
        fid = multipart_upload(title, fname, avatar_svg(m["initials"], m["color"]), avatars_folder)
        f_created += 1
    req("PATCH", "/users/" + uid, {"avatar": fid})
    a_patched += 1
print("directus_files (avatars): created %d / updated 0 / skipped %d" % (f_created, f_skipped))
print("user avatar patches: created 0 / updated %d / skipped %d" % (a_patched, a_skipped))

# ------------------------------------------------------------------ step 3: GATED null-fill
GATE = (len(sys.argv) > 1 and sys.argv[1] == "NULLFILL_APPROVED") or \
       os.environ.get("NULLFILL_APPROVED") == "NULLFILL_APPROVED"
NULLFILL_TITLES = {1: "Managing Director", 2: "Product Lead", 3: "Operations Manager"}
NULLFILL_PHONES = {cid: "+1-555-01%02d" % (cid - 1) for cid in range(4, 12)}
NULLFILL_NOTES = {
    1: "Primary decision maker at Demo Co and main point of contact for retainer scope.",
    2: "Leads product direction at Demo Co and reviews sprint demos every other week.",
    3: "Coordinates internal operations at Demo Co and handles invoice approvals.",
    4: "Founded Vellum Studio and stays close to every portfolio platform decision.",
    5: "Runs operations at Harbor Fitness and owns the class booking rollout.",
    6: "Directs marketing at Bloom Botanicals and drives the seasonal campaign calendar.",
    7: "Owns Cedar and Co Coffee and signs off on the website redesign milestones.",
    8: "Manages the Northlight Law brand and reviews identity concepts with partners.",
    9: "General manager at Sterling and Vine overseeing the reservations platform.",
    10: "Directs programs at Meridian Fund and champions the grant portal internally.",
    11: "CTO at Meridian Fund and technical reviewer for portal integrations.",
}
nf_updated = nf_skipped = 0
if GATE:
    for cid in range(1, 12):
        row = get("/items/contacts/%d?fields=id,job_title,phone,contact_notes" % cid)["data"]
        patch = {}
        if cid in NULLFILL_TITLES and not row.get("job_title"):
            patch["job_title"] = NULLFILL_TITLES[cid]
        if cid in NULLFILL_PHONES and not row.get("phone"):
            patch["phone"] = NULLFILL_PHONES[cid]
        if not row.get("contact_notes"):
            patch["contact_notes"] = NULLFILL_NOTES[cid]
        if patch:
            req("PATCH", "/items/contacts/%d" % cid, patch)
            nf_updated += 1
        else:
            nf_skipped += 1
    print("contacts null-fill (GATED, ran): created 0 / updated %d / skipped %d" % (nf_updated, nf_skipped))
else:
    print("contacts null-fill: SKIPPED (no NULLFILL_APPROVED token). Skipped items:")
    for cid in sorted(NULLFILL_TITLES):
        print("  skipped: contacts.%d job_title -> %s" % (cid, NULLFILL_TITLES[cid]))
    for cid in sorted(NULLFILL_PHONES):
        print("  skipped: contacts.%d phone -> %s" % (cid, NULLFILL_PHONES[cid]))
    for cid in sorted(NULLFILL_NOTES):
        print("  skipped: contacts.%d contact_notes (1 sentence)" % cid)

# ------------------------------------------------------------------ step 4: new contacts
NEW_CONTACTS = [
    # org 2 Cedar & Co Coffee
    {"org": 2, "first_name": "Maya", "last_name": "Castillo", "email": "maya.castillo@cedarandco.com",
     "job_title": "Cafe Operations Manager", "phone": "+1-555-0201",
     "contact_notes": "Runs day-to-day operations across all three cafes and reviews weekly site content updates."},
    {"org": 2, "first_name": "Ruben", "last_name": "Achterberg", "email": "ruben.achterberg@cedarandco.com",
     "job_title": "Head Roaster", "phone": "+1-555-0202",
     "contact_notes": "Owns the roasting program and supplies product photography for the online store."},
    # org 3 Northlight Law
    {"org": 3, "first_name": "Ingrid", "last_name": "Halvorsen", "email": "ingrid.halvorsen@northlightlaw.com",
     "job_title": "Managing Partner", "phone": "+1-555-0203",
     "contact_notes": "Gives final sign-off on all brand and website decisions for the firm."},
    {"org": 3, "first_name": "Casey", "last_name": "Whitfield", "email": "casey.whitfield@northlightlaw.com",
     "job_title": "Marketing Coordinator", "phone": "+1-555-0204",
     "contact_notes": "Primary day-to-day contact for the SEO retainer and content calendar."},
    # org 4 Vellum Studio
    {"org": 4, "first_name": "Noor", "last_name": "Haddad", "email": "noor.haddad@vellum.studio",
     "job_title": "Creative Director", "phone": "+1-555-0205",
     "contact_notes": "Sets the creative direction for the portfolio platform and approves all case study layouts."},
    {"org": 4, "first_name": "Jasper", "last_name": "Lindgren", "email": "jasper.lindgren@vellum.studio",
     "job_title": "Studio Manager", "phone": "+1-555-0206",
     "contact_notes": "Coordinates asset delivery and keeps the project schedule on track."},
    # org 5 Harbor Fitness
    {"org": 5, "first_name": "Bianca", "last_name": "Moretti", "email": "bianca.moretti@harborfitness.co",
     "job_title": "Membership Director", "phone": "+1-555-0207",
     "contact_notes": "Owns the membership funnel and reviews booking app analytics monthly."},
    {"org": 5, "first_name": "Kofi", "last_name": "Mensah", "email": "kofi.mensah@harborfitness.co",
     "job_title": "Head Trainer", "phone": "+1-555-0208",
     "contact_notes": "Provides class schedules and trainer bios for the booking app."},
    # org 6 Bloom Botanicals
    {"org": 6, "first_name": "Petra", "last_name": "Vogel", "email": "petra.vogel@bloombotanicals.com",
     "job_title": "E-commerce Manager", "phone": "+1-555-0209",
     "contact_notes": "Manages the Shopify storefront and coordinates seasonal campaign launches."},
    {"org": 6, "first_name": "Silas", "last_name": "Thornton", "email": "silas.thornton@bloombotanicals.com",
     "job_title": "Fulfillment Lead", "phone": "+1-555-0210",
     "contact_notes": "Point of contact for subscription box logistics and shipping integrations."},
    # org 7 Sterling & Vine
    {"org": 7, "first_name": "Camille", "last_name": "Beaumont", "email": "camille.beaumont@sterlingandvine.com",
     "job_title": "Events Director", "phone": "+1-555-0211",
     "contact_notes": "Books private events across all three locations and requested the events calendar module."},
    {"org": 7, "first_name": "Marco", "last_name": "Petrucci", "email": "marco.petrucci@sterlingandvine.com",
     "job_title": "Executive Chef", "phone": "+1-555-0212",
     "contact_notes": "Supplies seasonal menu updates for the reservations site."},
    {"org": 7, "first_name": "Odette", "last_name": "Laurent", "email": "odette.laurent@sterlingandvine.com",
     "job_title": "Reservations Manager", "phone": "+1-555-0213",
     "contact_notes": "Day-to-day contact for the reservations platform rollout."},
    # org 8 Meridian Fund
    {"org": 8, "first_name": "Harriet", "last_name": "Boateng", "email": "harriet.boateng@meridianfund.org",
     "job_title": "Grants Administrator", "phone": "+1-555-0214",
     "contact_notes": "Administers the grant intake pipeline and tests each reviewer dashboard release."},
    {"org": 8, "first_name": "Elliot", "last_name": "Nakamura", "email": "elliot.nakamura@meridianfund.org",
     "job_title": "Communications Lead", "phone": "+1-555-0215",
     "contact_notes": "Handles applicant communications and public program announcements."},
]

c_created = c_updated = c_skipped = 0
new_contact_ids = {}
for c in NEW_CONTACTS:
    q = urllib.parse.quote(c["email"])
    rows = get("/items/contacts?filter[email][_eq]=" + q +
               "&limit=1&fields=id,job_title,phone,contact_notes")["data"]
    if rows:
        row = rows[0]
        new_contact_ids[c["email"]] = row["id"]
        patch = {}
        for f in ("job_title", "phone", "contact_notes"):
            if not row.get(f):
                patch[f] = c[f]
        if patch:
            req("PATCH", "/items/contacts/%d" % row["id"], patch)
            c_updated += 1
        else:
            c_skipped += 1
    else:
        body = {"first_name": c["first_name"], "last_name": c["last_name"],
                "email": c["email"], "phone": c["phone"], "job_title": c["job_title"],
                "contact_notes": c["contact_notes"], "status": "active",
                "is_test_data": False}
        new = req("POST", "/items/contacts", body)["data"]
        new_contact_ids[c["email"]] = new["id"]
        c_created += 1
print("contacts: created %d / updated %d / skipped %d" % (c_created, c_updated, c_skipped))

# ------------------------------------------------------------------ step 5: junction rows
EXISTING_MAP = {1: 1, 2: 1, 3: 1, 4: 4, 5: 5, 6: 6, 7: 2, 8: 3, 9: 7, 10: 8, 11: 8}
contact_to_org = dict(EXISTING_MAP)
for c in NEW_CONTACTS:
    contact_to_org[new_contact_ids[c["email"]]] = c["org"]

j_created = j_skipped = 0
for cid, oid in sorted(contact_to_org.items()):
    rows = get("/items/organizations_contacts?filter[organizations_id][_eq]=%d"
               "&filter[contacts_id][_eq]=%d&limit=1" % (oid, cid))["data"]
    if rows:
        j_skipped += 1
    else:
        req("POST", "/items/organizations_contacts",
            {"organizations_id": oid, "contacts_id": cid})
        j_created += 1
print("organizations_contacts: created %d / updated 0 / skipped %d" % (j_created, j_skipped))

# ------------------------------------------------- step 6: additive read grants (demo policy)
try:
    access = get("/roles/" + EMPLOYEE_ROLE + "?fields=id,name,policies.policy")["data"]
    policy_ids = [p["policy"] for p in access.get("policies", []) if p.get("policy")]
    grants_added = []
    for pid in policy_ids:
        pol = get("/policies/" + pid + "?fields=id,name,admin_access")["data"]
        if pol.get("admin_access"):
            continue
        for coll in ("contacts", "organizations_contacts", "organizations"):
            perms = get("/permissions?filter[policy][_eq]=" + pid +
                        "&filter[collection][_eq]=" + coll +
                        "&filter[action][_eq]=read&limit=1")["data"]
            if not perms:
                req("POST", "/permissions",
                    {"policy": pid, "collection": coll, "action": "read",
                     "fields": ["*"], "permissions": {}, "validation": None})
                grants_added.append("%s:%s" % (pol.get("name", pid), coll))
    if grants_added:
        print("permissions: added read-only grants -> " + ", ".join(grants_added))
    else:
        print("permissions: all read grants already present (contacts, organizations_contacts, organizations)")
except Exception as e:
    print("permissions check WARNING (non-fatal): %s" % e)

# ------------------------------------------------------------------ output contract
all_junctions = get("/items/organizations_contacts?limit=-1&fields=organizations_id,contacts_id")["data"]
membership = {}
for j in all_junctions:
    membership.setdefault(j["organizations_id"], []).append(j["contacts_id"])
primary_by_org = {str(oid): min(cids) for oid, cids in sorted(membership.items())}

print("OUTPUT_CONTRACT_BEGIN")
print("EMAIL_TO_USER_ID=" + json.dumps(email_to_id, sort_keys=True))
print("CONTACT_TO_ORG=" + json.dumps({str(k): v for k, v in sorted(contact_to_org.items())}))
print("PRIMARY_CONTACT_BY_ORG=" + json.dumps(primary_by_org, sort_keys=True))
print("OUTPUT_CONTRACT_END")

# ------------------------------------------------------------------ verify probe
probe = ('query { contacts(limit: 5, sort: ["last_name"]) { id first_name last_name email '
         'phone job_title status organizations { organizations_id { id name service_status } } } }')
r = urllib.request.Request(BASE + "/graphql", data=json.dumps({"query": probe}).encode(),
                           method="POST",
                           headers={"Authorization": "Bearer " + TOKEN,
                                    "Content-Type": "application/json"})
with urllib.request.urlopen(r, timeout=60) as resp:
    result = json.loads(resp.read())
print("VERIFY_GRAPHQL_BEGIN")
print(json.dumps(result, indent=1))
print("VERIFY_GRAPHQL_END")
if "errors" in result:
    print("VERIFY: FAILED (GraphQL errors)")
    sys.exit(1)
rows = result["data"]["contacts"]
nonempty = [c for c in rows if c["organizations"]]
print("VERIFY: %d rows returned, %d with non-empty organizations arrays" % (len(rows), len(nonempty)))
if rows and len(nonempty) == len(rows):
    print("VERIFY: OK")
else:
    print("VERIFY: PARTIAL (some contacts missing org membership)")
