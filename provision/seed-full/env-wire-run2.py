#!/usr/bin/env python3
"""Wire the run2 image tag + mocks overlay flag into the elk-os env file.

- Backs the file up first (timestamped copy, add-only).
- Rewrites ONLY these keys, appending them if absent:
    PORTAL_IMAGE=elk-os/portal:run2-csp
    ELK_OS_WITH_MOCKS=true
- Never prints any value from the file; output is key names + changed/unchanged.

Run with ROLLBACK=1 to point PORTAL_IMAGE back at the previous tag
(elk-os/portal:ae-09c1d485) and set ELK_OS_WITH_MOCKS=false.
"""
import os
import shutil
import time

PATH = os.path.join(os.path.expanduser("~"), "elk-os", ".env")
ROLLBACK = os.environ.get("ROLLBACK") == "1"

TARGETS = {
    "PORTAL_IMAGE": "elk-os/portal:ae-09c1d485" if ROLLBACK else "elk-os/portal:run2-csp",
    "ELK_OS_WITH_MOCKS": "false" if ROLLBACK else "true",
}

backup = PATH + ".bak-run2-" + time.strftime("%Y%m%d%H%M%S")
shutil.copy2(PATH, backup)
print("backup written:", os.path.basename(backup))

with open(PATH) as f:
    lines = f.readlines()

seen = set()
out = []
changed = []
for line in lines:
    stripped = line.strip()
    key = stripped.partition("=")[0].strip() if "=" in stripped and not stripped.startswith("#") else None
    if key in TARGETS:
        seen.add(key)
        new_line = f"{key}={TARGETS[key]}\n"
        if line != new_line:
            changed.append(key)
        out.append(new_line)
    else:
        out.append(line)

for key, value in TARGETS.items():
    if key not in seen:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key}={value}\n")
        changed.append(key + " (appended)")

with open(PATH, "w") as f:
    f.writelines(out)

print("changed:", ", ".join(changed) if changed else "nothing (already wired)")
for key in TARGETS:
    print(f"  {key} -> {TARGETS[key]}")
