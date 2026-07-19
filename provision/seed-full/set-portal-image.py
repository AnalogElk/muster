#!/usr/bin/env python3
"""Key-scoped edit of ~/elk-os/.env: point PORTAL_IMAGE at the freshly built
portal image and ensure ELK_OS_WITH_MOCKS=true so bin/elk-os keeps the mocks
overlay in its file set. Only these two NON-SECRET keys are read or printed;
no other line is touched or rendered. Idempotent."""
import os

ENV_PATH = os.path.expanduser("~/elk-os/.env")
NEW_IMAGE = "elk-os/portal:run2-csp"

with open(ENV_PATH) as f:
    lines = f.read().splitlines()

out = []
seen_image = False
seen_mocks = False
old_image = None
old_mocks = None
for line in lines:
    stripped = line.strip()
    if stripped.startswith("PORTAL_IMAGE="):
        old_image = stripped.partition("=")[2]
        out.append(f"PORTAL_IMAGE={NEW_IMAGE}")
        seen_image = True
    elif stripped.startswith("ELK_OS_WITH_MOCKS="):
        old_mocks = stripped.partition("=")[2]
        out.append("ELK_OS_WITH_MOCKS=true")
        seen_mocks = True
    else:
        out.append(line)

if not seen_image:
    out.append(f"PORTAL_IMAGE={NEW_IMAGE}")
if not seen_mocks:
    out.append("ELK_OS_WITH_MOCKS=true")

with open(ENV_PATH, "w") as f:
    f.write("\n".join(out) + "\n")

print(f"PORTAL_IMAGE: {old_image or '<absent>'} -> {NEW_IMAGE}")
print(f"ELK_OS_WITH_MOCKS: {old_mocks or '<absent>'} -> true")
