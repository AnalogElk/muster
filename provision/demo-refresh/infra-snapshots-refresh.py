#!/usr/bin/env python3
"""Daily infra_snapshots appender for the Muster demo box.

The employee dashboard's Infrastructure Operations section reads the newest
row of the `infra_snapshots` collection (lib/infra/storage.ts prefers a
persisted CMS snapshot over live env-gated cloud APIs). The demo rows are
synthetic; without a daily appender the newest row ages out of the UI's
freshness window and the cost trend slides empty.

This script copies the latest snapshot forward one row per missing day (up to
14 days of catch-up), keeping the payload internally consistent:

  - summary columns aws_mtd_cost_usd / neon_cost_usd / netlify_bw_used_gib are
    recomputed from the per-day rate implied by the latest row (month-to-date
    figures reset on the 1st and grow linearly, matching the original seed).
  - payload.collectedAt, payload.aws.mtdCostUsd/mtdCostPeriod,
    payload.neon.* MTD figures, payload.netlify.bandwidth (usedGib + period on
    month rollover), payload.healthchecks.checks[*].lastPing and
    payload.github.runs[*].createdAt move with the new day.
  - everything else (instances, sites, stripe MRR, repos) is copied verbatim.

Idempotent: a day that already has a row is skipped, so re-running is safe.
Add-only: never edits or deletes existing rows. is_test_data:false (the demo
viewer is a real viewer; flagged rows are filtered out of the portal).

Admin token is read from ~/elk-os/.env INSIDE this script and never printed.
Output: row counts and dates only.
"""
import copy
import json
import os
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone

BASE = "https://cms.musterr.dev"
MAX_CATCHUP_DAYS = 14


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


def req(path, method="GET", body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def iso_day(dt):
    return dt.strftime("%Y-%m-%d")


def day_has_row(day):
    flt = (
        f"filter[collected_at][_between]={day.strftime('%Y-%m-%dT00:00:00')},"
        f"{day.strftime('%Y-%m-%dT23:59:59')}"
    )
    st, data = req(f"/items/infra_snapshots?{flt}&fields=id&limit=1")
    return st == 200 and bool(data.get("data"))


def shift_iso(ts, delta_days):
    """Shift an ISO 'YYYY-MM-DDTHH:MM:SSZ'-ish string by N days; keep format."""
    try:
        base = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        return (base + timedelta(days=delta_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ts


def build_row(latest, day, delta_days):
    """Derive a consistent snapshot row for `day` from the latest row."""
    src_day = datetime.strptime(latest["collected_at"][:10], "%Y-%m-%d")
    src_dom = max(src_day.day, 1)
    dom = day.day

    def mtd(value):
        if value is None:
            return None
        rate = float(value) / src_dom
        return round(rate * dom, 2)

    payload = latest.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = copy.deepcopy(payload) if payload else {}

    collected = day.strftime("%Y-%m-%dT06:00:00Z")
    payload["collectedAt"] = collected

    aws = payload.get("aws") or {}
    if aws:
        aws["mtdCostUsd"] = mtd(aws.get("mtdCostUsd"))
        aws["mtdCostPeriod"] = f"{day.strftime('%Y-%m')}-01 to {iso_day(day)}"

    neon = payload.get("neon") or {}
    if neon:
        for k in ("totalCuHoursMtd", "computeCostUsd"):
            if neon.get(k) is not None:
                neon[k] = mtd(neon[k])
        storage = float(neon.get("storageCostUsd") or 0)
        if neon.get("computeCostUsd") is not None:
            neon["totalCostUsd"] = round(neon["computeCostUsd"] + storage, 2)
        for proj in neon.get("projects") or []:
            for k in ("cuHoursMtd", "estCostUsd"):
                if proj.get(k) is not None:
                    proj[k] = mtd(proj[k])

    netlify = payload.get("netlify") or {}
    bw = netlify.get("bandwidth") or {}
    if bw:
        bw["usedGib"] = mtd(bw.get("usedGib"))
        month_start = day.replace(day=1)
        days_in_month = monthrange(day.year, day.month)[1]
        bw["periodStart"] = month_start.strftime("%Y-%m-%dT00:00:00Z")
        bw["periodEnd"] = (month_start + timedelta(days=days_in_month)).strftime(
            "%Y-%m-%dT00:00:00Z"
        )

    for check in (payload.get("healthchecks") or {}).get("checks") or []:
        if check.get("lastPing"):
            check["lastPing"] = day.strftime("%Y-%m-%dT05:54:00Z")

    for run in (payload.get("github") or {}).get("runs") or []:
        if run.get("createdAt"):
            run["createdAt"] = shift_iso(run["createdAt"], delta_days)

    return {
        "collected_at": collected,
        "aws_mtd_cost_usd": mtd(latest.get("aws_mtd_cost_usd")),
        "neon_cost_usd": mtd(latest.get("neon_cost_usd")),
        "neon_cu_hours": mtd(latest.get("neon_cu_hours")),
        "netlify_bw_used_gib": mtd(latest.get("netlify_bw_used_gib")),
        "netlify_bw_included_gib": latest.get("netlify_bw_included_gib"),
        "hc_total": latest.get("hc_total"),
        "hc_up": latest.get("hc_up"),
        "hc_down": latest.get("hc_down"),
        "hc_grace": latest.get("hc_grace"),
        "down_slugs": latest.get("down_slugs"),
        "payload": payload,
        "is_test_data": False,
    }


def main():
    st, data = req("/items/infra_snapshots?sort=-collected_at&limit=1")
    if st != 200 or not data.get("data"):
        print(f"infra_snapshots: cannot read latest row (HTTP {st}); nothing to refresh")
        return
    latest = data["data"][0]
    last_day = datetime.strptime(latest["collected_at"][:10], "%Y-%m-%d")
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    today = datetime(today.year, today.month, today.day)

    created = skipped = 0
    day = max(last_day + timedelta(days=1), today - timedelta(days=MAX_CATCHUP_DAYS - 1))
    while day <= today:
        delta_days = (day - last_day).days
        if day_has_row(day):
            skipped += 1
        else:
            row = build_row(latest, day, delta_days)
            st, resp = req("/items/infra_snapshots", "POST", row)
            if st in (200, 201, 204):
                created += 1
            else:
                print(f"infra_snapshots: POST failed for {iso_day(day)} (HTTP {st}): "
                      f"{json.dumps(resp)[:200]}")
        day += timedelta(days=1)
    print(f"infra_snapshots: created {created} / skipped {skipped} "
          f"(latest was {iso_day(last_day)})")


if __name__ == "__main__":
    main()
