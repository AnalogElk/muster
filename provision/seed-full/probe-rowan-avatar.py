#!/usr/bin/env python3
"""Probe Rowan Ashford's (client@muster.dev) avatar: file id, type, size,
public (unauthenticated) fetchability, and the portal optimizer verdict.
Prints demo content metadata only. Never prints the token."""
import json
import os
import urllib.request
import urllib.error

BASE = "https://cms.musterr.dev"


def load_env():
    env = {}
    path = os.path.join(os.path.expanduser("~"), "elk-os", ".env")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def get(path, auth=True):
    req = urllib.request.Request(BASE + path)
    if auth:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


users = get("/users?filter[email][_eq]=client@muster.dev&fields=id,first_name,last_name,avatar,role")["data"]
if not users:
    print("NO client@muster.dev user found")
    raise SystemExit(1)
u = users[0]
print("user:", u["id"], u["first_name"], u["last_name"], "avatar:", u["avatar"])

if not u["avatar"]:
    print("AVATAR IS NULL")
    raise SystemExit(0)

f = get(f"/files/{u['avatar']}?fields=id,type,filesize,filename_download,width,height,folder")["data"]
print("file:", json.dumps(f))

# Unauthenticated fetch of the asset (what the browser / optimizer does)
req = urllib.request.Request(BASE + "/assets/" + u["avatar"])
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        print("public asset GET:", r.status, "content-type:", r.headers.get("Content-Type"), "bytes:", len(body))
except urllib.error.HTTPError as e:
    print("public asset GET FAILED:", e.code, e.reason)

# The exact optimizer URL the portal browser requests
import urllib.parse
opt = ("https://app.musterr.dev/_next/image?url="
       + urllib.parse.quote(BASE + "/assets/" + u["avatar"], safe="")
       + "&w=64&q=75")
req = urllib.request.Request(opt)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("optimizer GET:", r.status, "content-type:", r.headers.get("Content-Type"))
except urllib.error.HTTPError as e:
    print("optimizer GET FAILED:", e.code, e.reason, "body:", e.read()[:120].decode("utf-8", "replace"))
