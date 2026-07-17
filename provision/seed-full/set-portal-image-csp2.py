#!/usr/bin/env python3
"""Key-scoped edit of ~/elk-os/.env: point PORTAL_IMAGE at the run2-csp2
portal image (images.remotePatterns + SVG fix). Only this NON-SECRET key is
read or printed; no other line is touched or rendered. Idempotent."""
import os

ENV_PATH = os.path.expanduser("~/elk-os/.env")
NEW_IMAGE = "elk-os/portal:run2-csp2"

with open(ENV_PATH) as f:
    lines = f.read().splitlines()

out = []
seen_image = False
old_image = None
for line in lines:
    stripped = line.strip()
    if stripped.startswith("PORTAL_IMAGE="):
        old_image = stripped.partition("=")[2]
        out.append(f"PORTAL_IMAGE={NEW_IMAGE}")
        seen_image = True
    else:
        out.append(line)

if not seen_image:
    out.append(f"PORTAL_IMAGE={NEW_IMAGE}")

with open(ENV_PATH, "w") as f:
    f.write("\n".join(out) + "\n")

print(f"PORTAL_IMAGE: {old_image or '<absent>'} -> {NEW_IMAGE}")
