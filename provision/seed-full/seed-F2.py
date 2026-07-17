#!/usr/bin/env python3
"""seed-F2: foundation files/assets for the Muster demo.

Wave 1 work package F2 (foundation-files-assets):
  1. Upsert directus_folders by name: Branding, Avatars, Photos, Receipts,
     Deliverables, Attachments.
  2. [GATED] Org 1 Demo Co logo null-fill. Runs ONLY when NULLFILL_APPROVED=1
     is set in the process environment by the orchestrator. Default: skip.
  3. Import 30 neutral-titled photos (picsum.photos seeded URLs) into Photos.
  4. Generate + upload 8 receipt SVG documents into Receipts (canonical
     vendor+month list matched by D2).
  5. Write machine-readable assets-manifest.json next to this script.

Add-only, idempotent (upsert by title / folder name). Never deletes.
Output: counts, ids, titles only. The admin token is never printed.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "https://cms.musterr.dev"
SEED_DIR = os.path.expanduser("~/elk-os/provision/seed-full")
MANIFEST_PATH = os.path.join(SEED_DIR, "assets-manifest.json")


def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(method, path, body=None, ctype="application/json", timeout=120):
    if body is not None and ctype == "application/json":
        data = json.dumps(body).encode()
    else:
        data = body
    headers = {"Authorization": "Bearer " + TOKEN}
    if data is not None:
        headers["Content-Type"] = ctype
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def get(path):
    return req("GET", path)


def file_by_title(title):
    q = urllib.parse.quote(title)
    rows = get("/files?filter[title][_eq]=" + q + "&limit=1&fields=id,title,folder")["data"]
    return rows[0] if rows else None


def multipart_upload(title, filename, svg_text, folder_id):
    boundary = uuid.uuid4().hex
    parts = []

    def field(name, value):
        parts.append(
            ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, name, value)).encode()
        )

    field("title", title)
    field("folder", folder_id)
    parts.append(
        (
            "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: image/svg+xml\r\n\r\n" % (boundary, filename)
        ).encode()
        + svg_text.encode()
        + b"\r\n"
    )
    parts.append(("--%s--\r\n" % boundary).encode())
    body = b"".join(parts)
    return req("POST", "/files", body, ctype="multipart/form-data; boundary=" + boundary)["data"]["id"]


# ---------------------------------------------------------------- 1. folders
FOLDER_NAMES = ["Branding", "Avatars", "Photos", "Receipts", "Deliverables", "Attachments"]
folders = {}
f_created = f_skipped = 0
for name in FOLDER_NAMES:
    rows = get("/folders?filter[name][_eq]=" + urllib.parse.quote(name) + "&limit=1")["data"]
    if rows:
        folders[name] = rows[0]["id"]
        f_skipped += 1
    else:
        folders[name] = req("POST", "/folders", {"name": name})["data"]["id"]
        f_created += 1
print("directus_folders: created %d / updated 0 / skipped %d" % (f_created, f_skipped))

# ------------------------------------------------- 2. org 1 logo (GATED)
GATE = os.environ.get("NULLFILL_APPROVED") == "1"
logo_gate = {"ran": False, "reason": "NULLFILL_APPROVED not passed; default SKIP", "org_1_logo": None}
org1 = get("/items/organizations/1?fields=logo")["data"]
logo_gate["org_1_logo"] = org1.get("logo")
if GATE:
    if org1.get("logo"):
        logo_gate.update(ran=True, reason="logo already non-null, skipped")
        print("org1 logo gate: SKIPPED (already set)")
    else:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
            '<rect width="512" height="512" rx="96" fill="#1f2937"/>'
            '<text x="256" y="256" font-family="Helvetica, Arial, sans-serif" font-size="200" '
            'font-weight="700" fill="#ffffff" text-anchor="middle" dominant-baseline="central">DC</text>'
            "</svg>"
        )
        fid = multipart_upload("Demo Co logo", "demo-co-logo.svg", svg, folders["Branding"])
        req("PATCH", "/items/organizations/1", {"logo": fid})
        logo_gate.update(ran=True, reason="gate token present, logo uploaded", org_1_logo=fid)
        print("org1 logo gate: RAN, file %s" % fid)
else:
    print("org1 logo gate: SKIPPED (no NULLFILL_APPROVED token)")

# ---------------------------------------------------------------- 3. photos
PHOTOS = (
    [("Project photo %02d" % i, "muster-project-%02d" % i) for i in range(1, 25)]
    + [("Site photography %02d" % i, "muster-site-%02d" % i) for i in range(1, 4)]
    + [("Moodboard frame %02d" % i, "muster-mood-%02d" % i) for i in range(1, 4)]
)
manifest_files = []
p_created = p_skipped = p_failed = 0
for title, slug in PHOTOS:
    existing = file_by_title(title)
    if existing:
        p_skipped += 1
        manifest_files.append(
            {"id": existing["id"], "title": title, "folder": folders["Photos"], "folder_name": "Photos"}
        )
        continue
    url = "https://picsum.photos/seed/%s/1200/800" % slug
    payload = {"url": url, "data": {"title": title, "folder": folders["Photos"]}}
    fid = None
    for attempt in (1, 2):
        try:
            fid = req("POST", "/files/import", payload)["data"]["id"]
            break
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = e.read().decode()[:200]
                except Exception:
                    pass
            print("  import retry %d for %r: %s %s" % (attempt, title, e, detail), file=sys.stderr)
            time.sleep(2)
    if fid:
        p_created += 1
        manifest_files.append({"id": fid, "title": title, "folder": folders["Photos"], "folder_name": "Photos"})
    else:
        p_failed += 1
print("directus_files (photos): created %d / updated 0 / skipped %d / failed %d" % (p_created, p_skipped, p_failed))

# --------------------------------------------------------------- 4. receipts
def receipt_svg(vendor, date, items, total):
    w = 640
    rows = []
    y = 250
    for label, amount in items:
        rows.append(
            '<text x="60" y="%d" font-family="Helvetica, Arial, sans-serif" font-size="20" fill="#374151">%s</text>'
            '<text x="%d" y="%d" font-family="Helvetica, Arial, sans-serif" font-size="20" fill="#111827" text-anchor="end">%s</text>'
            % (y, label, w - 60, y, amount)
        )
        y += 44
    y += 10
    sep2 = '<line x1="60" y1="%d" x2="%d" y2="%d" stroke="#d1d5db" stroke-width="2"/>' % (y, w - 60, y)
    y += 48
    total_row = (
        '<text x="60" y="%d" font-family="Helvetica, Arial, sans-serif" font-size="24" font-weight="700" fill="#111827">Total (USD)</text>'
        '<text x="%d" y="%d" font-family="Helvetica, Arial, sans-serif" font-size="24" font-weight="700" fill="#111827" text-anchor="end">%s</text>'
        % (y, w - 60, y, total)
    )
    h = y + 80
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h)
        + '<rect width="%d" height="%d" fill="#ffffff"/>' % (w, h)
        + '<text x="60" y="90" font-family="Helvetica, Arial, sans-serif" font-size="34" font-weight="700" fill="#111827">%s</text>' % vendor
        + '<text x="60" y="130" font-family="Helvetica, Arial, sans-serif" font-size="16" letter-spacing="4" fill="#6b7280">RECEIPT</text>'
        + '<text x="%d" y="90" font-family="Helvetica, Arial, sans-serif" font-size="18" fill="#374151" text-anchor="end">Date: %s</text>' % (w - 60, date)
        + '<line x1="60" y1="170" x2="%d" y2="170" stroke="#d1d5db" stroke-width="2"/>' % (w - 60)
        + "".join(rows)
        + sep2
        + total_row
        + "</svg>"
    )


RECEIPTS = [
    ("Figma", "2026-06", "2026-06-05",
     [("Figma Professional, 6 editor seats", "$90.00"), ("FigJam add-on, 4 seats", "$12.00")], "$102.00"),
    ("AWS", "2026-06", "2026-06-30",
     [("EC2 compute, t3.medium hours", "$62.14"), ("S3 storage and requests", "$18.37"),
      ("CloudFront data transfer", "$9.61")], "$90.12"),
    ("Linear", "2026-05", "2026-05-11",
     [("Linear Standard, 9 seats", "$72.00"), ("Guest seats, 3", "$12.00")], "$84.00"),
    ("Amtrak", "2026-04", "2026-04-17",
     [("Acela Business, NYP to BOS", "$138.00"), ("Acela Business, BOS to NYP", "$124.00")], "$262.00"),
    ("Moo Print", "2026-03", "2026-03-09",
     [("Business cards, Luxe, 200 ct", "$94.00"), ("Notecards, 100 ct", "$56.00"),
      ("Shipping", "$12.50")], "$162.50"),
    ("Adobe Creative Cloud", "2026-05", "2026-05-21",
     [("All Apps plan, 3 seats", "$179.97"), ("Adobe Stock credits, 10", "$29.99")], "$209.96"),
    ("Notion", "2026-07", "2026-07-02",
     [("Business plan, 12 seats", "$216.00"), ("Notion AI add-on, 12 seats", "$96.00")], "$312.00"),
    ("Uline", "2026-02", "2026-02-24",
     [("Shipping boxes 12x12x8, 25 pack", "$38.00"), ("Packing tape, 6 rolls", "$21.50"),
      ("Freight", "$19.80")], "$79.30"),
]

manifest_receipts = []
r_created = r_skipped = 0
for vendor, month, date, items, total in RECEIPTS:
    title = "Receipt - %s %s" % (vendor, month)
    existing = file_by_title(title)
    if existing:
        fid = existing["id"]
        r_skipped += 1
    else:
        slug = vendor.lower().replace(" ", "-").replace("&", "and")
        fid = multipart_upload(title, "receipt-%s-%s.svg" % (slug, month),
                               receipt_svg(vendor, date, items, total), folders["Receipts"])
        r_created += 1
    manifest_files.append({"id": fid, "title": title, "folder": folders["Receipts"], "folder_name": "Receipts"})
    manifest_receipts.append({"file_id": fid, "vendor": vendor, "month": month, "title": title})
print("directus_files (receipts): created %d / updated 0 / skipped %d" % (r_created, r_skipped))

# --------------------------------------------------------------- 5. manifest
manifest = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "task": "F2 foundation-files-assets",
    "folders": folders,
    "files": manifest_files,
    "receipts": manifest_receipts,
    "logo_gate": logo_gate,
}
os.makedirs(SEED_DIR, exist_ok=True)
with open(MANIFEST_PATH, "w") as f:
    json.dump(manifest, f, indent=2)
print("manifest: wrote %s (%d files, %d receipts, %d folders)"
      % (MANIFEST_PATH, len(manifest_files), len(manifest_receipts), len(folders)))

# ----------------------------------------------------------------- verify
agg = get("/files?filter[folder][_nnull]=true&aggregate[count]=id")["data"][0]
count = agg.get("count")
if isinstance(count, dict):
    count = count.get("id")
print("VERIFY files-in-folders count: %s (need >= 30)" % count)

probes = [
    ("files+folders filtered",
     "query { files(filter: { folder: { id: { _nnull: true } } }, limit: 3) { id title } "
     "folders(limit: 10) { id name } }"),
    ("files+folders plain",
     "query { files(limit: 3) { id title } folders(limit: 10) { id name } }"),
]
for label, q in probes:
    try:
        gql = req("POST", "/graphql/system", {"query": q})
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:500]
        except Exception:
            pass
        print("VERIFY graphql/system (%s): HTTP %s %s" % (label, e.code, body))
        continue
    if gql.get("errors"):
        print("VERIFY graphql/system (%s): ERRORS %s" % (label, json.dumps(gql["errors"])[:400]))
    else:
        print("VERIFY graphql/system (%s) files: %s" % (label, json.dumps(gql["data"]["files"])))
        print("VERIFY graphql/system (%s) folders: %s" % (label, json.dumps(gql["data"]["folders"])))
        break
