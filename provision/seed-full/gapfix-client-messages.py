#!/usr/bin/env python3
"""Gap-fix: top up org-2 (Cedar & Co Coffee) message threads so the client
portal message center feels lived-in (verifier asked for 5-8 org-scoped
threads; D4 seeded 2 for org 2). Adds 4 threads with 3-5 alternating
client/team messages each. Existing rows are never edited.

Write pattern copied from seed-D4.py (REV 3): Directus stamps date_created at
create time, so every backdated row is POST create followed by PATCH
{date_created: deterministic}. Thread markers (last_message_at,
team_last_read_at, client_last_read_at) are choreographed from READ-BACK
stored message timestamps. Upsert keys: threads (organization, subject);
messages (thread, date_created) with a (thread, body) repair fallback.

Deterministic base 2026-06-20T10:15:00Z (disjoint from D4's 2026-06-04 grid)
so re-runs match and D4 rows are untouched. All rows is_test_data false.
Token loaded inside this script, never printed.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://cms.musterr.dev"
UTC = timezone.utc
BASE_TS = datetime(2026, 6, 20, 10, 15, 0, tzinfo=UTC)
THREAD_STEP = timedelta(days=5)
MSG_STEP = timedelta(hours=6, minutes=23)

ORG_CEDAR = 2
CLIENT_USER = "91fb50ea-5ead-4713-9c48-a32bb945932f"  # Rowan Ashford (client@muster.dev)
TEAM_FALLBACK = [
    "78cf2976-e1da-4b8b-b238-822bcbe1b8fb",  # felix.anders@team.musterr.dev
    "86f5c9cd-b6fb-4d43-bb5c-2050e66c7f40",  # aisha.karim@team.musterr.dev
    "a043509e-00b1-4d4c-b613-fd0d30b878db",  # tom.beckett@team.musterr.dev
]


def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def request(method, path, payload=None, retries=3):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(retries):
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + TOKEN}
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                return r.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            try:
                return e.code, json.loads(body)
            except Exception:
                return e.code, {"_raw": body[:400]}
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    return 0, {}


COUNTS = {}


def bump(coll, key, n=1):
    COUNTS.setdefault(coll, {"created": 0, "updated": 0, "skipped": 0, "failed": 0})
    COUNTS[coll][key] += n


def q(s):
    return urllib.parse.quote(s, safe="")


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def same_ts(a, b):
    pa = parse_ts(a) if isinstance(a, str) else a
    pb = parse_ts(b) if isinstance(b, str) else b
    if pa is None or pb is None:
        return False
    return abs((pa - pb).total_seconds()) < 2


def list_items(coll, qs):
    st, r = request("GET", "/items/%s?%s" % (coll, qs))
    if st != 200:
        print("  WARN list %s -> %s %s" % (coll, st, json.dumps(r)[:200]))
        return []
    return r.get("data") or []


def create_backdated(coll, payload, det):
    st, r = request("POST", "/items/%s" % coll, payload)
    if st not in (200, 201):
        print("  FAIL create %s -> %s %s" % (coll, st, json.dumps(r)[:300]))
        bump(coll, "failed")
        return None
    rid = r["data"]["id"]
    st2, r2 = request("PATCH", "/items/%s/%s" % (coll, rid), {"date_created": iso(det)})
    if st2 != 200:
        print("  WARN backdate %s/%s -> %s" % (coll, rid, st2))
    bump(coll, "created")
    return rid


def repair_dc(coll, rid, current, det):
    if same_ts(current, det):
        bump(coll, "skipped")
        return
    st, _ = request("PATCH", "/items/%s/%s" % (coll, rid), {"date_created": iso(det)})
    bump(coll, "updated" if st == 200 else "failed")


def resolve_team_rotation():
    ids = []
    for email, fb in [("felix.anders@team.musterr.dev", TEAM_FALLBACK[0]),
                      ("aisha.karim@team.musterr.dev", TEAM_FALLBACK[1]),
                      ("tom.beckett@team.musterr.dev", TEAM_FALLBACK[2])]:
        st, r = request("GET", "/users?filter[email][_eq]=%s&fields=id" % q(email))
        rows = (r.get("data") or []) if st == 200 else []
        ids.append(rows[0]["id"] if rows else fb)
    return ids


# choreography: emp_unread = latest msg from client, team marker behind;
# client_unread = latest msg from team, client marker behind; read = both level.
THREADS = [
    (ORG_CEDAR, "Wholesale portal beta invite list", "open", "client_unread", [
        ("client", "We have the first batch of wholesale accounts ready for the beta. Fourteen cafes and two grocery partners. Where should we send the list?"),
        ("team", "Nice list. Drop the spreadsheet in the shared folder and we will import them into the wholesale portal staging environment."),
        ("client", "Uploaded. Two of the cafes share a billing contact, flagging in case that matters for account setup."),
        ("team", "Good flag. Shared billing contacts are supported, each cafe still gets its own ordering login. Import runs tomorrow morning."),
        ("team", "Import finished. All sixteen accounts are live on staging and invite emails are queued for your go-ahead."),
    ]),
    (ORG_CEDAR, "Holiday menu photography", "open", "emp_unread", [
        ("team", "Planning ahead for the holiday menu launch. Do you want us to book the same photographer as the spring shoot?"),
        ("client", "Yes, she was great. We will have six new drinks and two pastry boxes to shoot."),
        ("team", "Booked for the second week of August. Send over the drink names when the menu is final so we can prep the shot list."),
        ("client", "Menu is final. Sending the names and a few reference photos from our test kitchen this afternoon."),
    ]),
    (ORG_CEDAR, "Gift card integration question", "closed", "read", [
        ("client", "A customer asked whether online gift cards will work in store as well. Is that part of the current build?"),
        ("team", "Yes. Gift cards purchased online generate a code that the register accepts, and balances stay in sync both ways."),
        ("client", "Perfect, that is what we hoped. We will mention it in the newsletter."),
        ("team", "Sounds good. Closing this one out, reopen any time if the register sync raises questions."),
    ]),
    (ORG_CEDAR, "June analytics recap", "closed", "read", [
        ("team", "June recap is in your portal. Sessions up 9 percent, and the wholesale landing page is now the third most visited page."),
        ("client", "Encouraging numbers, thanks. The wholesale interest lines up with what we hear at the counter."),
        ("team", "Agreed, it supports the beta timing. Full report is under Analytics in the portal whenever you want the detail."),
    ]),
]


def msg_time(i, j):
    return BASE_TS + i * THREAD_STEP + j * MSG_STEP


def thread_time(i):
    return msg_time(i, 0) - timedelta(minutes=30)


def seed_threads():
    ids = []
    for i, (org, subject, status, _cho, _msgs) in enumerate(THREADS):
        det = thread_time(i)
        rows = list_items(
            "os_message_threads",
            "filter[organization][_eq]=%s&filter[subject][_eq]=%s&fields=id,date_created&limit=1"
            % (org, q(subject)))
        if rows:
            ids.append(rows[0]["id"])
            repair_dc("os_message_threads", rows[0]["id"], rows[0].get("date_created"), det)
            continue
        rid = create_backdated(
            "os_message_threads",
            {"organization": org, "subject": subject, "status": status,
             "user_created": CLIENT_USER if _msgs[0][0] == "client" else None,
             "is_test_data": False},
            det)
        ids.append(rid)
    return ids


def seed_messages(thread_ids, rotation):
    for i, (_org, _subject, _status, _cho, msgs) in enumerate(THREADS):
        tid = thread_ids[i]
        if not tid:
            continue
        existing = list_items(
            "os_messages",
            "filter[thread][_eq]=%s&fields=id,date_created,body&limit=200" % tid)
        for j, (role, body) in enumerate(msgs):
            det = msg_time(i, j)
            hit = next((e for e in existing if same_ts(e.get("date_created"), det)), None)
            if hit is None:
                hit = next((e for e in existing if e.get("body") == body), None)
                if hit is not None:
                    repair_dc("os_messages", hit["id"], hit.get("date_created"), det)
                    continue
            if hit is not None:
                bump("os_messages", "skipped")
                continue
            author = rotation[(i * 3 + j) % len(rotation)] if role == "team" else CLIENT_USER
            create_backdated(
                "os_messages",
                {"thread": tid, "author_role": role, "author": author, "body": body,
                 "is_test_data": False},
                det)


def choreograph(thread_ids):
    for i, (_org, subject, _status, cho, msgs) in enumerate(THREADS):
        tid = thread_ids[i]
        if not tid:
            continue
        rows = list_items(
            "os_messages",
            "filter[thread][_eq]=%s&fields=id,date_created,author_role&limit=200" % tid)
        rows = [r for r in rows if parse_ts(r.get("date_created"))]
        rows.sort(key=lambda r: parse_ts(r["date_created"]))
        if len(rows) < 2:
            print("  WARN thread %s has %d messages, skipping markers" % (subject, len(rows)))
            continue
        latest, second = rows[-1], rows[-2]
        if latest["author_role"] != msgs[-1][0]:
            print("  ASSERT FAIL thread %s latest role %s != expected %s"
                  % (subject, latest["author_role"], msgs[-1][0]))
        last_at = latest["date_created"]
        if cho == "emp_unread":
            team_read, client_read = second["date_created"], latest["date_created"]
        elif cho == "client_unread":
            team_read, client_read = latest["date_created"], second["date_created"]
        else:
            team_read = client_read = latest["date_created"]
        st, r = request("GET", "/items/os_message_threads/%s?fields=id,last_message_at,team_last_read_at,client_last_read_at" % tid)
        cur = r.get("data", {}) if st == 200 else {}
        if (same_ts(cur.get("last_message_at"), last_at)
                and same_ts(cur.get("team_last_read_at"), team_read)
                and same_ts(cur.get("client_last_read_at"), client_read)):
            bump("thread_markers", "skipped")
        else:
            st2, _ = request("PATCH", "/items/os_message_threads/%s" % tid,
                             {"last_message_at": last_at,
                              "team_last_read_at": team_read,
                              "client_last_read_at": client_read})
            bump("thread_markers", "updated" if st2 == 200 else "failed")


def main():
    rotation = resolve_team_rotation()
    tids = seed_threads()
    seed_messages(tids, rotation)
    choreograph(tids)
    for coll, c in sorted(COUNTS.items()):
        print("%s: created %d / updated %d / skipped %d / failed %d"
              % (coll, c["created"], c["updated"], c["skipped"], c["failed"]))
    st, r = request("GET", "/items/os_message_threads?filter[organization][_eq]=2&aggregate[count]=id")
    print("org2 thread total:", (r.get("data") or [{}])[0])


if __name__ == "__main__":
    main()
