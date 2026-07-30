#!/usr/bin/env python3
"""Mock-service data fix: point the 7 brand-logo dam_assets rows at PNG keys.

Why: the DAM tile pipeline only renders raster keys. app/api/portal/dam/thumb
routes any key failing RASTER_EXT (lib/dam/thumbnail.ts:14, jpg/png/webp/...)
into a 302 redirect to the presigned original, and with the on-box S3 mock the
presigned host (agency-directus-assets.elk-os-mocks) is only resolvable inside
the docker network, so a browser can never follow it: .svg keys are broken
tiles FOREVER, .png keys render (server-side sharp resize, 200 image/webp).

The PNG objects are 512x512 renditions of the same curated brand SVGs
(render-logo-pngs.js) and already sit in the mock data dir at the new keys.
Updates per row: key, s3_uri, mime, width, height, size_bytes, checksum, and
seo_filename when it carries a .svg extension. Idempotent: rows whose key
already ends in .png are skipped.
"""
import hashlib
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client.directus_client import call, load_env  # noqa: E402

BASE = "https://cms.musterr.dev"
BUCKET_DIR = os.path.expanduser("~/elk-os/mocks/data/agency-directus-assets")


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(method, path, params=None, body=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    st, raw, err = call(method, url, data=data, headers=headers, timeout=30)
    if err is not None:
        raise err
    return json.loads(raw)


rows = req("GET", "/items/dam_assets", {
    "filter": json.dumps({"key": {"_ends_with": ".svg"}}),
    "fields": "id,key,bucket,mime,title,seo_filename",
    "limit": "-1",
})["data"]

patched = skipped = missing = 0
for row in rows:
    new_key = row["key"][:-4] + ".png"
    obj = os.path.join(BUCKET_DIR, new_key)
    if not os.path.isfile(obj):
        missing += 1
        print(f"  MISSING object for {new_key}; row {row['id']} left untouched")
        continue
    data = open(obj, "rb").read()
    payload = {
        "key": new_key,
        "s3_uri": f"s3://{row['bucket']}/{new_key}",
        "mime": "image/png",
        "width": 512,
        "height": 512,
        "size_bytes": len(data),
        "checksum": hashlib.md5(data).hexdigest(),
    }
    seo = row.get("seo_filename")
    if seo and seo.endswith(".svg"):
        payload["seo_filename"] = seo[:-4] + ".png"
    req("PATCH", f"/items/dam_assets/{row['id']}", body=payload)
    patched += 1
    print(f"  patched {row['title']!r}: {row['key']} -> {new_key}")

already = req("GET", "/items/dam_assets", {
    "filter": json.dumps({"key": {"_ends_with": ".png"}}),
    "fields": "id", "limit": "-1"})["data"]
print(f"dam_assets logo keys: patched {patched} / skipped {skipped} / missing-object {missing}; "
      f"png-key rows now {len(already)}")

svg_left = req("GET", "/items/dam_assets", {
    "filter": json.dumps({"key": {"_ends_with": ".svg"}}),
    "fields": "id,key", "limit": "-1"})["data"]
print(f"VERIFY svg-key rows remaining: {len(svg_left)}")
