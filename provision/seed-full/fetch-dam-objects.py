#!/usr/bin/env python3
"""Build the S3-mock object store for the DAM demo.

Downloads one object per seeded dam_assets key into
  ~/elk-os/mocks/data/agency-directus-assets/<key>
(the dir compose.mocks.yaml bind-mounts read-only into elk-os-mocks at
/data). Photo keys are themed: where one of the 21 curated Unsplash
directus_files matches the asset's subject, that file is downloaded from the
demo Directus itself; the rest use deterministic picsum seeds. Logo keys are
PNG renditions rendered OFF-BOX from the curated brand SVG files (sharp on
the workstation; the container has no fonts, so librsvg text would render
blank there) -- this script only stages the source SVGs for that step under
mocks/data/_logo-src/.

Idempotent: any existing non-empty target file is skipped. Prints names and
byte counts only; the admin token never renders.
"""
import json
import os
import urllib.request
import urllib.parse

BASE = "https://cms.musterr.dev"
DATA = os.path.expanduser("~/elk-os/mocks/data")
BUCKET_DIR = os.path.join(DATA, "agency-directus-assets")
LOGO_SRC = os.path.join(DATA, "_logo-src")


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


def api(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    r = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.load(resp)


def fetch_bytes(url, auth=False):
    headers = {"User-Agent": "elk-os-demo-seed/1.0"}
    if auth:
        headers["Authorization"] = "Bearer " + TOKEN
    r = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return resp.read()


# Curated directus_files, matched by exact title (ids resolved live).
files = api("/files", {"fields": "id,title,type", "limit": "-1"})["data"]
by_title = {f["title"]: f["id"] for f in files if f.get("title")}

# dam key -> curated file title (themed) or None (picsum seed fallback)
PHOTO_SOURCES = {
    "dam/cedar-and-co-coffee/cafe-interior-main-room.jpg": "Cafe interior",
    "dam/cedar-and-co-coffee/coffee-roasting-drum.jpg": "Coffee roasting",
    "dam/cedar-and-co-coffee/loyalty-app-banner.jpg": None,
    "dam/cedar-and-co-coffee/spring-menu-hero.jpg": None,
    "dam/cedar-and-co-coffee/storefront-morning.jpg": None,
    "dam/cedar-and-co-coffee/menu-board-draft.jpg": None,
    "dam/cedar-and-co-coffee/barista-counter.jpg": None,
    "dam/sterling-and-vine/wine-bar-evening.jpg": "Wine bar",
    "dam/sterling-and-vine/dining-room-table.jpg": "Restaurant table",
    "dam/bloom-botanicals/fern-detail-macro.jpg": "Botanical detail",
    "dam/bloom-botanicals/shop-floor-display.jpg": "Plant shop",
    "dam/bloom-botanicals/summer-campaign-hero-draft.jpg": None,
    "dam/northlight-law/reception-office.jpg": "Law office",
    "dam/northlight-law/letterhead-mock-draft.jpg": None,
    "dam/vellum-studio/editorial-spread.jpg": "Editorial layout",
    "dam/vellum-studio/studio-workspace.jpg": "Design studio",
    "dam/vellum-studio/moodboard-2025-archive.jpg": "Brand moodboard",
    "dam/meridian-fund/grant-portal-dashboard-draft.jpg": "Dashboard mockup",
    "dam/meridian-fund/team-meeting-boardroom.jpg": "Team meeting",
    "dam/harbor-fitness/waterfront-gym-floor.jpg": "Gym waterfront",
    "dam/harbor-fitness/booking-app-screens.jpg": "Mobile app",
    "dam/harbor-fitness/class-schedule-promo-draft.jpg": None,
    "dam/demo-co/brand-explorations-draft.jpg": None,
}

# Brand logo SVG sources (curated directus_files) -> local staging name.
LOGO_SOURCES = {
    "Cedar & Co Coffee logo": "cedar-logo-primary",
    "Sterling & Vine logo": "sterling-logo-primary",
    "Northlight Law logo": "northlight-logo-primary",
    "Vellum Studio logo": "vellum-logo-primary",
    "Harbor Fitness logo": "harbor-logo-primary",
    "Bloom Botanicals logo": "bloom-logo-primary",
    "Meridian Fund logo": "meridian-logo-primary",
}

os.makedirs(BUCKET_DIR, exist_ok=True)
os.makedirs(LOGO_SRC, exist_ok=True)

created = skipped = failed = 0
for key, title in sorted(PHOTO_SOURCES.items()):
    target = os.path.join(BUCKET_DIR, key)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        skipped += 1
        continue
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        if title:
            fid = by_title[title]
            data = fetch_bytes(f"{BASE}/assets/{fid}", auth=True)
            src = f"curated:{title}"
        else:
            seed = os.path.splitext(os.path.basename(key))[0]
            data = fetch_bytes(f"https://picsum.photos/seed/{seed}/1600/1067")
            src = "picsum"
        with open(target, "wb") as f:
            f.write(data)
        created += 1
        print(f"  wrote {key} ({len(data)} bytes, {src})")
    except Exception as exc:
        failed += 1
        print(f"  FAILED {key}: {exc}")

print(f"photos: created {created} / skipped {skipped} / failed {failed}")

lcreated = lskipped = lfailed = 0
for title, slug in sorted(LOGO_SOURCES.items()):
    target = os.path.join(LOGO_SRC, slug + ".svg")
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        lskipped += 1
        continue
    try:
        fid = by_title[title]
        data = fetch_bytes(f"{BASE}/assets/{fid}", auth=True)
        with open(target, "wb") as f:
            f.write(data)
        lcreated += 1
        print(f"  staged {slug}.svg ({len(data)} bytes)")
    except Exception as exc:
        lfailed += 1
        print(f"  FAILED logo {slug}: {exc}")

print(f"logo svg staging: created {lcreated} / skipped {lskipped} / failed {lfailed}")
print("NOTE: run render-logo-pngs.js on the workstation next; it converts")
print("_logo-src/*.svg into 512x512 PNGs at dam/<org>/<slug>.png keys.")
