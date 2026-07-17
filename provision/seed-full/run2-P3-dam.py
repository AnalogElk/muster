#!/usr/bin/env python3
"""run2-P3-dam: create + seed the 7 dam_* collections on the Muster demo CMS.

Work package P3 of run 2 (2026-07-16). Creates the DAM schema captured in
blocked-sections.json (dam_assets, dam_collections, dam_assets_collections,
dam_share_links, dam_guidelines, dam_guideline_blocks, dam_render_jobs),
adds additive read-only permission rows to the Demo Read-Only policy
(shared by the Employee demo user and the Client demo user), then seeds a
believable agency asset library:

- 17 dam_collections themed per organization
- 30 dam_assets reusing existing directus_files media as metadata source
  (the source file uuid is recorded in exif.demo_source_file; dam_assets has
  no directus_files relation by design, its media pointer is bucket+key)
- 5 assets at ai_state=suggested so /employee-portal/dam/review has a queue
- 3 dam_guidelines (brand books) with 15 typed blocks for org 2
  (Cedar & Co Coffee, the client demo org), 2 of them client-visible

Idempotent: collections/fields/relations/permissions are skipped when
present; items upsert by natural key (slug, bucket+key, junction pair,
guideline+type+sort). Add-only: nothing is deleted or overwritten.

Verification (same run): REST probes with fresh session tokens for
demo@muster.dev and client@muster.dev using the portal services' exact
field strings, plus an admin GraphQL probe of the list shapes.

dam_share_links and dam_render_jobs are created but left empty per spec
(queue/token tables; blocked-sections.json marks them safe to leave empty).
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cms.musterr.dev"
POLICY_DEMO = "c69b84d1-8957-4687-a6dd-b049b3e890b9"  # Demo Read-Only (Employee + Client roles)


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


def req(path, method="GET", body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": "Bearer " + (token or TOKEN),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        return e.code, payload


def die(msg, payload=None):
    print("FATAL:", msg)
    if payload:
        print(json.dumps(payload, indent=1)[:2000])
    raise SystemExit(1)


# --------------------------------------------------------------------------
# 1. Collections + fields (additive)
# --------------------------------------------------------------------------

def uuid_pk():
    return {
        "field": "id", "type": "uuid",
        "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
        "schema": {"is_primary_key": True, "length": 36, "has_auto_increment": False},
    }


def f_str(name, required=False, default=None, choices=None):
    meta = {"interface": "select-dropdown" if choices else "input"}
    if choices:
        meta["options"] = {"choices": [{"text": c.replace("_", " ").title(), "value": c} for c in choices]}
    if required:
        meta["required"] = True
    schema = {}
    if default is not None:
        schema["default_value"] = default
    return {"field": name, "type": "string", "meta": meta, "schema": schema}


def f_text(name):
    return {"field": name, "type": "text", "meta": {"interface": "input-multiline"}, "schema": {}}


def f_int(name, default=None):
    schema = {}
    if default is not None:
        schema["default_value"] = default
    return {"field": name, "type": "integer", "meta": {"interface": "input"}, "schema": schema}


def f_json(name):
    return {"field": name, "type": "json",
            "meta": {"interface": "input-code", "options": {"language": "JSON"}}, "schema": {}}


def f_bool(name, default=False):
    return {"field": name, "type": "boolean", "meta": {"interface": "boolean"},
            "schema": {"default_value": default}}


def f_m2o_org():
    return {"field": "org", "type": "integer",
            "meta": {"interface": "select-dropdown-m2o", "display": "related-values",
                     "display_options": {"template": "{{name}}"}}, "schema": {}}


def f_file(name):
    return {"field": name, "type": "uuid",
            "meta": {"interface": "file-image", "special": ["file"]}, "schema": {}}


def f_m2o_uuid(name, required=False):
    meta = {"interface": "select-dropdown-m2o"}
    if required:
        meta["required"] = True
    return {"field": name, "type": "uuid", "meta": meta, "schema": {}}


def f_ts(name, special):
    return {"field": name, "type": "timestamp",
            "meta": {"interface": "datetime", "readonly": True, "hidden": True, "special": [special]},
            "schema": {}}


COLLECTIONS = {
    "dam_assets": {
        "meta": {"icon": "image", "note": "DAM canonical assets (Muster demo)", "sort_field": None},
        "fields": [
            uuid_pk(), f_m2o_org(),
            f_str("s3_uri", required=True), f_str("bucket", required=True), f_str("key", required=True),
            f_str("checksum"), f_str("mime"), f_int("width"), f_int("height"),
            {"field": "size_bytes", "type": "bigInteger", "meta": {"interface": "input"}, "schema": {}},
            f_json("exif"), f_str("title"), f_text("description"), f_text("alt_text"),
            f_str("seo_filename"), f_json("tags"), f_json("dominant_colors"),
            f_str("status", required=True, default="draft",
                  choices=["draft", "internal", "client_approved", "archived"]),
            f_str("ai_state", default="none", choices=["none", "suggested", "accepted"]),
            f_json("ai_suggestions"), f_json("embedding"),
            f_text("rights_note"),
            {"field": "rights_expiry", "type": "date", "meta": {"interface": "datetime"}, "schema": {}},
            f_str("credit"), f_int("download_count", default=0), f_json("edits"),
            f_ts("date_created", "date-created"), f_ts("date_updated", "date-updated"),
        ],
        "alias": [{"field": "collections", "meta": {"interface": "list-m2m", "special": ["m2m"]}}],
    },
    "dam_collections": {
        "meta": {"icon": "folder_special", "note": "DAM curated collections (Muster demo)"},
        "fields": [
            uuid_pk(), f_m2o_org(),
            f_str("name", required=True), f_str("slug", required=True),
            f_text("description"), f_bool("is_client_visible", default=False),
            # Not in blocked-sections.json but REQUIRED by the frozen portal:
            # lib/dam/assets-service.ts listCollections() sorts by "sort";
            # without the column Directus 400s and the Collections panel
            # renders empty. Additive fragment-diff fix.
            f_int("sort"),
        ],
        "alias": [{"field": "assets", "meta": {"interface": "list-m2m", "special": ["m2m"]}}],
    },
    "dam_assets_collections": {
        "meta": {"icon": "import_export", "note": "DAM asset<->collection junction", "hidden": True},
        "fields": [
            {"field": "id", "type": "integer", "meta": {"hidden": True},
             "schema": {"is_primary_key": True, "has_auto_increment": True}},
            f_m2o_uuid("dam_assets_id"), f_m2o_uuid("dam_collections_id"),
        ],
        "alias": [],
    },
    "dam_share_links": {
        "meta": {"icon": "share", "note": "DAM share links (empty by design in demo)"},
        "fields": [
            uuid_pk(), f_str("label"), f_str("token_hash", required=True),
            f_m2o_uuid("asset"), f_m2o_uuid("collection_ref"),
            {"field": "expires_at", "type": "timestamp", "meta": {"interface": "datetime", "required": True},
             "schema": {}},
            f_str("password_hash"), f_int("max_downloads"), f_int("download_count", default=0),
        ],
        "alias": [],
    },
    "dam_guidelines": {
        "meta": {"icon": "menu_book", "note": "Brand Books (Muster demo)"},
        "fields": [
            uuid_pk(), f_m2o_org(),
            f_str("title", required=True), f_text("body"), f_int("sort"),
            f_bool("is_client_visible", default=False),
            f_str("slug"), f_str("tagline"), f_str("accent_color"),
            f_file("cover_image"), f_file("logo"),
            f_str("logo_plate", choices=["none", "light", "dark"]),
        ],
        "alias": [{"field": "blocks", "meta": {"interface": "list-o2m", "special": ["o2m"]}}],
    },
    "dam_guideline_blocks": {
        "meta": {"icon": "view_agenda", "note": "Brand Book blocks", "hidden": True},
        "fields": [
            uuid_pk(), f_m2o_uuid("guideline", required=True), f_int("sort"),
            f_str("type", required=True,
                  choices=["cover", "palette", "typography", "logo", "voice",
                           "imagery", "usage", "gallery", "richtext", "downloads"]),
            f_json("data"),
        ],
        "alias": [],
    },
    "dam_render_jobs": {
        "meta": {"icon": "movie_filter", "note": "DAM render queue (empty by design in demo)",
                 "hidden": True},
        "fields": [
            uuid_pk(), f_m2o_uuid("asset", required=True),
            f_str("status", required=True, default="pending",
                  choices=["pending", "processing", "done", "failed", "archived"]),
            f_str("output_key"), f_text("last_error"), f_int("attempts", default=0),
            f_json("edits_snapshot"), f_ts("date_created", "date-created"),
        ],
        "alias": [],
    },
}

RELATIONS = [
    {"collection": "dam_assets", "field": "org", "related_collection": "organizations"},
    {"collection": "dam_collections", "field": "org", "related_collection": "organizations"},
    {"collection": "dam_guidelines", "field": "org", "related_collection": "organizations"},
    {"collection": "dam_guidelines", "field": "cover_image", "related_collection": "directus_files"},
    {"collection": "dam_guidelines", "field": "logo", "related_collection": "directus_files"},
    {"collection": "dam_share_links", "field": "asset", "related_collection": "dam_assets"},
    {"collection": "dam_share_links", "field": "collection_ref", "related_collection": "dam_collections"},
    {"collection": "dam_render_jobs", "field": "asset", "related_collection": "dam_assets"},
    {"collection": "dam_guideline_blocks", "field": "guideline", "related_collection": "dam_guidelines",
     "meta": {"one_field": "blocks", "sort_field": "sort"}},
    {"collection": "dam_assets_collections", "field": "dam_assets_id", "related_collection": "dam_assets",
     "meta": {"one_field": "collections", "junction_field": "dam_collections_id"}},
    {"collection": "dam_assets_collections", "field": "dam_collections_id",
     "related_collection": "dam_collections",
     "meta": {"one_field": "assets", "junction_field": "dam_assets_id"}},
]


def ensure_collections():
    created = skipped = fields_added = failed = 0
    for name, spec in COLLECTIONS.items():
        st, _ = req(f"/collections/{name}")
        if st == 200:
            skipped += 1
        else:
            body = {"collection": name, "meta": spec["meta"], "schema": {},
                    "fields": spec["fields"]}
            st2, resp = req("/collections", "POST", body)
            if st2 in (200, 204):
                created += 1
                print(f"  collection {name}: created")
            else:
                failed += 1
                print(f"  collection {name}: FAILED {st2}", json.dumps(resp)[:400])
                continue
        # additive field diff (also adds alias fields)
        st3, existing = req(f"/fields/{name}")
        have = {f["field"] for f in existing.get("data", [])} if st3 == 200 else set()
        want = list(spec["fields"]) + [
            {"field": a["field"], "type": "alias", "meta": a["meta"], "schema": None}
            for a in spec["alias"]
        ]
        for fdef in want:
            if fdef["field"] in have:
                continue
            st4, resp = req(f"/fields/{name}", "POST", fdef)
            if st4 in (200, 204):
                fields_added += 1
                print(f"  field {name}.{fdef['field']}: added")
            else:
                failed += 1
                print(f"  field {name}.{fdef['field']}: FAILED {st4}", json.dumps(resp)[:300])
    print(f"collections: created {created} / skipped {skipped} / fields added {fields_added} / failed {failed}")
    return failed == 0


def ensure_relations():
    st, existing = req("/relations")
    have = set()
    if st == 200:
        for r in existing.get("data", []):
            have.add((r.get("collection"), r.get("field")))
    created = skipped = failed = 0
    for rel in RELATIONS:
        keypair = (rel["collection"], rel["field"])
        if keypair in have:
            skipped += 1
            continue
        st2, resp = req("/relations", "POST", rel)
        if st2 in (200, 204):
            created += 1
            print(f"  relation {rel['collection']}.{rel['field']} -> {rel['related_collection']}: created")
        else:
            failed += 1
            print(f"  relation {rel['collection']}.{rel['field']}: FAILED {st2}", json.dumps(resp)[:300])
    print(f"relations: created {created} / skipped {skipped} / failed {failed}")
    return failed == 0


def ensure_permissions():
    created = skipped = failed = 0
    for name in COLLECTIONS:
        st, resp = req(
            f"/permissions?filter[policy][_eq]={POLICY_DEMO}"
            f"&filter[collection][_eq]={name}&filter[action][_eq]=read&limit=1"
        )
        if st == 200 and resp.get("data"):
            skipped += 1
            continue
        body = {"policy": POLICY_DEMO, "collection": name, "action": "read",
                "permissions": {}, "validation": None, "presets": None, "fields": ["*"]}
        st2, resp2 = req("/permissions", "POST", body)
        if st2 in (200, 204):
            created += 1
            print(f"  permission read {name}: created")
        else:
            failed += 1
            print(f"  permission read {name}: FAILED {st2}", json.dumps(resp2)[:300])
    print(f"permissions (policy Demo Read-Only): created {created} / skipped {skipped} / failed {failed}")
    return failed == 0


# --------------------------------------------------------------------------
# 2. Seed data
# --------------------------------------------------------------------------

# org ids (probed live 2026-07-16): 1 Demo Co, 2 Cedar & Co Coffee,
# 3 Northlight Law, 4 Vellum Studio, 5 Harbor Fitness, 6 Bloom Botanicals,
# 7 Sterling & Vine, 8 Meridian Fund

DAM_COLLECTIONS_SEED = [
    # (slug, org, name, description, is_client_visible, sort)
    ("cedar-logos-brand-marks", 2, "Logos & Brand Marks",
     "Approved Cedar & Co logo lockups, monograms, and clear-space variants.", True, 1),
    ("cedar-location-photography", 2, "Location & Product Photography",
     "Cafe interiors, roasting, and storefront photography cleared for client use.", True, 2),
    ("cedar-web-social", 2, "Web & Social Graphics",
     "Hero images and banners sized for cedarandco.com and social channels.", True, 3),
    ("cedar-internal-wip", 2, "Internal Work in Progress",
     "Drafts and unreviewed shots. Not visible to the client portal.", False, 4),
    ("bloom-brand", 6, "Brand & Logo",
     "Bloom Botanicals logo files and brand marks.", True, 1),
    ("bloom-product-photography", 6, "Product Photography",
     "Greenhouse and plant photography for the storefront.", True, 2),
    ("bloom-campaigns", 6, "Campaign Assets",
     "Seasonal campaign drafts awaiting review.", False, 3),
    ("harbor-brand", 5, "Brand & Logo",
     "Harbor Fitness brand marks.", True, 1),
    ("harbor-app-ui", 5, "App Screens & UI",
     "Booking app screens and UI exports for release notes.", False, 2),
    ("harbor-photography", 5, "Facility Photography",
     "Waterfront gym facility photography.", True, 3),
    ("northlight-brand-system", 3, "Brand System",
     "Northlight Law identity files.", True, 1),
    ("northlight-collateral", 3, "Stationery & Collateral",
     "Letterhead, office, and print collateral sources.", False, 2),
    ("vellum-brand", 4, "Brand & Logo",
     "Vellum Studio brand marks and moodboards.", True, 1),
    ("vellum-portfolio-imagery", 4, "Portfolio Imagery",
     "Editorial and workspace photography for the portfolio site.", True, 2),
    ("sterling-brand", 7, "Brand & Logo",
     "Sterling & Vine brand marks.", True, 1),
    ("sterling-photography", 7, "Restaurant Photography",
     "Dining room and wine bar photography.", True, 2),
    ("meridian-brand", 8, "Brand & Logo",
     "Meridian Fund identity and report graphics.", True, 1),
]

# file metadata mirrored from directus_files (probed live 2026-07-16)
SVG = ("image/svg+xml", None, None, 579)
ASSETS_SEED = [
    # (source_file_id, org, key, title, status, ai_state, collection_slugs,
    #  (mime,w,h,size), tags, dominant_colors, description, alt_text,
    #  seo_filename, credit, rights_note, rights_expiry, download_count, created)
    ("987980ab-9ff3-4819-9d29-3d82f9798b30", 2, "dam/cedar-and-co-coffee/cedar-logo-primary.svg",
     "Cedar & Co primary logo", "client_approved", "none", ["cedar-logos-brand-marks"], SVG,
     ["logo", "brand", "vector"], ["#7A4F2B", "#F5EFE6"],
     "Primary horizontal lockup of the Cedar & Co Coffee wordmark.",
     "Cedar & Co Coffee logo on a light background",
     "cedar-and-co-coffee-logo.svg", "Muster Studio", None, None, 14, "2026-02-04T10:00:00Z"),
    ("52b06b7f-3ca4-45df-bc3f-43f04625fc13", 2, "dam/cedar-and-co-coffee/cafe-interior-main-room.jpg",
     "Cafe interior, main room", "client_approved", "accepted", ["cedar-location-photography"],
     ("image/jpeg", 1200, 800, 186167),
     ["cafe", "interior", "photography"], ["#8A6A4F", "#D9C7B2", "#3A2E24"],
     "Main seating room at the Pearl District cafe, morning light.",
     "Warm cafe interior with wooden tables and morning light",
     "cedar-cafe-interior.jpg", "Muster Studio", None, None, 9, "2026-02-18T10:00:00Z"),
    ("5a577e85-8145-40e7-96d3-f36a1657d155", 2, "dam/cedar-and-co-coffee/coffee-roasting-drum.jpg",
     "Coffee roasting drum", "client_approved", "none", ["cedar-location-photography"],
     ("image/jpeg", 1200, 915, 284087),
     ["roasting", "coffee", "process"], ["#4A3626", "#B08D5B"],
     "Roasting drum mid-batch at the Cedar & Co roastery.",
     "Coffee beans tumbling in a roasting drum",
     "cedar-coffee-roasting.jpg", "Muster Studio", None, None, 6, "2026-03-02T10:00:00Z"),
    ("454ed00f-3624-4499-afc5-cfb0a072ffd7", 2, "dam/cedar-and-co-coffee/storefront-morning.jpg",
     "Storefront, morning", "client_approved", "suggested", ["cedar-location-photography"],
     ("image/jpeg", 1200, 800, 135955),
     ["storefront", "exterior"], ["#6E7B70", "#C9B79C"],
     "Street-facing storefront before opening.",
     "Cedar & Co storefront with awning at sunrise",
     "cedar-storefront-morning.jpg", "Muster Studio", None, None, 4, "2026-04-11T10:00:00Z"),
    ("4986a741-4518-4d29-aca1-67c5925717f8", 2, "dam/cedar-and-co-coffee/barista-counter.jpg",
     "Barista at counter", "internal", "none", ["cedar-location-photography"],
     ("image/jpeg", 1200, 800, 54943),
     ["barista", "counter", "people"], ["#5C4433", "#E8DFD2"],
     "Counter service during the mid-morning rush. Faces not yet cleared for external use.",
     "Barista preparing espresso at the counter",
     "cedar-barista-counter.jpg", "Muster Studio",
     "Model release pending for staff visible in frame.", None, 2, "2026-04-25T10:00:00Z"),
    ("97c4c195-7cd2-4b42-839f-1c528e93766b", 2, "dam/cedar-and-co-coffee/menu-board-draft.jpg",
     "Menu board draft", "draft", "suggested", ["cedar-internal-wip"],
     ("image/jpeg", 1200, 800, 75298),
     ["menu", "draft"], ["#2B211A", "#D9C7B2"],
     "Draft photograph of the spring menu board. Needs retake for glare.",
     "Chalk menu board above the espresso machine",
     "cedar-menu-board.jpg", None, None, None, 0, "2026-06-20T10:00:00Z"),
    ("0de6e142-c5d7-4ba4-a686-c66c91db9b30", 2, "dam/cedar-and-co-coffee/spring-menu-hero.jpg",
     "Spring menu hero", "client_approved", "none", ["cedar-web-social"],
     ("image/jpeg", 1200, 800, 123438),
     ["hero", "web", "seasonal"], ["#7A4F2B", "#9FB48E"],
     "Hero image for the spring menu landing page.",
     "Latte and pastry on a wooden table with spring flowers",
     "cedar-spring-menu-hero.jpg", "Licensed stock",
     "Licensed stock image, web use only.", "2027-03-31", 11, "2026-03-20T10:00:00Z"),
    ("f82fed74-f2fd-4ae4-8e76-3ba3caa7fbff", 2, "dam/cedar-and-co-coffee/loyalty-app-banner.jpg",
     "Loyalty app banner", "internal", "none", ["cedar-web-social"],
     ("image/jpeg", 1200, 800, 26393),
     ["banner", "app", "loyalty"], ["#7A4F2B", "#F5EFE6"],
     "Banner concept for the loyalty app launch. Awaiting copy sign-off.",
     "Coffee cup with loyalty card graphic overlay",
     "cedar-loyalty-banner.jpg", None, None, None, 1, "2026-05-14T10:00:00Z"),
    ("a9796bf6-6a70-47ca-9f40-230c21787d28", 6, "dam/bloom-botanicals/bloom-logo-primary.svg",
     "Bloom Botanicals primary logo", "client_approved", "none", ["bloom-brand"], SVG,
     ["logo", "brand", "vector"], ["#4C7A45", "#F2F0E6"],
     "Primary Bloom Botanicals wordmark.",
     "Bloom Botanicals logo", "bloom-botanicals-logo.svg", "Muster Studio",
     None, None, 8, "2026-02-10T10:00:00Z"),
    ("c8d8370b-ad68-4147-8475-74a87958366a", 6, "dam/bloom-botanicals/shop-floor-display.jpg",
     "Shop floor display", "client_approved", "accepted", ["bloom-product-photography"],
     ("image/jpeg", 1200, 799, 51063),
     ["retail", "plants", "display"], ["#4C7A45", "#D8CBB4"],
     "Front-of-shop plant display, summer arrangement.",
     "Rows of potted plants on wooden shelving",
     "bloom-shop-display.jpg", "Muster Studio", None, None, 7, "2026-03-12T10:00:00Z"),
    ("67d91258-bceb-461d-bbaa-6e099075db02", 6, "dam/bloom-botanicals/fern-detail-macro.jpg",
     "Fern detail macro", "internal", "none", ["bloom-product-photography"],
     ("image/jpeg", 1200, 886, 152747),
     ["macro", "plants"], ["#3E5F38", "#A6BE97"],
     "Macro frond detail for texture backgrounds.",
     "Close-up of fern fronds", "bloom-fern-macro.jpg", "Muster Studio",
     None, None, 3, "2026-05-06T10:00:00Z"),
    ("4ccc0388-111d-4a8a-96c8-ffc29674a41d", 6, "dam/bloom-botanicals/summer-campaign-hero-draft.jpg",
     "Summer campaign hero draft", "draft", "suggested", ["bloom-campaigns"],
     ("image/jpeg", 1200, 800, 35334),
     ["campaign", "draft", "summer"], ["#4C7A45", "#E8D9A0"],
     "Draft hero for the summer subscription campaign.",
     "Sunlit greenhouse bench with seedling trays",
     "bloom-summer-hero.jpg", None, None, None, 0, "2026-06-28T10:00:00Z"),
    ("a57c9ac7-e93e-488a-ba8c-f616e5473dc1", 5, "dam/harbor-fitness/harbor-logo-primary.svg",
     "Harbor Fitness primary logo", "client_approved", "none", ["harbor-brand"], SVG,
     ["logo", "brand", "vector"], ["#1F4E6B", "#F0F4F6"],
     "Primary Harbor Fitness wordmark.",
     "Harbor Fitness logo", "harbor-fitness-logo.svg", "Muster Studio",
     None, None, 10, "2026-02-14T10:00:00Z"),
    ("7091da69-f26b-4ee6-bc07-d97c967859cc", 5, "dam/harbor-fitness/waterfront-gym-floor.jpg",
     "Waterfront gym floor", "client_approved", "none", ["harbor-photography"],
     ("image/jpeg", 1200, 800, 163168),
     ["gym", "facility", "waterfront"], ["#1F4E6B", "#C4CDD3"],
     "Main training floor with the waterfront window line.",
     "Gym floor with rowing machines and harbor view",
     "harbor-gym-floor.jpg", "Muster Studio", None, None, 5, "2026-03-25T10:00:00Z"),
    ("e8fafa66-1847-4ff7-b95f-6b699d29eddf", 5, "dam/harbor-fitness/booking-app-screens.jpg",
     "Booking app screens", "internal", "none", ["harbor-app-ui"],
     ("image/jpeg", 1200, 800, 115592),
     ["app", "ui", "screens"], ["#1F4E6B", "#FFFFFF"],
     "Composite of booking flow screens for the v2.3 release notes.",
     "Phone screens showing a class booking flow",
     "harbor-booking-screens.jpg", None, None, None, 2, "2026-06-05T10:00:00Z"),
    ("7cc4963e-cdb9-4a26-b01e-4e6c966b51b6", 5, "dam/harbor-fitness/class-schedule-promo-draft.jpg",
     "Class schedule promo draft", "draft", "suggested", ["harbor-photography"],
     ("image/jpeg", 1200, 800, 144095),
     ["promo", "draft", "classes"], ["#1F4E6B", "#E4B04A"],
     "Draft promo tile for the fall class schedule.",
     "Group fitness class mid-session",
     "harbor-class-promo.jpg", None, None, None, 0, "2026-07-08T10:00:00Z"),
    ("600e9ca6-5abb-470d-a4b1-897eae13755d", 3, "dam/northlight-law/northlight-logo-primary.svg",
     "Northlight Law primary logo", "client_approved", "none", ["northlight-brand-system"], SVG,
     ["logo", "brand", "vector"], ["#22303C", "#C8A96A"],
     "Primary Northlight Law wordmark.",
     "Northlight Law logo", "northlight-law-logo.svg", "Muster Studio",
     None, None, 6, "2026-02-22T10:00:00Z"),
    ("717b155e-a747-4330-a980-92364e1473fa", 3, "dam/northlight-law/reception-office.jpg",
     "Reception office", "internal", "none", ["northlight-collateral"],
     ("image/jpeg", 1200, 787, 137329),
     ["office", "reception"], ["#22303C", "#D6CFC2"],
     "Reception area photography for the about page refresh.",
     "Law office reception with wood paneling",
     "northlight-reception.jpg", "Muster Studio", None, None, 1, "2026-04-18T10:00:00Z"),
    ("60f8488b-430d-487b-9361-aca3d0534881", 3, "dam/northlight-law/letterhead-mock-draft.jpg",
     "Letterhead mock draft", "draft", "none", ["northlight-collateral"],
     ("image/jpeg", 1200, 800, 115667),
     ["stationery", "draft"], ["#22303C", "#FFFFFF"],
     "Draft letterhead mock. Pending partner review.",
     "Letterhead mockup on a desk", "northlight-letterhead-mock.jpg", None,
     None, None, 0, "2026-06-30T10:00:00Z"),
    ("373aa345-84e0-41a4-8a46-f3507e4270c0", 4, "dam/vellum-studio/vellum-logo-primary.svg",
     "Vellum Studio primary logo", "client_approved", "none", ["vellum-brand"], SVG,
     ["logo", "brand", "vector"], ["#3B3630", "#EDE6DA"],
     "Primary Vellum Studio wordmark.",
     "Vellum Studio logo", "vellum-studio-logo.svg", "Muster Studio",
     None, None, 7, "2026-02-27T10:00:00Z"),
    ("c316a688-465a-46d8-b572-d399838d5956", 4, "dam/vellum-studio/studio-workspace.jpg",
     "Studio workspace", "client_approved", "none", ["vellum-portfolio-imagery"],
     ("image/jpeg", 1200, 801, 109060),
     ["studio", "workspace"], ["#3B3630", "#C9BFAF"],
     "Studio workspace photography for the portfolio home page.",
     "Design studio desks with monitors and print samples",
     "vellum-studio-workspace.jpg", "Muster Studio", None, None, 4, "2026-03-30T10:00:00Z"),
    ("08798d8b-e0d5-4442-8f02-ed7f07000e91", 4, "dam/vellum-studio/editorial-spread.jpg",
     "Editorial spread", "internal", "none", ["vellum-portfolio-imagery"],
     ("image/jpeg", 1200, 800, 187577),
     ["editorial", "print"], ["#3B3630", "#E0D6C6"],
     "Editorial spread photography, awaiting client approval to publish.",
     "Open magazine spread on a table",
     "vellum-editorial-spread.jpg", "Muster Studio", None, None, 2, "2026-05-22T10:00:00Z"),
    ("ac9926b1-5f7f-4b7b-a3a5-53869b3c496b", 4, "dam/vellum-studio/moodboard-2025-archive.jpg",
     "Moodboard 2025 (archive)", "archived", "none", ["vellum-brand"],
     ("image/jpeg", 1200, 1500, 292684),
     ["moodboard", "archive"], ["#8B7B66", "#D9CDBB"],
     "Superseded 2025 brand moodboard, retained for reference.",
     "Collage moodboard with fabric and paper samples",
     "vellum-moodboard-2025.jpg", "Muster Studio", None, None, 3, "2026-02-06T10:00:00Z"),
    ("5f1f8acc-2afa-48b5-ad1f-2bc6277cc309", 7, "dam/sterling-and-vine/sterling-logo-primary.svg",
     "Sterling & Vine primary logo", "client_approved", "none", ["sterling-brand"], SVG,
     ["logo", "brand", "vector"], ["#5B2333", "#E9E2D6"],
     "Primary Sterling & Vine wordmark.",
     "Sterling & Vine logo", "sterling-and-vine-logo.svg", "Muster Studio",
     None, None, 9, "2026-03-05T10:00:00Z"),
    ("94542633-4c2c-4332-843b-d63ae464b391", 7, "dam/sterling-and-vine/dining-room-table.jpg",
     "Dining room table setting", "client_approved", "none", ["sterling-photography"],
     ("image/jpeg", 1200, 800, 240287),
     ["dining", "restaurant"], ["#5B2333", "#D9C9B4"],
     "Dining room table setting for the reservations page.",
     "Set restaurant table with wine glasses",
     "sterling-dining-room.jpg", "Muster Studio", None, None, 6, "2026-04-02T10:00:00Z"),
    ("bf29684e-535c-40dd-8852-4a07cdd7f4ad", 7, "dam/sterling-and-vine/wine-bar-evening.jpg",
     "Wine bar, evening", "internal", "suggested", ["sterling-photography"],
     ("image/jpeg", 1200, 800, 102699),
     ["bar", "evening", "wine"], ["#3A1E28", "#B98A4C"],
     "Evening bar photography, color grade in review.",
     "Wine bar with backlit bottle shelves at night",
     "sterling-wine-bar.jpg", "Muster Studio", None, None, 1, "2026-06-12T10:00:00Z"),
    ("3f85d524-2804-4f2f-a104-cbdd79300671", 8, "dam/meridian-fund/meridian-logo-primary.svg",
     "Meridian Fund primary logo", "client_approved", "none", ["meridian-brand"], SVG,
     ["logo", "brand", "vector"], ["#14324A", "#DCE4EA"],
     "Primary Meridian Fund wordmark.",
     "Meridian Fund logo", "meridian-fund-logo.svg", "Muster Studio",
     None, None, 5, "2026-03-09T10:00:00Z"),
    ("b0717d6c-2f7e-48f6-9906-00f4b3577b52", 8, "dam/meridian-fund/team-meeting-boardroom.jpg",
     "Team meeting, boardroom", "internal", "none", [],
     ("image/jpeg", 1200, 800, 143802),
     ["meeting", "team"], ["#14324A", "#C9CFD4"],
     "Boardroom photography for the annual report, internal review copy.",
     "Team around a boardroom table",
     "meridian-team-meeting.jpg", "Muster Studio", None, None, 1, "2026-05-28T10:00:00Z"),
    ("27cc7800-6ffa-460a-9f3d-cc2630261192", 8, "dam/meridian-fund/grant-portal-dashboard-draft.jpg",
     "Grant portal dashboard draft", "draft", "none", [],
     ("image/jpeg", 1200, 800, 116517),
     ["dashboard", "ui", "draft"], ["#14324A", "#FFFFFF"],
     "Draft dashboard capture for the grant portal case study.",
     "Analytics dashboard on a laptop screen",
     "meridian-dashboard-draft.jpg", None, None, None, 0, "2026-07-03T10:00:00Z"),
    ("573b7d86-4931-4f8d-be00-c728d24c233b", 1, "dam/demo-co/brand-explorations-draft.jpg",
     "Brand explorations draft", "draft", "none", [],
     ("image/jpeg", 1200, 800, 51287),
     ["exploration", "draft"], ["#1F2937", "#E5E7EB"],
     "Early brand exploration frames for the Demo Co refresh.",
     "Moodboard frame with type samples",
     "demo-co-brand-explorations.jpg", None, None, None, 0, "2026-07-10T10:00:00Z"),
]

AI_SUGGESTIONS = {
    "dam/cedar-and-co-coffee/storefront-morning.jpg": {
        "title": "Cedar & Co storefront at sunrise",
        "description": "Street-level view of the Cedar & Co Coffee storefront with awning and sidewalk seating in early morning light.",
        "alt_text": "Coffee shop storefront with green awning at sunrise",
        "seo_filename": "cedar-co-coffee-storefront-sunrise.jpg",
        "tags": ["storefront", "exterior", "morning", "cafe"],
        "dominant_colors": ["#6E7B70", "#C9B79C", "#3E4A42"],
        "model": "claude-sonnet-4", "enriched_at": "2026-07-10T14:12:00Z",
    },
    "dam/cedar-and-co-coffee/menu-board-draft.jpg": {
        "title": "Spring menu chalkboard",
        "description": "Hand-lettered chalk menu board mounted above the espresso machine listing seasonal drinks.",
        "alt_text": "Chalkboard menu above an espresso machine",
        "seo_filename": "cedar-co-spring-menu-board.jpg",
        "tags": ["menu", "chalkboard", "seasonal"],
        "dominant_colors": ["#2B211A", "#D9C7B2"],
        "model": "claude-sonnet-4", "enriched_at": "2026-07-10T14:13:00Z",
    },
    "dam/bloom-botanicals/summer-campaign-hero-draft.jpg": {
        "title": "Greenhouse seedling bench in summer light",
        "description": "Sunlit greenhouse bench holding seedling trays, shot for the summer subscription campaign.",
        "alt_text": "Seedling trays on a greenhouse bench in sunlight",
        "seo_filename": "bloom-summer-greenhouse-hero.jpg",
        "tags": ["greenhouse", "seedlings", "summer", "campaign"],
        "dominant_colors": ["#4C7A45", "#E8D9A0", "#F2F0E6"],
        "model": "claude-sonnet-4", "enriched_at": "2026-07-11T09:41:00Z",
    },
    "dam/harbor-fitness/class-schedule-promo-draft.jpg": {
        "title": "Group class in session",
        "description": "Group fitness class mid-session on the main floor, candidate tile for the fall schedule promo.",
        "alt_text": "People exercising in a group fitness class",
        "seo_filename": "harbor-fitness-group-class.jpg",
        "tags": ["fitness", "class", "promo"],
        "dominant_colors": ["#1F4E6B", "#E4B04A"],
        "model": "claude-sonnet-4", "enriched_at": "2026-07-12T16:05:00Z",
    },
    "dam/sterling-and-vine/wine-bar-evening.jpg": {
        "title": "Backlit wine bar at night",
        "description": "Evening interior of the Sterling & Vine bar with backlit bottle shelving and low ambient light.",
        "alt_text": "Wine bar with glowing backlit shelves at night",
        "seo_filename": "sterling-vine-wine-bar-night.jpg",
        "tags": ["bar", "wine", "evening", "interior"],
        "dominant_colors": ["#3A1E28", "#B98A4C"],
        "model": "claude-sonnet-4", "enriched_at": "2026-07-13T11:27:00Z",
    },
}

CEDAR_LOGO = "987980ab-9ff3-4819-9d29-3d82f9798b30"
CEDAR_INTERIOR = "52b06b7f-3ca4-45df-bc3f-43f04625fc13"
CEDAR_ROASTING = "5a577e85-8145-40e7-96d3-f36a1657d155"
CEDAR_STOREFRONT = "454ed00f-3624-4499-afc5-cfb0a072ffd7"
CEDAR_HERO = "0de6e142-c5d7-4ba4-a686-c66c91db9b30"
CEDAR_BANNER = "f82fed74-f2fd-4ae4-8e76-3ba3caa7fbff"
CEDAR_BARISTA = "4986a741-4518-4d29-aca1-67c5925717f8"

GUIDELINES_SEED = [
    {
        "slug": "cedar-brand-guidelines",
        "org": 2, "title": "Cedar & Co Brand Guidelines",
        "tagline": "Warmth in every cup",
        "accent_color": "#7A4F2B",
        "logo": CEDAR_LOGO, "cover_image": CEDAR_INTERIOR, "logo_plate": "light",
        "is_client_visible": True, "sort": 1,
        "body": "The complete identity system for Cedar & Co Coffee: palette, typography, logo usage, voice, and photography direction. Maintained by Muster Studio; last reviewed July 2026.",
        "blocks": [
            ("cover", 1, {"statement": "Cedar & Co is a neighborhood roaster with a craft-first story. Everything we make should feel warm, honest, and unhurried."}),
            ("palette", 2, {
                "intro": "Warm naturals anchored by Cedar Brown. Use Cream for backgrounds and reserve Copper for accents and calls to action.",
                "groups": [
                    {"label": "Primary", "swatches": [
                        {"name": "Cedar Brown", "hex": "#7A4F2B", "rgb": "122, 79, 43", "usage": "Wordmark, headers, primary buttons"},
                        {"name": "Cream", "hex": "#F5EFE6", "rgb": "245, 239, 230", "usage": "Backgrounds and cards"},
                        {"name": "Roast Black", "hex": "#2B211A", "rgb": "43, 33, 26", "usage": "Body text"}]},
                    {"label": "Accent", "swatches": [
                        {"name": "Copper", "hex": "#B87333", "rgb": "184, 115, 51", "usage": "Links, highlights, seasonal badges"},
                        {"name": "Leaf Green", "hex": "#5F7A46", "rgb": "95, 122, 70", "usage": "Sustainability messaging only"}]},
                ],
            }),
            ("typography", 3, {
                "intro": "Fraunces carries the brand voice in display sizes; Inter keeps interfaces and body copy quiet and legible.",
                "families": [
                    {"name": "Fraunces", "role": "display", "stack": "'Fraunces', Georgia, serif",
                     "source": "Google Fonts", "weights": [400, 600],
                     "specimen": "Warmth in every cup"},
                    {"name": "Inter", "role": "body", "stack": "'Inter', -apple-system, sans-serif",
                     "source": "Google Fonts", "weights": [400, 500, 700],
                     "specimen": "Small-batch roasting since 2019."},
                ],
                "scale": [
                    {"label": "Display", "sizePx": 56, "lineHeight": 1.05, "weight": 600},
                    {"label": "H1", "sizePx": 36, "lineHeight": 1.15, "weight": 600},
                    {"label": "H2", "sizePx": 24, "lineHeight": 1.25, "weight": 600},
                    {"label": "Body", "sizePx": 16, "lineHeight": 1.6, "weight": 400},
                    {"label": "Caption", "sizePx": 13, "lineHeight": 1.4, "weight": 500},
                ],
            }),
            ("logo", 4, {
                "intro": "The horizontal lockup is the default. Use the reversed version on Cedar Brown or photography.",
                "lockups": [
                    {"fileId": CEDAR_LOGO, "background": "light", "label": "Primary lockup"},
                    {"fileId": CEDAR_LOGO, "background": "dark", "label": "Reversed on Roast Black"},
                    {"fileId": CEDAR_LOGO, "background": "accent", "label": "On Cedar Brown"},
                ],
                "clearSpace": "Keep clear space equal to the height of the C on all sides.",
                "minSize": "Never render the lockup below 120px wide on screen or 30mm in print.",
                "misuse": [
                    "Do not recolor the wordmark outside the approved palette.",
                    "Do not add drop shadows or outlines.",
                    "Do not set the lockup on busy photography without the light plate.",
                ],
            }),
            ("voice", 5, {
                "personality": "A knowledgeable neighbor, not a barista influencer. Cedar & Co speaks plainly about craft and sourcing.",
                "adjectives": ["warm", "honest", "craft-driven", "unhurried"],
                "dos": ["Lead with the growers and the roast.", "Use concrete detail over superlatives.", "Keep sentences short."],
                "donts": ["No coffee puns in headlines.", "No urgency language like limited time.", "Avoid jargon such as third wave."],
                "examples": [
                    {"label": "Menu description", "text": "Guatemala Huehuetenango. Washed, medium roast. Cocoa and red apple."},
                    {"label": "Instagram caption", "text": "New crop from the Vasquez family farm lands Thursday. Come taste what a week off the boat does for brightness."},
                ],
            }),
            ("imagery", 6, {
                "intro": "Natural light, warm tones, working hands. Photography should feel documentary rather than staged.",
                "direction": [
                    "Shoot in available morning light where possible.",
                    "Favor process shots: roasting, pouring, weighing.",
                    "Keep saturation natural; no heavy filters.",
                ],
                "images": [
                    {"fileId": CEDAR_INTERIOR, "caption": "Main room, morning light"},
                    {"fileId": CEDAR_ROASTING, "caption": "Roasting drum mid-batch"},
                    {"fileId": CEDAR_STOREFRONT, "caption": "Storefront before opening"},
                ],
            }),
            ("usage", 7, {
                "intro": "How the identity behaves in the wild.",
                "dos": [
                    {"title": "Cream backgrounds", "body": "Set long-form content on Cream with Roast Black text."},
                    {"title": "Copper for action", "body": "Reserve Copper for links, buttons, and seasonal badges."},
                ],
                "donts": [
                    {"title": "No gradients", "body": "The palette is flat; never blend brand colors."},
                    {"title": "No stacked lockups", "body": "Do not stack the wordmark; use the monogram in tight spaces."},
                ],
            }),
            ("downloads", 8, {
                "intro": "Current production files. Request print-resolution photography from the studio.",
                "items": [
                    {"label": "Primary logo (SVG)", "fileId": CEDAR_LOGO, "kind": "logo"},
                    {"label": "Cafe interior (web)", "fileId": CEDAR_INTERIOR, "kind": "other"},
                    {"label": "Roasting photography (web)", "fileId": CEDAR_ROASTING, "kind": "other"},
                ],
            }),
        ],
    },
    {
        "slug": "cedar-web-style-guide",
        "org": 2, "title": "Cedar & Co Web Style Guide",
        "tagline": "Design language for cedarandco.com",
        "accent_color": "#2F5D50",
        "logo": CEDAR_LOGO, "cover_image": CEDAR_HERO, "logo_plate": "light",
        "is_client_visible": True, "sort": 2,
        "body": "Digital-only rules for cedarandco.com and campaign landing pages. Extends the master brand guidelines with web color, type scale, and imagery crops.",
        "blocks": [
            ("richtext", 1, {"heading": "Scope",
                             "body": "This guide covers cedarandco.com, the loyalty app web views, and campaign landing pages. Print and packaging live in the master brand guidelines."}),
            ("palette", 2, {
                "intro": "Web palette adds a deep green for interactive states and keeps AA contrast on Cream.",
                "groups": [
                    {"label": "Digital", "swatches": [
                        {"name": "Pine", "hex": "#2F5D50", "rgb": "47, 93, 80", "usage": "Interactive states, focus rings"},
                        {"name": "Cedar Brown", "hex": "#7A4F2B", "rgb": "122, 79, 43", "usage": "Primary buttons"},
                        {"name": "Cream", "hex": "#F5EFE6", "rgb": "245, 239, 230", "usage": "Page background"},
                        {"name": "Roast Black", "hex": "#2B211A", "rgb": "43, 33, 26", "usage": "Text"}]},
                ],
            }),
            ("typography", 3, {
                "intro": "Web type scale, 16px base.",
                "families": [
                    {"name": "Fraunces", "role": "display", "stack": "'Fraunces', Georgia, serif",
                     "source": "Google Fonts", "weights": [600], "specimen": "Seasonal menu"},
                    {"name": "Inter", "role": "body", "stack": "'Inter', -apple-system, sans-serif",
                     "source": "Google Fonts", "weights": [400, 500], "specimen": "Order ahead for pickup."},
                ],
                "scale": [
                    {"label": "Hero", "sizePx": 48, "lineHeight": 1.1, "weight": 600},
                    {"label": "Section", "sizePx": 28, "lineHeight": 1.2, "weight": 600},
                    {"label": "Body", "sizePx": 16, "lineHeight": 1.6, "weight": 400},
                ],
            }),
            ("gallery", 4, {
                "intro": "Approved web crops currently in rotation.",
                "images": [
                    {"fileId": CEDAR_HERO, "caption": "Spring menu hero"},
                    {"fileId": CEDAR_INTERIOR, "caption": "About page header"},
                    {"fileId": CEDAR_STOREFRONT, "caption": "Contact page header"},
                ],
            }),
        ],
    },
    {
        "slug": "cedar-social-media-kit",
        "org": 2, "title": "Cedar & Co Social Media Kit",
        "tagline": "Templates and rules for social",
        "accent_color": "#B87333",
        "logo": CEDAR_LOGO, "cover_image": CEDAR_ROASTING, "logo_plate": "dark",
        "is_client_visible": False, "sort": 3,
        "body": "Internal kit for the studio social team. Not client-visible: contains working notes and unapproved crops.",
        "blocks": [
            ("richtext", 1, {"heading": "Working notes",
                             "body": "Grid alternates process photography and menu graphics. Captions follow the voice rules in the master guidelines. Tag the roastery location on process posts."}),
            ("imagery", 2, {
                "intro": "Working set for July. Barista frames are NOT cleared until model releases land.",
                "direction": ["Square crops center on hands and product.", "Stories use the vertical roasting frames."],
                "images": [
                    {"fileId": CEDAR_ROASTING, "caption": "Cleared for use"},
                    {"fileId": CEDAR_BARISTA, "caption": "HOLD: release pending"},
                    {"fileId": CEDAR_BANNER, "caption": "Loyalty launch tile, copy pending"},
                ],
            }),
            ("downloads", 3, {
                "intro": "Templates and source files.",
                "items": [
                    {"label": "Primary logo (SVG)", "fileId": CEDAR_LOGO, "kind": "logo"},
                    {"label": "Loyalty banner source", "fileId": CEDAR_BANNER, "kind": "template"},
                ],
            }),
        ],
    },
]


def upsert(collection, filt_query, body, label, stats):
    st, resp = req(f"/items/{collection}?{filt_query}&limit=1&fields=id")
    if st == 200 and resp.get("data"):
        stats["skipped"] += 1
        return resp["data"][0]["id"]
    st2, resp2 = req(f"/items/{collection}", "POST", body)
    if st2 in (200, 204):
        stats["created"] += 1
        return (resp2.get("data") or {}).get("id")
    stats["failed"] += 1
    print(f"  {collection} {label}: FAILED {st2}", json.dumps(resp2)[:300])
    return None


def seed_collections_items():
    stats = {"created": 0, "skipped": 0, "failed": 0}
    slug_to_id = {}
    for slug, org, name, desc, cv, sort in DAM_COLLECTIONS_SEED:
        rid = upsert(
            "dam_collections", f"filter[slug][_eq]={slug}",
            {"slug": slug, "org": org, "name": name, "description": desc,
             "is_client_visible": cv, "sort": sort},
            slug, stats)
        if rid:
            slug_to_id[slug] = rid
    print(f"dam_collections: created {stats['created']} / skipped {stats['skipped']} / failed {stats['failed']}")
    return slug_to_id, stats["failed"] == 0


def seed_assets(slug_to_id):
    stats = {"created": 0, "skipped": 0, "failed": 0}
    jstats = {"created": 0, "skipped": 0, "failed": 0}
    for row in ASSETS_SEED:
        (fid, org, key, title, status, ai_state, coll_slugs, meta, tags, colors,
         desc, alt, seo, credit, rights_note, rights_expiry, dls, created) = row
        mime, w, h, size = meta
        body = {
            "org": org,
            "s3_uri": f"s3://agency-directus-assets/{key}",
            "bucket": "agency-directus-assets",
            "key": key,
            "checksum": hashlib.md5(key.encode()).hexdigest(),
            "mime": mime, "width": w, "height": h, "size_bytes": size,
            "exif": {"demo_source_file": fid,
                     "note": "Seeded demo asset; media mirrors this directus_files id"},
            "title": title, "description": desc, "alt_text": alt,
            "seo_filename": seo, "tags": tags, "dominant_colors": colors,
            "status": status, "ai_state": ai_state,
            "ai_suggestions": AI_SUGGESTIONS.get(key),
            "rights_note": rights_note, "rights_expiry": rights_expiry,
            "credit": credit, "download_count": dls,
            "date_created": created,
        }
        aid = upsert(
            "dam_assets",
            "filter[bucket][_eq]=agency-directus-assets&filter[key][_eq]=" + urllib.parse.quote(key, safe=""),
            body, key, stats)
        if not aid:
            continue
        for slug in coll_slugs:
            cid = slug_to_id.get(slug)
            if not cid:
                continue
            upsert(
                "dam_assets_collections",
                f"filter[dam_assets_id][_eq]={aid}&filter[dam_collections_id][_eq]={cid}",
                {"dam_assets_id": aid, "dam_collections_id": cid},
                f"{key}->{slug}", jstats)
    print(f"dam_assets: created {stats['created']} / skipped {stats['skipped']} / failed {stats['failed']}")
    print(f"dam_assets_collections: created {jstats['created']} / skipped {jstats['skipped']} / failed {jstats['failed']}")
    return stats["failed"] == 0 and jstats["failed"] == 0


def backdate_assets():
    """The date-created special overrides the create payload, stamping run time.
    Backdate seeded rows to their intended dates so the library reads as a
    6-month-old archive. Idempotent: PATCHes only rows whose date part differs
    from the seed table (rows this script created; add-only otherwise)."""
    intended = {row[2]: row[17] for row in ASSETS_SEED}
    st, resp = req("/items/dam_assets?fields=id,key,date_created&limit=500"
                   "&filter[bucket][_eq]=agency-directus-assets")
    if st != 200:
        print("backdate: list failed", st)
        return False
    patched = skipped = failed = 0
    for row in resp.get("data", []):
        want = intended.get(row.get("key"))
        if not want:
            continue
        have = (row.get("date_created") or "")[:10]
        if have == want[:10]:
            skipped += 1
            continue
        st2, resp2 = req(f"/items/dam_assets/{row['id']}", "PATCH", {"date_created": want})
        if st2 in (200, 204):
            patched += 1
        else:
            failed += 1
            print(f"  backdate {row['key']}: FAILED {st2}", json.dumps(resp2)[:200])
    print(f"dam_assets backdate: patched {patched} / skipped {skipped} / failed {failed}")
    return failed == 0


def seed_guidelines():
    gstats = {"created": 0, "skipped": 0, "failed": 0}
    bstats = {"created": 0, "skipped": 0, "failed": 0}
    for g in GUIDELINES_SEED:
        body = {k: v for k, v in g.items() if k != "blocks"}
        gid = upsert("dam_guidelines", f"filter[slug][_eq]={g['slug']}", body, g["slug"], gstats)
        if not gid:
            continue
        for btype, sort, data in g["blocks"]:
            upsert(
                "dam_guideline_blocks",
                f"filter[guideline][_eq]={gid}&filter[type][_eq]={btype}&filter[sort][_eq]={sort}",
                {"guideline": gid, "type": btype, "sort": sort, "data": data},
                f"{g['slug']}#{btype}", bstats)
    print(f"dam_guidelines: created {gstats['created']} / skipped {gstats['skipped']} / failed {gstats['failed']}")
    print(f"dam_guideline_blocks: created {bstats['created']} / skipped {bstats['skipped']} / failed {bstats['failed']}")
    return gstats["failed"] == 0 and bstats["failed"] == 0


# --------------------------------------------------------------------------
# 3. Verification probes (portal read shapes, session tokens)
# --------------------------------------------------------------------------

ASSET_FIELDS = ("id,org.id,org.name,s3_uri,bucket,key,checksum,mime,width,height,size_bytes,"
                "title,description,alt_text,seo_filename,tags,dominant_colors,status,ai_state,"
                "ai_suggestions,rights_note,rights_expiry,credit,download_count,edits,"
                "date_created,date_updated,collections.dam_collections_id.id,"
                "collections.dam_collections_id.name")
CLIENT_ASSET_FIELDS = ("id,title,description,alt_text,seo_filename,tags,mime,width,height,"
                       "size_bytes,status,credit,date_updated,collections.dam_collections_id.id,"
                       "collections.dam_collections_id.name")
CLIENT_COLLECTION_FIELDS = "id,name,slug,description"
CLIENT_FILE_FIELDS = "id,bucket,key,seo_filename,status,org"
EMP_COLLECTION_FIELDS = "id,org.id,org.name,name,slug,description,is_client_visible"
GUIDELINE_FIELDS = ("id,org.id,org.name,title,body,sort,is_client_visible,slug,tagline,"
                    "accent_color,cover_image,logo,logo_plate,blocks.id,blocks.type,"
                    "blocks.sort,blocks.data")

# Public demo credentials (shown on the musterr.dev landing page; not secrets).
DEMO_LOGINS = {
    "employee": {"email": "demo@muster.dev", "password": "muster-demo"},
    "client": {"email": "client@muster.dev", "password": "muster-demo"},
}


def login(kind):
    st, resp = req("/auth/login", "POST", DEMO_LOGINS[kind])
    if st != 200:
        print(f"  VERIFY: {kind} login FAILED {st}")
        return None
    return resp["data"]["access_token"]


def probe(label, path, token, expect_min=1):
    st, resp = req(path, token=token)
    rows = resp.get("data")
    n = len(rows) if isinstance(rows, list) else (1 if rows else 0)
    ok = st == 200 and n >= expect_min
    print(f"  {'PASS' if ok else 'FAIL'} {label}: HTTP {st}, rows {n}")
    if not ok:
        print("    ", json.dumps(resp)[:300])
    return ok


def verify():
    ok = True
    emp = login("employee")
    cli = login("client")
    if not emp or not cli:
        return False

    print("VERIFY employee (demo@muster.dev), exact portal read shapes:")
    ok &= probe("dam_assets ASSET_FIELDS sort=-date_created",
                f"/items/dam_assets?fields={ASSET_FIELDS}&limit=500&sort=-date_created", emp, 30)
    ok &= probe("dam_collections employee fields sort=sort",
                f"/items/dam_collections?fields={EMP_COLLECTION_FIELDS}&limit=200&sort=sort", emp, 17)
    ok &= probe("dam_guidelines GUIDELINE_FIELDS sort=sort",
                f"/items/dam_guidelines?fields={GUIDELINE_FIELDS}&limit=200&sort=sort", emp, 3)
    ok &= probe("dam review queue (ai_state=suggested)",
                f"/items/dam_assets?fields={ASSET_FIELDS}&filter[ai_state][_eq]=suggested&limit=500&sort=-date_created",
                emp, 5)

    print("VERIFY client (client@muster.dev, org 2), exact portal read shapes:")
    ok &= probe("brand-assets route: client_approved org 2 CLIENT_ASSET_FIELDS",
                f"/items/dam_assets?fields={CLIENT_ASSET_FIELDS}&limit=500&sort=-date_created"
                "&filter[org][_eq]=2&filter[status][_in]=client_approved", cli, 5)
    ok &= probe("brand-assets route: collections org 2 CLIENT_COLLECTION_FIELDS",
                f"/items/dam_collections?fields={CLIENT_COLLECTION_FIELDS}&limit=200&sort=sort"
                "&filter[org][_eq]=2", cli, 4)
    ok &= probe("guidelines route: GUIDELINE_FIELDS (route re-filters to org 2 visible)",
                f"/items/dam_guidelines?fields={GUIDELINE_FIELDS}&limit=200&sort=sort", cli, 3)
    st, resp = req("/items/dam_assets?filter[org][_eq]=2&filter[status][_eq]=client_approved"
                   "&limit=1&fields=id", token=cli)
    if st == 200 and resp.get("data"):
        aid = resp["data"][0]["id"]
        ok &= probe("client file route: CLIENT_FILE_FIELDS single asset",
                    f"/items/dam_assets/{aid}?fields={CLIENT_FILE_FIELDS}", cli, 1)

    print("VERIFY admin GraphQL list shapes:")
    gql = {"query": "{ dam_assets(limit: 3) { id title status org { id name } "
                    "collections { dam_collections_id { id name } } } "
                    "dam_collections(limit: 3) { id name slug is_client_visible } "
                    "dam_guidelines(filter: { org: { id: { _eq: 2 } } }, sort: [\"sort\"]) "
                    "{ id title slug is_client_visible blocks { id type sort } } }"}
    st, resp = req("/graphql", "POST", gql)
    errs = resp.get("errors")
    d = resp.get("data") or {}
    n_assets = len(d.get("dam_assets") or [])
    n_colls = len(d.get("dam_collections") or [])
    n_guides = len(d.get("dam_guidelines") or [])
    blocks_total = sum(len(g.get("blocks") or []) for g in (d.get("dam_guidelines") or []))
    gok = st == 200 and not errs and n_assets == 3 and n_colls == 3 and n_guides == 3
    print(f"  {'PASS' if gok else 'FAIL'} graphql: HTTP {st}, dam_assets {n_assets}, "
          f"dam_collections {n_colls}, dam_guidelines(org 2) {n_guides}, blocks {blocks_total}")
    if errs:
        print("    ", json.dumps(errs)[:400])
    ok &= gok
    return ok


def counts():
    for name in ["dam_assets", "dam_collections", "dam_assets_collections",
                 "dam_guidelines", "dam_guideline_blocks", "dam_share_links", "dam_render_jobs"]:
        st, resp = req(f"/items/{name}?aggregate[count]=id")
        n = (resp.get("data") or [{}])[0].get("count", {})
        n = n.get("id") if isinstance(n, dict) else n
        print(f"  {name}: {n} rows")


def main():
    print("== run2-P3-dam: schema ==")
    ok = ensure_collections()
    ok &= ensure_relations()
    ok &= ensure_permissions()
    print("== run2-P3-dam: seed ==")
    slug_to_id, ok2 = seed_collections_items()
    ok &= ok2
    ok &= seed_assets(slug_to_id)
    ok &= backdate_assets()
    ok &= seed_guidelines()
    print("== run2-P3-dam: totals ==")
    counts()
    print("== run2-P3-dam: verify ==")
    vok = verify()
    print(f"== run2-P3-dam: {'ALL OK' if (ok and vok) else 'ERRORS PRESENT'} "
          f"(seed {'ok' if ok else 'errors'}, verify {'pass' if vok else 'fail'}) ==")


if __name__ == "__main__":
    main()
