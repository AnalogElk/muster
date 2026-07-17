#!/usr/bin/env python3
"""
elk-os-mocks: one-port mock service for the Muster demo box.

Serves two external integrations the frozen demo portal is wired to:

  1. Matomo Reporting API  ->  POST (or GET) /index.php
     Form-encoded, module=API, format=json, token_auth required.
     Implements every method the portal source calls:
       VisitsSummary.get, VisitFrequency.get, MultiSites.getAll,
       Actions.getPageUrls / getEntryPageUrls / getExitPageUrls /
       getPageTitles / getOutlinks / getDownloads,
       Referrers.getReferrerType / getWebsites / getSearchEngines / getSocials,
       DevicesDetection.getType / getBrowsers / getOsFamilies,
       UserCountry.getCountry / getRegion / getCity,
       VisitTime.getVisitInformationPerServerTime,
       Live.getLastVisitsDetails, Events.getCategory, Goals.get
     Any unrecognized method returns an empty-but-valid shape
     ({} when the method name ends in ".get", [] otherwise), never a 500.

  2. Migadu Admin API  ->  GET /v1/domains/<domain>/mailboxes
     Basic auth required (any credentials accepted). Response shape matches
     what lib/portal/email/migadu.ts parses:
       {"mailboxes": [{"address", "local_part", "name", "is_active"}]}

Determinism: every number is pseudo-random but seeded by (site_id, date),
so identical queries always return identical payloads and day-to-day series
look organic. Per-site base levels are calibrated to the analytics_snapshots
payloads seeded on cms.musterr.dev on 2026-07-16, so live mock numbers and
persisted snapshot numbers agree loosely (KPI totals within a few percent).

Stdlib only. No external dependencies. Demo data only, no real analytics.
"""

import datetime as dt
import json
import math
import os
import random
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote

PORT = int(os.environ.get("PORT", "8080"))
# When set, token_auth must equal this value; when empty, any non-empty
# token is accepted. The compose overlay pins it to the fake demo token so
# wiring mistakes surface as Matomo-style errors instead of silent wrong data.
EXPECTED_TOKEN = os.environ.get("MOCK_MATOMO_TOKEN", "")

SEED_NS = "muster-mock"

# ---------------------------------------------------------------------------
# Site profiles, calibrated to the seeded analytics_snapshots (2026-07-16):
# daily = last30 visits / 30 from the snapshot payload totals.
# ---------------------------------------------------------------------------

SITES = {
    2: {"label": "Cedar & Co Coffee", "domain": "cedarandco.com",
        "daily": 65.7, "uniq": 0.772, "ppv": 2.56, "bounce": 51,
        "avg_time": 205, "industry": "coffee"},
    3: {"label": "Northlight Law", "domain": "northlightlaw.com",
        "daily": 40.1, "uniq": 0.767, "ppv": 2.65, "bounce": 49,
        "avg_time": 129, "industry": "law"},
    4: {"label": "Vellum Studio", "domain": "vellum.studio",
        "daily": 55.3, "uniq": 0.770, "ppv": 2.56, "bounce": 39,
        "avg_time": 180, "industry": "studio"},
    5: {"label": "Harbor Fitness", "domain": "harborfitness.co",
        "daily": 67.1, "uniq": 0.774, "ppv": 2.54, "bounce": 38,
        "avg_time": 191, "industry": "fitness"},
    6: {"label": "Bloom Botanicals", "domain": "bloombotanicals.com",
        "daily": 47.1, "uniq": 0.770, "ppv": 2.59, "bounce": 51,
        "avg_time": 182, "industry": "shop"},
    7: {"label": "Sterling & Vine", "domain": "sterlingandvine.com",
        "daily": 30.6, "uniq": 0.762, "ppv": 2.56, "bounce": 46,
        "avg_time": 153, "industry": "restaurant"},
    8: {"label": "Meridian Fund", "domain": "meridianfund.org",
        "daily": 59.0, "uniq": 0.771, "ppv": 2.51, "bounce": 46,
        "avg_time": 199, "industry": "fund"},
}


def site_profile(site_id):
    if site_id in SITES:
        return SITES[site_id]
    rng = random.Random(f"{SEED_NS}:site:{site_id}")
    return {
        "label": f"Site {site_id}",
        "domain": f"site{site_id}.example.com",
        "daily": rng.uniform(18, 60),
        "uniq": rng.uniform(0.72, 0.80),
        "ppv": rng.uniform(2.2, 3.1),
        "bounce": rng.randint(35, 58),
        "avg_time": rng.randint(110, 240),
        "industry": "default",
    }


# ---------------------------------------------------------------------------
# Deterministic daily engine
# ---------------------------------------------------------------------------

WEEKDAY_FACTOR = [1.08, 1.12, 1.10, 1.07, 1.02, 0.75, 0.71]  # Mon..Sun


def day_metrics(site_id, day):
    """Core metrics for one site on one calendar day. Fully deterministic."""
    p = site_profile(site_id)
    rng = random.Random(f"{SEED_NS}:{site_id}:{day.isoformat()}")
    noise = rng.uniform(0.84, 1.18)
    visits = max(1, round(p["daily"] * WEEKDAY_FACTOR[day.weekday()] * noise))
    uniq = max(1, round(visits * p["uniq"] * rng.uniform(0.96, 1.04)))
    actions = max(visits, round(visits * p["ppv"] * rng.uniform(0.93, 1.07)))
    bounce = min(75, max(20, p["bounce"] + rng.randint(-4, 4)))
    avg_time = max(45, p["avg_time"] + rng.randint(-24, 24))
    conversions = round(visits * rng.uniform(0.012, 0.032))
    return {
        "visits": visits,
        "uniq": uniq,
        "actions": actions,
        "bounce": bounce,
        "avg_time": avg_time,
        "conversions": conversions,
    }


def parse_one_date(s, today):
    s = s.strip().lower()
    if s == "today":
        return today
    if s == "yesterday":
        return today - dt.timedelta(days=1)
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return today


def resolve_window(date_param, today=None):
    """Resolve a Matomo date param to an inclusive (start, end) date pair.

    Handles: "YYYY-MM-DD,YYYY-MM-DD", "lastN", "previousN", "today",
    "yesterday", and a single "YYYY-MM-DD". Falls back to last30.
    """
    today = today or dt.date.today()
    s = (date_param or "last30").strip().lower()
    if "," in s:
        a, b = s.split(",", 1)
        start, end = parse_one_date(a, today), parse_one_date(b, today)
    else:
        m_last = re.fullmatch(r"last(\d+)", s)
        m_prev = re.fullmatch(r"previous(\d+)", s)
        if m_last:
            n = max(1, int(m_last.group(1)))
            end = today
            start = today - dt.timedelta(days=n - 1)
        elif m_prev:
            n = max(1, int(m_prev.group(1)))
            end = today - dt.timedelta(days=1)
            start = end - dt.timedelta(days=n - 1)
        else:
            start = end = parse_one_date(s, today)
    if end < start:
        start, end = end, start
    # Safety cap so a hostile date range cannot spin the loop for minutes.
    if (end - start).days > 1500:
        start = end - dt.timedelta(days=1500)
    return start, end


def iter_days(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def range_totals(site_id, start, end, seg_factor=1.0):
    visits = uniq = actions = conversions = 0
    bounce_weighted = time_weighted = 0.0
    for day in iter_days(start, end):
        m = day_metrics(site_id, day)
        visits += m["visits"]
        uniq += m["uniq"]
        actions += m["actions"]
        conversions += m["conversions"]
        bounce_weighted += m["bounce"] * m["visits"]
        time_weighted += m["avg_time"] * m["visits"]
    bounce = round(bounce_weighted / visits) if visits else 0
    avg_time = round(time_weighted / visits) if visits else 0
    if seg_factor < 1.0:
        visits = round(visits * seg_factor)
        uniq = round(uniq * seg_factor)
        actions = round(actions * seg_factor)
        conversions = round(conversions * seg_factor)
    return {
        "visits": visits,
        "uniq": uniq,
        "actions": actions,
        "conversions": conversions,
        "bounce": bounce,
        "avg_time": avg_time,
    }


# ---------------------------------------------------------------------------
# Segment scaling (the portal builds segments like
# "referrerType==search;deviceType==desktop;countryCode==us")
# ---------------------------------------------------------------------------

CHANNEL_SHARES = {"direct": 0.38, "search": 0.34, "website": 0.12,
                  "social": 0.11, "campaign": 0.05}
DEVICE_SHARES = {"desktop": 0.58, "smartphone": 0.36, "tablet": 0.06}
COUNTRY_SHARES = {"us": 0.55, "ca": 0.12, "gb": 0.10, "de": 0.06,
                  "au": 0.05, "nl": 0.04, "fr": 0.04, "se": 0.04}


def segment_factor(segment):
    if not segment:
        return 1.0
    f = 1.0
    for part in segment.split(";"):
        if "==" not in part:
            continue
        key, val = part.split("==", 1)
        val = val.strip().lower()
        key = key.strip()
        if key == "referrerType":
            f *= CHANNEL_SHARES.get(val, 0.05)
        elif key == "deviceType":
            f *= DEVICE_SHARES.get(val, 0.05)
        elif key == "countryCode":
            f *= COUNTRY_SHARES.get(val, 0.02)
    return f


# ---------------------------------------------------------------------------
# Ranked-report content pools (industry flavored, fictional universe)
# ---------------------------------------------------------------------------

PAGES = {
    "coffee": ["/", "/menu", "/locations", "/shop", "/wholesale", "/about",
               "/blog/spring-menu", "/blog/single-origin-guide", "/gift-cards",
               "/events", "/contact"],
    "law": ["/", "/practice-areas", "/attorneys", "/case-results",
            "/insights/estate-planning-basics", "/insights/small-business-contracts",
            "/about", "/careers", "/contact"],
    "studio": ["/", "/work", "/studio", "/contact", "/work/harbor-rebrand",
               "/work/meridian-annual-report", "/services", "/journal"],
    "fitness": ["/", "/classes", "/schedule", "/memberships", "/trainers",
                "/blog/strength-programming", "/blog/mobility-basics", "/app",
                "/contact"],
    "shop": ["/", "/shop", "/shop/monstera-deliciosa", "/care-guides",
             "/subscriptions", "/blog/repotting-101", "/about", "/contact"],
    "restaurant": ["/", "/menu", "/reservations", "/private-events",
                   "/wine-club", "/about", "/gift-cards", "/contact"],
    "fund": ["/", "/grants", "/apply", "/impact", "/reports/annual-2025",
             "/about", "/team", "/news", "/contact"],
    "default": ["/", "/about", "/services", "/blog", "/pricing", "/contact"],
}

OUTLINKS = {
    "coffee": ["instagram.com", "maps.google.com", "doordash.com", "yelp.com",
               "facebook.com"],
    "law": ["linkedin.com", "avvo.com", "maps.google.com", "martindale.com"],
    "studio": ["instagram.com", "behance.net", "dribbble.com", "linkedin.com"],
    "fitness": ["instagram.com", "mindbodyonline.com", "maps.google.com",
                "apps.apple.com", "play.google.com"],
    "shop": ["instagram.com", "pinterest.com", "facebook.com", "usps.com"],
    "restaurant": ["opentable.com", "instagram.com", "maps.google.com",
                   "yelp.com"],
    "fund": ["linkedin.com", "guidestar.org", "maps.google.com", "youtube.com"],
    "default": ["instagram.com", "maps.google.com", "linkedin.com",
                "facebook.com"],
}

DOWNLOADS = {
    "coffee": ["files/menu.pdf", "files/wholesale-catalog.pdf",
               "files/catering-guide.pdf"],
    "law": ["files/client-intake-form.pdf", "files/fee-schedule.pdf",
            "files/estate-planning-checklist.pdf"],
    "studio": ["files/capabilities-deck.pdf", "files/rate-card.pdf"],
    "fitness": ["files/class-schedule.pdf", "files/membership-guide.pdf"],
    "shop": ["files/plant-care-guide.pdf", "files/gift-guide.pdf"],
    "restaurant": ["files/dinner-menu.pdf", "files/wine-list.pdf",
                   "files/private-events.pdf"],
    "fund": ["files/annual-report-2025.pdf", "files/grant-guidelines.pdf",
             "files/application-checklist.pdf"],
    "default": ["files/brochure.pdf", "files/price-list.pdf"],
}

REFERRER_WEBSITES = {
    "coffee": ["yelp.com", "sprudge.com", "eater.com", "reddit.com",
               "tripadvisor.com"],
    "law": ["avvo.com", "justia.com", "superlawyers.com", "reddit.com",
            "nolo.com"],
    "studio": ["clutch.co", "behance.net", "awwwards.com", "dribbble.com",
               "siteinspire.com"],
    "fitness": ["classpass.com", "yelp.com", "reddit.com", "mapmyrun.com"],
    "shop": ["etsy.com", "apartmenttherapy.com", "reddit.com", "thespruce.com"],
    "restaurant": ["opentable.com", "eater.com", "yelp.com", "infatuation.com",
                   "tripadvisor.com"],
    "fund": ["guidestar.org", "charitynavigator.org", "philanthropy.com",
             "linkedin.com"],
    "default": ["yelp.com", "reddit.com", "medium.com", "producthunt.com"],
}

EVENT_CATEGORIES = {
    "coffee": ["Online Order", "Newsletter Signup", "Menu PDF", "Store Locator"],
    "law": ["Consultation Request", "Newsletter Signup", "Callback Request",
            "Guide Download"],
    "studio": ["Project Inquiry", "Newsletter Signup", "Deck Download"],
    "fitness": ["Class Booking", "Trial Signup", "App Download",
                "Newsletter Signup"],
    "shop": ["Add To Cart", "Checkout", "Newsletter Signup", "Care Guide"],
    "restaurant": ["Reservation", "Gift Card Purchase", "Newsletter Signup",
                   "Menu PDF"],
    "fund": ["Grant Application", "Newsletter Signup", "Report Download",
             "Donation"],
    "default": ["Contact Form", "Newsletter Signup", "Download"],
}

SEARCH_ENGINES = [("Google", 0.78), ("Bing", 0.10), ("DuckDuckGo", 0.06),
                  ("Yahoo!", 0.04), ("Ecosia", 0.02)]

SOCIALS_CONSUMER = [("Instagram", 0.44), ("Facebook", 0.24), ("Pinterest", 0.14),
                    ("LinkedIn", 0.10), ("X (Twitter)", 0.08)]
SOCIALS_PROFESSIONAL = [("LinkedIn", 0.52), ("Instagram", 0.18),
                        ("Facebook", 0.14), ("X (Twitter)", 0.10),
                        ("YouTube", 0.06)]

BROWSERS = [("Chrome", 0.52), ("Safari", 0.17), ("Mobile Safari", 0.12),
            ("Firefox", 0.08), ("Microsoft Edge", 0.07),
            ("Samsung Browser", 0.04)]

OS_FAMILIES = [("Windows", 0.34), ("iOS", 0.24), ("Android", 0.20),
               ("Mac", 0.16), ("GNU/Linux", 0.06)]

DEVICE_TYPES = [("Desktop", 0.58), ("Smartphone", 0.36), ("Tablet", 0.06)]

COUNTRIES = [("United States", 0.55), ("Canada", 0.12),
             ("United Kingdom", 0.10), ("Germany", 0.06), ("Australia", 0.05),
             ("Netherlands", 0.04), ("France", 0.04), ("Sweden", 0.04)]

REGIONS = [("California, United States", 0.16),
           ("New York, United States", 0.13),
           ("Washington, United States", 0.10),
           ("Texas, United States", 0.09),
           ("Oregon, United States", 0.08),
           ("Ontario, Canada", 0.09),
           ("British Columbia, Canada", 0.06),
           ("England, United Kingdom", 0.10),
           ("Berlin, Germany", 0.05),
           ("New South Wales, Australia", 0.05),
           ("Illinois, United States", 0.05),
           ("Massachusetts, United States", 0.04)]

CITIES = [("San Francisco, California, United States", 0.11),
          ("New York, New York, United States", 0.11),
          ("Seattle, Washington, United States", 0.09),
          ("Portland, Oregon, United States", 0.08),
          ("Austin, Texas, United States", 0.07),
          ("Toronto, Ontario, Canada", 0.08),
          ("Vancouver, British Columbia, Canada", 0.05),
          ("London, England, United Kingdom", 0.09),
          ("Berlin, Berlin, Germany", 0.04),
          ("Sydney, New South Wales, Australia", 0.04),
          ("Chicago, Illinois, United States", 0.05),
          ("Boston, Massachusetts, United States", 0.04)]

REFERRER_TYPES = [("Direct Entry", "direct"), ("Search Engines", "search"),
                  ("Websites", "website"), ("Social Networks", "social"),
                  ("Campaigns", "campaign")]


def pretty_title(path, label):
    if path == "/":
        return f"Home | {label}"
    seg = path.strip("/").split("/")[-1].replace("-", " ").title()
    return f"{seg} | {label}"


# ---------------------------------------------------------------------------
# Ranked-report builders
# ---------------------------------------------------------------------------

def weighted_rows(site_id, start, end, category, items, total, value_key,
                  jitter=0.25, extra_fn=None, filter_limit=None):
    """Distribute `total` across items with per-site deterministic jitter.

    `items` is either a list of labels (exponential falloff weights) or a
    list of (label, weight) pairs. Returns rows sorted by value descending.
    """
    rng = random.Random(
        f"{SEED_NS}:rank:{site_id}:{category}:{start.isoformat()}:{end.isoformat()}")
    if items and isinstance(items[0], tuple):
        pairs = [(lbl, w * rng.uniform(1 - jitter, 1 + jitter))
                 for lbl, w in items]
    else:
        pairs = [(lbl, (0.62 ** i) * rng.uniform(1 - jitter, 1 + jitter))
                 for i, lbl in enumerate(items)]
    wsum = sum(w for _, w in pairs) or 1.0
    rows = []
    for lbl, w in pairs:
        val = round(total * w / wsum)
        if val <= 0:
            continue
        row = {"label": lbl, value_key: val}
        if extra_fn:
            row.update(extra_fn(lbl, val, rng))
        rows.append(row)
    rows.sort(key=lambda r: r[value_key], reverse=True)
    if filter_limit:
        rows = rows[:filter_limit]
    return rows


def pages_rows(site_id, start, end, category, totals, filter_limit, seg_factor):
    p = site_profile(site_id)
    items = PAGES.get(p["industry"], PAGES["default"])
    total = round(totals["visits"] * 0.92)

    def extra(lbl, val, rng):
        hits = round(val * rng.uniform(1.15, 1.65))
        avg_page_time = rng.randint(35, 180)
        return {
            "nb_hits": hits,
            "nb_entrances": round(val * rng.uniform(0.30, 0.55)),
            "nb_exits": round(val * rng.uniform(0.25, 0.50)),
            "bounce_rate": f"{rng.randint(25, 62)}%",
            "exit_rate": f"{rng.randint(18, 55)}%",
            "sum_time_spent": hits * avg_page_time,
            "avg_time_on_page": avg_page_time,
            "url": f"https://{p['domain']}{lbl}",
        }

    return weighted_rows(site_id, start, end, category, items, total,
                         "nb_visits", extra_fn=extra, filter_limit=filter_limit)


def simple_rows(site_id, start, end, category, items, totals, share,
                value_key, filter_limit, extra_fn=None):
    total = round(totals["visits"] * share)
    return weighted_rows(site_id, start, end, category, items, total,
                         value_key, extra_fn=extra_fn,
                         filter_limit=filter_limit)


# ---------------------------------------------------------------------------
# Matomo method handlers
# ---------------------------------------------------------------------------

def visits_summary_totals(t):
    visits = t["visits"]
    return {
        "nb_uniq_visitors": t["uniq"],
        "nb_users": 0,
        "nb_visits": visits,
        "nb_actions": t["actions"],
        "nb_visits_converted": t["conversions"],
        "bounce_count": round(visits * t["bounce"] / 100),
        "sum_visit_length": visits * t["avg_time"],
        "max_actions": 14,
        "bounce_rate": f"{t['bounce']}%",
        "nb_actions_per_visit": round(t["actions"] / visits, 1) if visits else 0,
        "avg_time_on_site": t["avg_time"],
    }


def handle_matomo(params):
    method = params.get("method", "")
    id_site_raw = params.get("idSite", "1")
    period = params.get("period", "day")
    date_param = params.get("date", "last30")
    segment = params.get("segment", "")
    try:
        filter_limit = int(params.get("filter_limit", "0")) or None
    except ValueError:
        filter_limit = None

    start, end = resolve_window(date_param)
    seg = segment_factor(unquote(segment)) if segment else 1.0

    if id_site_raw == "all":
        site_id = 0
    else:
        try:
            site_id = int(id_site_raw)
        except ValueError:
            site_id = 1

    p = site_profile(site_id) if site_id else None
    totals = range_totals(site_id, start, end, seg) if site_id else None

    # --- account-wide ---
    if method == "MultiSites.getAll":
        rows = []
        for sid in sorted(SITES):
            t = range_totals(sid, start, end, seg)
            sp = site_profile(sid)
            rows.append({
                "idsite": sid,
                "label": sp["label"],
                "main_url": f"https://{sp['domain']}",
                "nb_visits": t["visits"],
                "nb_actions": t["actions"],
                "nb_pageviews": t["actions"],
                "nb_uniq_visitors": t["uniq"],
                "avg_time_on_site": t["avg_time"],
                "bounce_rate": f"{t['bounce']}%",
                "revenue": 0,
            })
        return rows

    if not site_id:
        # Non-MultiSites call with idSite=all: empty-but-valid.
        return {} if method.endswith(".get") else []

    # --- summary objects ---
    if method == "VisitsSummary.get":
        if period == "range":
            return visits_summary_totals(totals)
        # Keyed map, one entry per period bucket (portal only uses period=day).
        out = {}
        if period == "day":
            for day in iter_days(start, end):
                m = day_metrics(site_id, day)
                key_totals = range_totals(site_id, day, day, seg)
                out[day.isoformat()] = visits_summary_totals(key_totals)
                del m
        else:
            step = {"week": 7, "month": 30, "year": 365}.get(period, 7)
            cursor = start
            while cursor <= end:
                bucket_end = min(end, cursor + dt.timedelta(days=step - 1))
                out[cursor.isoformat()] = visits_summary_totals(
                    range_totals(site_id, cursor, bucket_end, seg))
                cursor = bucket_end + dt.timedelta(days=1)
        return out

    if method == "VisitFrequency.get":
        rng = random.Random(
            f"{SEED_NS}:freq:{site_id}:{start.isoformat()}:{end.isoformat()}")
        new_share = rng.uniform(0.58, 0.68)
        v_new = round(totals["visits"] * new_share)
        v_ret = totals["visits"] - v_new
        u_new = round(totals["uniq"] * min(1.0, new_share + 0.05))
        u_ret = max(0, totals["uniq"] - u_new)
        return {
            "nb_visits_new": v_new,
            "nb_uniq_visitors_new": u_new,
            "nb_users_new": 0,
            "nb_actions_new": round(totals["actions"] * new_share),
            "max_actions_new": 12,
            "bounce_rate_new": f"{min(75, totals['bounce'] + 6)}%",
            "avg_time_on_site_new": max(40, totals["avg_time"] - 30),
            "nb_visits_returning": v_ret,
            "nb_uniq_visitors_returning": u_ret,
            "nb_users_returning": 0,
            "nb_actions_returning": totals["actions"] - round(totals["actions"] * new_share),
            "max_actions_returning": 16,
            "bounce_rate_returning": f"{max(15, totals['bounce'] - 8)}%",
            "avg_time_on_site_returning": totals["avg_time"] + 45,
        }

    if method == "Goals.get":
        c = totals["conversions"]
        rng = random.Random(
            f"{SEED_NS}:goals:{site_id}:{start.isoformat()}:{end.isoformat()}")
        aov = rng.uniform(25, 90)
        visited = max(c, round(c * 1.06))
        rate = round(c / totals["visits"] * 100, 1) if totals["visits"] else 0
        return {
            "nb_conversions": c,
            "nb_visits_converted": visited,
            "conversion_rate": f"{rate}%",
            "revenue": round(c * aov, 2),
        }

    # --- ranked lists ---
    if method in ("Actions.getPageUrls", "Actions.getEntryPageUrls",
                  "Actions.getExitPageUrls"):
        return pages_rows(site_id, start, end, method, totals,
                          filter_limit, seg)

    if method == "Actions.getPageTitles":
        items = [pretty_title(path, p["label"])
                 for path in PAGES.get(p["industry"], PAGES["default"])]

        def extra(lbl, val, rng):
            return {"nb_hits": round(val * rng.uniform(1.15, 1.6))}
        return simple_rows(site_id, start, end, method, items, totals, 0.9,
                           "nb_visits", filter_limit, extra_fn=extra)

    if method == "Actions.getOutlinks":
        items = OUTLINKS.get(p["industry"], OUTLINKS["default"])

        def extra(lbl, val, rng):
            return {"nb_hits": round(val * rng.uniform(1.0, 1.3)),
                    "url": f"https://{lbl}"}
        return simple_rows(site_id, start, end, method, items, totals, 0.07,
                           "nb_visits", filter_limit, extra_fn=extra)

    if method == "Actions.getDownloads":
        items = DOWNLOADS.get(p["industry"], DOWNLOADS["default"])

        def extra(lbl, val, rng):
            return {"nb_hits": round(val * rng.uniform(1.0, 1.2)),
                    "url": f"https://{p['domain']}/{lbl}"}
        return simple_rows(site_id, start, end, method, items, totals, 0.04,
                           "nb_visits", filter_limit, extra_fn=extra)

    if method == "Referrers.getReferrerType":
        items = [(lbl, CHANNEL_SHARES[key]) for lbl, key in REFERRER_TYPES]
        return simple_rows(site_id, start, end, method, items, totals, 1.0,
                           "nb_visits", filter_limit)

    if method == "Referrers.getWebsites":
        items = REFERRER_WEBSITES.get(p["industry"],
                                      REFERRER_WEBSITES["default"])
        return simple_rows(site_id, start, end, method, items, totals,
                           CHANNEL_SHARES["website"], "nb_visits",
                           filter_limit)

    if method == "Referrers.getSearchEngines":
        return simple_rows(site_id, start, end, method, SEARCH_ENGINES,
                           totals, CHANNEL_SHARES["search"], "nb_visits",
                           filter_limit)

    if method == "Referrers.getSocials":
        pool = (SOCIALS_PROFESSIONAL if p["industry"] in ("law", "fund", "studio")
                else SOCIALS_CONSUMER)
        return simple_rows(site_id, start, end, method, pool, totals,
                           CHANNEL_SHARES["social"], "nb_visits",
                           filter_limit)

    if method == "DevicesDetection.getType":
        return simple_rows(site_id, start, end, method, DEVICE_TYPES, totals,
                           1.0, "nb_visits", filter_limit)

    if method == "DevicesDetection.getBrowsers":
        return simple_rows(site_id, start, end, method, BROWSERS, totals,
                           1.0, "nb_visits", filter_limit)

    if method == "DevicesDetection.getOsFamilies":
        return simple_rows(site_id, start, end, method, OS_FAMILIES, totals,
                           1.0, "nb_visits", filter_limit)

    if method == "UserCountry.getCountry":
        return simple_rows(site_id, start, end, method, COUNTRIES, totals,
                           1.0, "nb_visits", filter_limit)

    if method == "UserCountry.getRegion":
        return simple_rows(site_id, start, end, method, REGIONS, totals,
                           0.95, "nb_visits", filter_limit)

    if method == "UserCountry.getCity":
        return simple_rows(site_id, start, end, method, CITIES, totals,
                           0.88, "nb_visits", filter_limit)

    if method == "VisitTime.getVisitInformationPerServerTime":
        rng = random.Random(
            f"{SEED_NS}:hours:{site_id}:{start.isoformat()}:{end.isoformat()}")
        weights = []
        for hour in range(24):
            w = math.exp(-((hour - 13.5) / 4.5) ** 2) + 0.06
            weights.append(w * rng.uniform(0.85, 1.15))
        wsum = sum(weights)
        return [{"label": str(h),
                 "nb_visits": round(totals["visits"] * weights[h] / wsum),
                 "nb_actions": round(totals["actions"] * weights[h] / wsum)}
                for h in range(24)]

    if method == "Events.getCategory":
        items = EVENT_CATEGORIES.get(p["industry"], EVENT_CATEGORIES["default"])

        def extra(lbl, val, rng):
            return {"nb_visits": max(1, round(val * 0.8)),
                    "nb_events_with_value": 0, "sum_event_value": 0}
        return simple_rows(site_id, start, end, method, items, totals, 0.11,
                           "nb_events", filter_limit, extra_fn=extra)

    if method == "Live.getLastVisitsDetails":
        n = filter_limit or 10
        today = dt.date.today()
        rng = random.Random(f"{SEED_NS}:live:{site_id}:{today.isoformat()}")
        now_ts = int(dt.datetime.combine(
            today, dt.time(hour=12), tzinfo=dt.timezone.utc).timestamp())
        pages_pool = PAGES.get(p["industry"], PAGES["default"])
        countries = [c for c, _ in COUNTRIES]
        devices = ["desktop", "smartphone", "tablet"]
        browsers = [b for b, _ in BROWSERS]
        ref_types = ["direct", "search", "website", "social"]
        rows = []
        ts = now_ts
        for i in range(n):
            ts -= rng.randint(240, 5400)
            actions = rng.randint(1, 7)
            detail_paths = rng.sample(pages_pool,
                                      k=min(actions, 5, len(pages_pool)))
            rtype = rng.choice(ref_types)
            rname = {"direct": "", "search": "Google",
                     "website": rng.choice(REFERRER_WEBSITES.get(
                         p["industry"], REFERRER_WEBSITES["default"])),
                     "social": "Instagram"}[rtype]
            mins = rng.randint(0, 9)
            secs = rng.randint(5, 59)
            when = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
            rows.append({
                "idVisit": 900000 + site_id * 1000 + i,
                "visitorId": f"{rng.getrandbits(64):016x}",
                "serverTimePretty": when.strftime("%H:%M:%S"),
                "serverDatePretty": when.strftime("%A, %B %d, %Y"),
                "serverTimestamp": ts,
                "lastActionTimestamp": ts,
                "country": rng.choice(countries),
                "deviceType": rng.choices(devices, weights=[58, 36, 6])[0],
                "browserName": rng.choice(browsers),
                "referrerType": rtype,
                "referrerName": rname,
                "visitDurationPretty": f"{mins} min {secs}s",
                "actions": actions,
                "actionDetails": [
                    {"type": "action",
                     "url": f"https://{p['domain']}{path}",
                     "pageTitle": pretty_title(path, p["label"])}
                    for path in detail_paths
                ],
            })
        return rows

    # --- unknown method: empty-but-valid, never a 500 ---
    return {} if method.endswith(".get") else []


# ---------------------------------------------------------------------------
# Migadu mock
# ---------------------------------------------------------------------------

MIGADU_PATH = re.compile(r"^/v1/domains/([^/]+)/mailboxes/?$")

SHARED_BOXES = [("hello", "Front Desk"), ("info", "General Inbox"),
                ("billing", "Billing"), ("team", "Team")]
PEOPLE = [("mara.lindqvist", "Mara Lindqvist"), ("jonas.beck", "Jonas Beck"),
          ("priya.shah", "Priya Shah"), ("theo.grant", "Theo Grant"),
          ("sofia.reyes", "Sofia Reyes"), ("elin.novak", "Elin Novak"),
          ("marcus.hale", "Marcus Hale"), ("avery.stone", "Avery Stone"),
          ("ruben.castillo", "Ruben Castillo"), ("ingrid.olsen", "Ingrid Olsen"),
          ("callum.reid", "Callum Reid"), ("noor.haddad", "Noor Haddad")]


def migadu_mailboxes(domain):
    rng = random.Random(f"{SEED_NS}:migadu:{domain}")
    boxes = []
    for lp, name in rng.sample(SHARED_BOXES, k=rng.randint(2, 3)):
        boxes.append((lp, name, True))
    for lp, name in rng.sample(PEOPLE, k=rng.randint(2, 4)):
        boxes.append((lp, name, True))
    if rng.random() < 0.4:
        boxes.append(("archive", "Archive", False))
    return {
        "mailboxes": [
            {
                "address": f"{lp}@{domain}",
                "local_part": lp,
                "name": name,
                "is_active": active,
                "may_send": active,
                "may_receive": active,
            }
            for lp, name, active in boxes
        ]
    }


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "elk-os-mocks/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[mocks] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _matomo(self, params):
        method = params.get("method", "")
        module = params.get("module", "")
        if module != "API" or not method:
            self._send(200, {"result": "error",
                             "message": "Expected module=API and a method."})
            return
        token = params.get("token_auth", "")
        if not token or (EXPECTED_TOKEN and token != EXPECTED_TOKEN):
            self._send(200, {"result": "error",
                             "message": "token_auth authentication failed."})
            return
        try:
            self._send(200, handle_matomo(params))
        except Exception as exc:  # never leak a stack as a 500
            self._send(200, {"result": "error", "message": f"mock: {exc}"})

    def _flatten(self, qs):
        return {k: v[0] for k, v in qs.items() if v}

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/index.php":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8", "replace")
            params = self._flatten(parse_qs(raw))
            # Merge query-string params too; Matomo accepts both.
            params = {**self._flatten(parse_qs(parsed.query)), **params}
            self._matomo(params)
            return
        self._send(404, {"error": "not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send(200, {"ok": True, "service": "elk-os-mocks"})
            return
        if parsed.path == "/index.php":
            self._matomo(self._flatten(parse_qs(parsed.query)))
            return
        m = MIGADU_PATH.match(parsed.path)
        if m:
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Basic "):
                self._send(401, {"error": "Invalid credentials"})
                return
            domain = unquote(m.group(1)).strip().lower()
            if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
                self._send(400, {"error": "Invalid domain"})
                return
            self._send(200, migadu_mailboxes(domain))
            return
        self._send(404, {"error": "not found"})


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[mocks] elk-os-mocks listening on :{PORT} "
          f"(Matomo POST /index.php, Migadu GET /v1/domains/<domain>/mailboxes)",
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
