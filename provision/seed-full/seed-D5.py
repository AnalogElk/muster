#!/usr/bin/env python3
"""
D5 seed: domain-analytics-ai for the Muster demo (cms.musterr.dev).

Seeds:
  1. os_activity_log   ~173 new rows (workflow family incl. pr_merged + portal family)
  2. os_token_usage    56 rows (8 slugs x 2026-02..2026-07 + all_time)
  3. os_seo_snapshots  182 rows (14 urls x 13 weekly snapshots)

os_insights is seeded by the STANDALONE insights-seed.py (range keys shift with
the run day, so the Verify phase re-runs that script on the screenshot day).

Rules honored: add-only, idempotent upserts by natural key, deterministic
timestamps (fixed anchor 2026-07-16T00:00:00Z + seeded RNG keyed on stable
strings), no em dashes in any seeded content, no secrets printed.

Upsert keys:
  os_activity_log  (verb, target_id, timestamp)
  os_token_usage   (project_slug, period)
  os_seo_snapshots (url, collected_at)
"""
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Access (brief recipe: env read INSIDE the script, token never printed)
# ---------------------------------------------------------------------------

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

ENV = load_env()
BASE = "https://cms.musterr.dev"
TOKEN = ENV["DIRECTUS_ADMIN_TOKEN"]

def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    last = None
    for attempt, pause in enumerate((0, 2, 5, 10)):
        if pause:
            time.sleep(pause)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                continue
            detail = e.read().decode()[:300]
            raise RuntimeError(f"{method} {path} -> {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            last = e
            continue
    raise RuntimeError(f"{method} {path} failed after retries: {last}")

def get(path):
    return request("GET", path)

def post(path, body):
    return request("POST", path, body)

def patch(path, body):
    return request("PATCH", path, body)

# ---------------------------------------------------------------------------
# Determinism helpers
# ---------------------------------------------------------------------------

SEED = 20260716
ANCHOR = datetime(2026, 7, 16, 0, 0, 0, tzinfo=timezone.utc)  # fixed, never "now"

def rnd(key):
    """A fresh RNG keyed on the master seed + a stable string. Regenerates
    byte-identical draws regardless of call order or row-set changes."""
    return random.Random(f"{SEED}:{key}")

def clean(s):
    """No em dashes in anything we write."""
    return (s or "").replace("—", "-").replace("–", "-").strip()

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def norm_ts(raw):
    """Normalize a Directus timestamp to a comparable key (second precision)."""
    if not raw:
        return ""
    return raw.replace("Z", "").split(".")[0]

# ---------------------------------------------------------------------------
# Gate: F1 fields must exist (poll up to 10x30s)
# ---------------------------------------------------------------------------

def gate():
    for attempt in range(10):
        ok = True
        for path in ("/fields/os_activity_log/organization", "/fields/os_token_usage/est_cost_usd"):
            try:
                get(path)
            except RuntimeError:
                ok = False
        if ok:
            print("gate: F1 fields present")
            return
        print(f"gate: attempt {attempt + 1} failed, waiting 30s")
        time.sleep(30)
    raise SystemExit("gate: F1 fields absent after polling")

# ---------------------------------------------------------------------------
# Step 1: os_activity_log
# ---------------------------------------------------------------------------

DEMO_USER = "257a4b75-deff-476d-953d-1898c57f6684"
ADMIN_USER = "34d67d59-16c3-41c4-9efb-7fd51a216460"
MUSTER_PROJECT = "0ef5827c-924d-4c2a-a769-d9d7c84097e1"

def pick_actor(r, team):
    x = r.random()
    if x < 0.30:
        return ADMIN_USER
    if x < 0.80 and team:
        return team[int(r.random() * len(team))]
    return DEMO_USER

def weighted_day(r):
    """Day offset 1..90 weighted toward recent weeks."""
    pop = list(range(1, 91))
    weights = [3.0 if d <= 14 else 2.0 if d <= 28 else 1.0 if d <= 56 else 0.5 for d in pop]
    return r.choices(pop, weights=weights, k=1)[0]

def seed_activity_log():
    # Existing natural keys
    existing = get("/items/os_activity_log?fields=verb,target_id,timestamp&limit=-1")["data"]
    have = {(e["verb"], e["target_id"], norm_ts(e["timestamp"])) for e in existing}

    # Linkable rows (all sorted for determinism)
    projects = get("/items/os_projects?fields=id,name,organization&limit=-1&sort=id")["data"]
    proj_by_id = {p["id"]: p for p in projects}
    synthetic = sorted(p["id"] for p in projects if p["id"] != MUSTER_PROJECT)

    tasks = get("/items/os_tasks?fields=id,name,project&limit=-1&sort=id")["data"]
    syn_tasks = [t for t in tasks if t.get("project") in set(synthetic)]

    repos = get("/items/repositories?fields=id,name,project_id&limit=-1&sort=id")["data"]
    repo_proj = {r["id"]: r.get("project_id") for r in repos}
    releases = get("/items/releases?fields=id,version,title,repository_id&limit=-1&sort=id")["data"]
    linked_releases = [r for r in releases if repo_proj.get(r.get("repository_id"))]

    users = get("/users?fields=id,email&limit=-1")["data"]
    team = sorted(u["id"] for u in users if u.get("email", "").endswith("@team.musterr.dev"))
    email_of = {u["id"]: u.get("email", "") for u in users}

    orgs = get("/items/organizations?fields=id,name&limit=-1&sort=id")["data"]
    org_name = {o["id"]: clean(o["name"]) for o in orgs}
    org_ids = sorted(o["id"] for o in orgs)

    events = []

    def add(verb, target_collection, target_id, ts, actor, organization=None,
            project=None, metadata=None):
        events.append({
            "verb": verb,
            "target_collection": target_collection,
            "target_id": str(target_id),
            "timestamp": iso(ts),
            "actor": actor,
            "organization": organization,
            "project": project,
            "metadata": metadata or {},
        })

    # -- (a) WORKFLOW family ------------------------------------------------
    def task_event(verb, count):
        for i in range(count):
            r = rnd(f"wf:{verb}:{i}")
            t = syn_tasks[int(r.random() * len(syn_tasks))]
            proj = proj_by_id[t["project"]]
            day = weighted_day(r)
            ts = ANCHOR - timedelta(days=day) + timedelta(
                hours=r.randrange(8, 19), minutes=5 * r.randrange(0, 12))
            meta = {"name": clean(t["name"])}
            if verb == "status_changed":
                frm, to = r.choice([("pending", "in_progress"), ("in_progress", "in_review"),
                                    ("in_review", "completed"), ("pending", "active")])
                meta.update({"from": frm, "to": to})
            add(verb, "os_tasks", t["id"], ts, pick_actor(r, team),
                organization=proj["organization"], project=proj["id"], metadata=meta)

    task_event("created", 32)
    task_event("completed", 28)
    task_event("status_changed", 6)

    for i in range(6):  # update_posted -> project target
        r = rnd(f"wf:update_posted:{i}")
        pid = synthetic[int(r.random() * len(synthetic))]
        proj = proj_by_id[pid]
        day = weighted_day(r)
        ts = ANCHOR - timedelta(days=day) + timedelta(hours=r.randrange(9, 18), minutes=5 * r.randrange(0, 12))
        add("update_posted", "os_projects", pid, ts, pick_actor(r, team),
            organization=proj["organization"], project=pid,
            metadata={"name": f"Status update for {clean(proj['name'])}"})

    def release_event(verb, count):
        for i in range(count):
            r = rnd(f"wf:{verb}:{i}")
            rel = linked_releases[int(r.random() * len(linked_releases))]
            pid = repo_proj[rel["repository_id"]]
            proj = proj_by_id[pid]
            day = weighted_day(r)
            ts = ANCHOR - timedelta(days=day) + timedelta(hours=r.randrange(9, 18), minutes=5 * r.randrange(0, 12))
            add(verb, "releases", rel["id"], ts, pick_actor(r, team),
                organization=proj["organization"], project=pid,
                metadata={"name": clean(rel["title"]), "version": clean(rel["version"])})

    release_event("shipped", 6)
    release_event("deployed", 5)

    PR_TITLES = [
        "fix: booking double-submit guard", "feat: menu photography CDN swap",
        "feat: wholesale pricing tiers", "chore: dependency bumps",
        "fix: schedule timezone drift", "feat: grant intake step three",
        "feat: reservations SMS reminders", "fix: gallery lazy-load flicker",
        "feat: practice-area schema markup", "perf: image pipeline tuning",
        "fix: waitlist race condition", "feat: case study CMS fields",
    ]
    for i in range(10):  # pr_merged -> project target (chart series 'prs')
        r = rnd(f"wf:pr_merged:{i}")
        pid = synthetic[int(r.random() * len(synthetic))]
        proj = proj_by_id[pid]
        day = weighted_day(r)
        ts = ANCHOR - timedelta(days=day) + timedelta(hours=r.randrange(9, 18), minutes=5 * r.randrange(0, 12))
        title = PR_TITLES[int(r.random() * len(PR_TITLES))]
        add("pr_merged", "os_projects", pid, ts, pick_actor(r, team),
            organization=proj["organization"], project=pid,
            metadata={"name": f"{title} (#{r.randrange(20, 240)})"})

    # -- (b) PORTAL family ---------------------------------------------------
    DEVICES = [
        ("desktop", "Chrome", "macOS",
         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        ("desktop", "Edge", "Windows",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"),
        ("desktop", "Firefox", "Windows",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0"),
        ("mobile", "Safari", "iOS",
         "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"),
        ("mobile", "Chrome", "Android",
         "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"),
    ]
    PAGES = [
        "/client-portal", "/client-portal/projects", "/client-portal/invoices",
        "/client-portal/files", "/client-portal/analytics", "/client-portal/updates",
        "/client-portal/deliverables", "/client-portal/tickets", "/client-portal/kb",
    ]
    REFERRERS = [None, None, "https://www.google.com/", "https://musterr.dev/"]

    def portal_actor(r):
        return DEMO_USER if r.random() < 0.7 else ADMIN_USER

    def session_hex(r):
        return "".join(r.choice("0123456789abcdef") for _ in range(32))

    logins = []
    for i in range(24):
        r = rnd(f"portal:client_login:{i}")
        actor = portal_actor(r)
        org = org_ids[int(r.random() * len(org_ids))]
        day = weighted_day(r)
        ts = ANCHOR - timedelta(days=day) + timedelta(hours=r.randrange(7, 22), minutes=r.randrange(0, 60))
        device = DEVICES[int(r.random() * len(DEVICES))]
        logins.append((ts, actor, org, r, device))

    seen_first = set()
    for ts, actor, org, r, device in sorted(logins, key=lambda x: x[0]):
        first = (actor, org) not in seen_first
        seen_first.add((actor, org))
        add("client_login", "directus_users", actor, ts, actor, organization=org, metadata={
            "session_id": session_hex(r),
            "ip_address": f"203.0.113.{r.randrange(1, 255)}",
            "user_agent": device[3],
            "device_type": device[0],
            "browser": device[1],
            "os": device[2],
            "is_first_login": first,
            "email": email_of.get(actor, ""),
            "org_name": org_name.get(org, ""),
        })

    for i in range(41):
        r = rnd(f"portal:page_view:{i}")
        actor = portal_actor(r)
        org = org_ids[int(r.random() * len(org_ids))]
        day = weighted_day(r)
        ts = ANCHOR - timedelta(days=day) + timedelta(hours=r.randrange(7, 22), minutes=r.randrange(0, 60))
        device = DEVICES[int(r.random() * len(DEVICES))]
        add("page_view", "directus_users", actor, ts, actor, organization=org, metadata={
            "session_id": session_hex(r),
            "path": PAGES[int(r.random() * len(PAGES))],
            "referrer": REFERRERS[int(r.random() * len(REFERRERS))],
            "device_type": device[0],
            "email": email_of.get(actor, ""),
            "org_name": org_name.get(org, ""),
        })

    EDIT_FIELDS = [["status"], ["description"], ["due_date"], ["name", "description"], ["status", "points"]]
    for i in range(15):
        r = rnd(f"portal:client_edit:{i}")
        actor = portal_actor(r)
        t = syn_tasks[int(r.random() * len(syn_tasks))]
        proj = proj_by_id[t["project"]]
        org = proj["organization"]
        day = weighted_day(r)
        ts = ANCHOR - timedelta(days=day) + timedelta(hours=r.randrange(7, 22), minutes=r.randrange(0, 60))
        fields = EDIT_FIELDS[int(r.random() * len(EDIT_FIELDS))]
        add("client_edit", "os_tasks", t["id"], ts, actor, organization=org, metadata={
            "session_id": session_hex(r),
            "action": "updated",
            "target_collection": "os_tasks",
            "target_id": t["id"],
            "fields_changed": fields,
            "resource_name": clean(t["name"]),
            "email": email_of.get(actor, ""),
            "org_name": org_name.get(org, ""),
        })

    # -- create missing ------------------------------------------------------
    created = skipped = 0
    seen_batch = set()
    for ev in events:
        key = (ev["verb"], ev["target_id"], norm_ts(ev["timestamp"]))
        if key in have or key in seen_batch:
            skipped += 1
            continue
        seen_batch.add(key)
        post("/items/os_activity_log", ev)
        created += 1
    print(f"os_activity_log: created {created} / updated 0 / skipped {skipped}")
    return created

# ---------------------------------------------------------------------------
# Step 2: os_token_usage
# ---------------------------------------------------------------------------

SLUGS = [
    ("cedar-web", "Cedar & Co Website", "430df3e9-7f6d-4369-81cf-d9e5dc0fab00"),
    ("harbor-app", "Harbor Class Booking", "d16e4ef5-a11c-4165-8f5b-2a79fa1a1e51"),
    ("northlight-brand", "Northlight Brand", "91528c06-daee-41eb-b614-363afb1eb531"),
    ("sterling-reservations", "Sterling Reservations", "cd1eae58-ec99-4444-bbe4-ae6ab9370cea"),
    ("bloom-shopify", "Bloom Shopify", "3d5677cf-af08-4df2-a29a-6a4925ab9268"),
    ("vellum-portfolio", "Vellum Portfolio", "4ae1d3fa-92fb-443d-86c8-4636df95e41c"),
    ("meridian-grant-portal", "Meridian Grant Portal", "c6581803-8fe8-43e7-bb56-4f1e758e2a25"),
    ("muster", "Muster", "0ef5827c-924d-4c2a-a769-d9d7c84097e1"),
]
MONTHS = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]

def month_row(slug, label, project, period):
    r = rnd(f"tok:{slug}:{period}")
    input_t = r.randrange(2_000_000, 9_000_000)
    output_t = r.randrange(400_000, 2_000_000)
    cache_r = r.randrange(5_000_000, 40_000_000)
    cache_w = r.randrange(1_000_000, 6_000_000)
    total = input_t + output_t + cache_r + cache_w
    cost = round(r.uniform(40, 400), 2)
    sonnet_share = round(0.72 + r.random() * 0.2, 3)
    sonnet_t = int(total * sonnet_share)
    haiku_t = total - sonnet_t
    sonnet_c = round(cost * sonnet_share, 2)
    haiku_c = round(cost - sonnet_c, 2)
    return {
        "project_slug": slug,
        "project_label": label,
        "project": project,
        "period": period,
        "input_tokens": input_t,
        "output_tokens": output_t,
        "cache_read_tokens": cache_r,
        "cache_write_tokens": cache_w,
        "total_tokens": total,
        "est_cost_usd": cost,
        "model_breakdown": [
            {"model": "claude-sonnet-4", "tokens": sonnet_t, "cost": sonnet_c},
            {"model": "claude-haiku-3-5", "tokens": haiku_t, "cost": haiku_c},
        ],
        "source": "seed",
    }

def seed_token_usage():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    existing = get("/items/os_token_usage?fields=id,project_slug,period,total_tokens&limit=-1")["data"]
    have = {(e["project_slug"], e["period"]): e for e in existing}

    created = updated = skipped = 0
    for slug, label, project in SLUGS:
        months = [month_row(slug, label, project, m) for m in MONTHS]
        allrow = {
            "project_slug": slug,
            "project_label": label,
            "project": project,
            "period": "all_time",
            "input_tokens": sum(m["input_tokens"] for m in months),
            "output_tokens": sum(m["output_tokens"] for m in months),
            "cache_read_tokens": sum(m["cache_read_tokens"] for m in months),
            "cache_write_tokens": sum(m["cache_write_tokens"] for m in months),
            "total_tokens": sum(m["total_tokens"] for m in months),
            "est_cost_usd": round(sum(m["est_cost_usd"] for m in months), 2),
            "model_breakdown": [
                {"model": "claude-sonnet-4",
                 "tokens": sum(m["model_breakdown"][0]["tokens"] for m in months),
                 "cost": round(sum(m["model_breakdown"][0]["cost"] for m in months), 2)},
                {"model": "claude-haiku-3-5",
                 "tokens": sum(m["model_breakdown"][1]["tokens"] for m in months),
                 "cost": round(sum(m["model_breakdown"][1]["cost"] for m in months), 2)},
            ],
            "source": "seed",
        }
        for row in months + [allrow]:
            key = (row["project_slug"], row["period"])
            row["last_synced"] = now_iso
            prev = have.get(key)
            if prev is None:
                post("/items/os_token_usage", row)
                created += 1
            elif str(prev.get("total_tokens")) != str(row["total_tokens"]):
                patch(f"/items/os_token_usage/{prev['id']}", row)
                updated += 1
            else:
                skipped += 1
    print(f"os_token_usage: created {created} / updated {updated} / skipped {skipped}")

# ---------------------------------------------------------------------------
# Step 3: os_seo_snapshots
# ---------------------------------------------------------------------------

SEO_TARGETS = [
    (2, "https://cedarandco.com"), (2, "https://cedarandco.com/menu"),
    (3, "https://northlightlaw.com"), (3, "https://northlightlaw.com/practice-areas"),
    (4, "https://vellum.studio"), (4, "https://vellum.studio/work"),
    (5, "https://harborfitness.co"), (5, "https://harborfitness.co/schedule"),
    (6, "https://bloombotanicals.com"), (6, "https://bloombotanicals.com/shop"),
    (7, "https://sterlingandvine.com"), (7, "https://sterlingandvine.com/reservations"),
    (8, "https://meridianfund.org"), (8, "https://meridianfund.org/grants"),
]

def clamp(v, lo, hi):
    return max(lo, min(hi, int(round(v))))

def seed_seo_snapshots():
    existing = get("/items/os_seo_snapshots?fields=url,collected_at&limit=-1")["data"]
    have = {(e["url"], norm_ts(e["collected_at"])) for e in existing}

    created = skipped = 0
    for org, url in SEO_TARGETS:
        rbase = rnd(f"seo:base:{url}")
        base = rbase.uniform(58, 74)          # starting health 13 weeks ago
        slope = rbase.uniform(0.9, 1.7)       # gentle upward trend per week
        for k in range(13):                   # k=0 newest ... k=12 oldest
            collected = ANCHOR - timedelta(days=7 * k) + timedelta(hours=6)
            r = rnd(f"seo:{url}:{k}")
            weeks_in = 12 - k
            health = clamp(base + slope * weeks_in + r.uniform(-3, 3), 55, 97)
            perf = clamp(health + r.uniform(-6, 4), 45, 99)
            a11y = clamp(health + r.uniform(0, 10), 55, 100)
            bp = clamp(health + r.uniform(-4, 8), 50, 100)
            seo = clamp(health + r.uniform(-2, 9), 55, 100)
            lcp = round(max(1200.0, min(3500.0, 3600 - perf * 24 + r.uniform(-150, 150))), 0)
            inp = round(max(80.0, min(350.0, 380 - perf * 2.8 + r.uniform(-20, 20))), 0)
            cls = round(max(0.01, min(0.25, 0.28 - health * 0.0025 + r.uniform(-0.01, 0.01))), 3)
            key = (url, norm_ts(iso(collected)))
            if key in have:
                skipped += 1
                continue
            post("/items/os_seo_snapshots", {
                "url": url,
                "organization": org,
                "collected_at": iso(collected),
                "health_score": health,
                "performance_score": perf,
                "accessibility_score": a11y,
                "best_practices_score": bp,
                "seo_score": seo,
                "lcp_ms": lcp,
                "inp_ms": inp,
                "cls": cls,
                "raw": None,
            })
            created += 1
    print(f"os_seo_snapshots: created {created} / updated 0 / skipped {skipped}")

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    gate()
    seed_activity_log()
    seed_token_usage()
    seed_seo_snapshots()
    print("seed-D5 done")
