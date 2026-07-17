#!/usr/bin/env python3
"""
Standalone, re-runnable os_insights seeder for the Muster demo (cms.musterr.dev).

MUST be re-run on any day the portal is screenshot: the portal's insight cache
(lib/portal/analytics/insight-service.ts:61-79) filters
filter[period][_eq]=<exact 'YYYY-MM-DD,YYYY-MM-DD' string> AND requires
generated_at to be the same UTC day, so both the range keys and generated_at
shift with the run day.

Period keys are the FIVE concrete toolbar preset ranges computed on the run
day with the portal's own formula (lib/portal/analytics/date-range.ts):
  7d/28d/90d -> start = today-(N-1)d, end = today (UTC dates)
  qtd        -> quarter start .. today
  ytd        -> Jan 1 .. today

Upsert key: (organization, period). Existing rows are PATCHed (generated_at,
summary, highlights, metrics, model) so the same-day cache read always hits.

Shapes (lib/portal/analytics/insight.ts:16-26):
  highlights: [{label, value, direction?}] (3 objects, direction up|down|flat or omitted)
  metrics: {web: {visits, visitsDeltaPct, bounceRate}, revenue: {mrrUsd, outstandingUsd},
            delivery: {releasesShipped, onTimeRatePct}}

No em dashes anywhere. Deterministic numbers per (org, preset) via seeded RNG.
"""
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

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
        BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    last = None
    for pause in (0, 2, 5, 10):
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

SEED = 20260716

def rnd(key):
    return random.Random(f"{SEED}:{key}")

# --- Ranges computed from the RUN DAY with the portal's own formula ----------

def fmt(d):
    return d.strftime("%Y-%m-%d")

def preset_ranges(now=None):
    now = now or datetime.now(timezone.utc)
    today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    out = {}
    for key, n in (("7d", 7), ("28d", 28), ("90d", 90)):
        out[key] = f"{fmt(today - timedelta(days=n - 1))},{fmt(today)}"
    q_month = today.month - ((today.month - 1) % 3)
    out["qtd"] = f"{fmt(datetime(today.year, q_month, 1, tzinfo=timezone.utc))},{fmt(today)}"
    out["ytd"] = f"{fmt(datetime(today.year, 1, 1, tzinfo=timezone.utc))},{fmt(today)}"
    return out

def range_days(period):
    start_s, end_s = period.split(",")
    start = datetime.strptime(start_s, "%Y-%m-%d")
    end = datetime.strptime(end_s, "%Y-%m-%d")
    return (end - start).days + 1

# --- Deterministic metrics per (org, preset) ---------------------------------

def build_metrics(org_id, preset, period):
    r = rnd(f"insight:{org_id}:{preset}")
    daily = rnd(f"insight:daily:{org_id}").uniform(25, 140)
    days = range_days(period)
    visits = int(daily * days * r.uniform(0.85, 1.15))
    delta = None if r.random() < 0.15 else round(r.uniform(-18, 35), 1)
    bounce = f"{r.randrange(34, 59)}%"
    mrr = int(rnd(f"insight:mrr:{org_id}").uniform(800, 6500))
    outstanding = int(r.uniform(0, 9000))
    releases = max(0, int(round(days / 30 * r.uniform(0.5, 2.5))))
    on_time = r.randrange(72, 99)
    return {
        "web": {"visits": visits, "visitsDeltaPct": delta, "bounceRate": bounce},
        "revenue": {"mrrUsd": mrr, "outstandingUsd": outstanding},
        "delivery": {"releasesShipped": releases, "onTimeRatePct": on_time},
    }

def build_highlights(m):
    web, rev, dl = m["web"], m["revenue"], m["delivery"]
    h1 = {"label": "Visits", "value": f"{web['visits']:,}"}
    if web["visitsDeltaPct"] is not None:
        h1["direction"] = "up" if web["visitsDeltaPct"] > 0 else "down" if web["visitsDeltaPct"] < 0 else "flat"
    h2 = {"label": "Releases shipped", "value": str(dl["releasesShipped"])}
    h3 = {"label": "Outstanding", "value": f"${rev['outstandingUsd']:,}",
          "direction": "down" if rev["outstandingUsd"] < rev["mrrUsd"] else "up"}
    return [h1, h2, h3]

def build_summary(org_name, m):
    web, rev, dl = m["web"], m["revenue"], m["delivery"]
    delta = web["visitsDeltaPct"]
    if delta is None:
        s1 = f"{org_name} logged {web['visits']:,} visits over this window with a bounce rate of {web['bounceRate']}."
    else:
        word = "up" if delta > 0 else "down" if delta < 0 else "flat at"
        s1 = (f"{org_name} logged {web['visits']:,} visits over this window, "
              f"{word} {abs(delta)}% versus the prior period." if delta != 0 else
              f"{org_name} logged {web['visits']:,} visits over this window, flat versus the prior period.")
    n = dl["releasesShipped"]
    s2 = (f"{n} release{'s' if n != 1 else ''} shipped with an on-time rate of {dl['onTimeRatePct']}%.")
    s3 = f"Outstanding invoices stand at ${rev['outstandingUsd']:,} against ${rev['mrrUsd']:,} in monthly recurring revenue."
    return " ".join([s1, s2, s3])

# -----------------------------------------------------------------------------

def main():
    now = datetime.now(timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ranges = preset_ranges(now)
    print("ranges:", json.dumps(ranges))

    orgs = get("/items/organizations?fields=id,name&limit=-1&sort=id")["data"]
    created = updated = 0
    for org in orgs:
        org_id = org["id"]
        org_name = (org.get("name") or "").replace("—", "-").replace("–", "-")
        for preset, period in ranges.items():
            metrics = build_metrics(org_id, preset, period)
            body = {
                "organization": org_id,
                "period": period,
                "generated_at": generated_at,
                "summary": build_summary(org_name, metrics),
                "highlights": build_highlights(metrics),
                "metrics": metrics,
                "model": "claude-sonnet-4",
            }
            q = (f"/items/os_insights?filter[organization][_eq]={org_id}"
                 f"&filter[period][_eq]={urllib.parse.quote(period)}&fields=id&limit=1")
            existing = get(q)["data"]
            if existing:
                request("PATCH", f"/items/os_insights/{existing[0]['id']}", body)
                updated += 1
            else:
                request("POST", "/items/os_insights", body)
                created += 1
    print(f"os_insights: created {created} / updated {updated} / skipped 0")

if __name__ == "__main__":
    main()
