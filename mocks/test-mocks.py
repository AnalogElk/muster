#!/usr/bin/env python3
"""Shape assertions against a running elk-os-mocks instance.

Usage: python3 test-mocks.py [base_url]
Exits 0 on success, 1 with a failure list otherwise.
"""
import base64
import json
import sys
import urllib.request
import urllib.parse

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"
TOKEN = "demo-matomo-token"
FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {detail}")
        FAILS.append(name)


def matomo(method, extra=None, token=TOKEN):
    params = {"module": "API", "method": method, "idSite": "2",
              "period": "range", "date": "2026-06-17,2026-07-16",
              "format": "json"}
    if token is not None:
        params["token_auth"] = token
    params.update(extra or {})
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        BASE + "/index.php", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read().decode())


def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


# health
st, h = get("/healthz")
check("healthz", st == 200 and h.get("ok") is True)

# VisitsSummary.get range totals: parseable + calibrated to the seeded
# snapshot for site 2 last30 (1970 visits): accept 0.7x - 1.3x.
st, vs = matomo("VisitsSummary.get")
check("visits-summary-range-shape",
      isinstance(vs, dict) and isinstance(vs.get("nb_visits"), int)
      and isinstance(vs.get("bounce_rate"), str)
      and vs["bounce_rate"].endswith("%")
      and isinstance(vs.get("nb_uniq_visitors"), int)
      and isinstance(vs.get("avg_time_on_site"), int), str(vs)[:200])
check("visits-summary-correlation",
      isinstance(vs.get("nb_visits"), int) and 1379 <= vs["nb_visits"] <= 2561,
      f"nb_visits={vs.get('nb_visits')} target ~1970")

# determinism: identical call twice
st2, vs2 = matomo("VisitsSummary.get")
check("determinism", vs == vs2)

# per-day keyed map
st, daily = matomo("VisitsSummary.get",
                   {"period": "day", "date": "last30"})
check("visits-summary-daily-map",
      isinstance(daily, dict) and len(daily) == 30
      and all(isinstance(v, dict) and "nb_visits" in v
              for v in daily.values()),
      f"keys={len(daily) if isinstance(daily, dict) else type(daily)}")

# VisitFrequency.get
st, vf = matomo("VisitFrequency.get")
check("visit-frequency",
      isinstance(vf, dict) and isinstance(vf.get("nb_visits_new"), int)
      and isinstance(vf.get("nb_visits_returning"), int))

# MultiSites.getAll
st, ms = matomo("MultiSites.getAll", {"idSite": "all"})
check("multisites",
      isinstance(ms, list)
      and sorted(e.get("idsite") for e in ms) == [2, 3, 4, 5, 6, 7, 8]
      and all(isinstance(e.get("nb_visits"), int)
              and isinstance(e.get("bounce_rate"), str) for e in ms),
      str(ms)[:200])

# ranked lists
for method, key in [("Actions.getPageUrls", "nb_visits"),
                    ("Actions.getEntryPageUrls", "nb_visits"),
                    ("Actions.getExitPageUrls", "nb_visits"),
                    ("Actions.getPageTitles", "nb_visits"),
                    ("Actions.getOutlinks", "nb_visits"),
                    ("Actions.getDownloads", "nb_visits"),
                    ("Referrers.getWebsites", "nb_visits"),
                    ("Referrers.getSearchEngines", "nb_visits"),
                    ("Referrers.getSocials", "nb_visits"),
                    ("DevicesDetection.getType", "nb_visits"),
                    ("DevicesDetection.getBrowsers", "nb_visits"),
                    ("DevicesDetection.getOsFamilies", "nb_visits"),
                    ("UserCountry.getCountry", "nb_visits"),
                    ("UserCountry.getRegion", "nb_visits"),
                    ("UserCountry.getCity", "nb_visits"),
                    ("Events.getCategory", "nb_events")]:
    st, rows = matomo(method, {"filter_limit": "10"})
    check(method,
          isinstance(rows, list) and len(rows) > 0 and len(rows) <= 10
          and all(isinstance(r.get("label"), str)
                  and isinstance(r.get(key), int) for r in rows)
          and rows == sorted(rows, key=lambda r: r[key], reverse=True),
          str(rows)[:160])

# filter_limit respected
st, rows = matomo("Actions.getPageUrls", {"filter_limit": "3"})
check("filter-limit", isinstance(rows, list) and len(rows) <= 3)

# referrer types map to channel keys the portal parses
st, rt = matomo("Referrers.getReferrerType")
labels = " ".join(r["label"].lower() for r in rt)
check("referrer-type-labels",
      all(w in labels for w in ["direct", "search", "website", "social"]),
      labels)

# segment scaling shrinks totals
st, seg = matomo("VisitsSummary.get",
                 {"segment": "referrerType==search"})
check("segment-scaling",
      isinstance(seg.get("nb_visits"), int)
      and 0 < seg["nb_visits"] < vs["nb_visits"])

# hour-of-day: 24 buckets labeled 0..23
st, hours = matomo("VisitTime.getVisitInformationPerServerTime")
check("hour-of-day",
      isinstance(hours, list) and len(hours) == 24
      and [r["label"] for r in hours] == [str(h) for h in range(24)]
      and all(isinstance(r["nb_visits"], int) for r in hours))

# live visits
st, live = matomo("Live.getLastVisitsDetails", {"filter_limit": "10"})
check("live-visits",
      isinstance(live, list) and len(live) == 10
      and all(isinstance(r.get("serverTimestamp"), int)
              and isinstance(r.get("actionDetails"), list) for r in live)
      and [r["serverTimestamp"] for r in live]
      == sorted((r["serverTimestamp"] for r in live), reverse=True),
      str(live)[:160])

# goals
st, goals = matomo("Goals.get")
check("goals",
      isinstance(goals, dict) and isinstance(goals.get("nb_conversions"), int)
      and goals["nb_conversions"] > 0
      and isinstance(goals.get("revenue"), (int, float)))

# unknown methods: empty-but-valid, never 500
st, unk1 = matomo("CustomReports.getFancyThing")
check("unknown-method-list", st == 200 and unk1 == [])
st, unk2 = matomo("SomePlugin.get")
check("unknown-method-get", st == 200 and unk2 == {})

# token gate
st, err = matomo("VisitsSummary.get", token="")
check("missing-token", err.get("result") == "error")
st, err = matomo("VisitsSummary.get", token="wrong-token")
check("wrong-token", err.get("result") == "error")

# --- Migadu ---
basic = base64.b64encode(b"demo@musterr.dev:demo-migadu-key").decode()
st, mb = get("/v1/domains/cedarandco.com/mailboxes",
             {"Authorization": f"Basic {basic}"})
boxes = mb.get("mailboxes")
check("migadu-shape",
      st == 200 and isinstance(boxes, list) and len(boxes) >= 4
      and all(isinstance(b.get("address"), str)
              and b["address"].endswith("@cedarandco.com")
              and isinstance(b.get("local_part"), str)
              and isinstance(b.get("is_active"), bool) for b in boxes),
      str(mb)[:200])
active = [b for b in boxes or [] if b["is_active"]]
check("migadu-active-subset", len(active) >= 4)

# deterministic per domain
st2, mb2 = get("/v1/domains/cedarandco.com/mailboxes",
               {"Authorization": f"Basic {basic}"})
check("migadu-determinism", mb == mb2)

# different domain differs
st3, mb3 = get("/v1/domains/northlightlaw.com/mailboxes",
               {"Authorization": f"Basic {basic}"})
check("migadu-per-domain", mb3 != mb and st3 == 200)

# auth required
st4, _ = get("/v1/domains/cedarandco.com/mailboxes")
check("migadu-401", st4 == 401)

# 404 elsewhere
st5, _ = get("/nope")
check("not-found", st5 == 404)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} checks: {FAILS}")
    sys.exit(1)
print("ALL CHECKS PASSED")
