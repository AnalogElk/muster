# Muster Seed Shared Client — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the duplicated env-loading / request / upsert helpers in the Muster provision seed scripts into one configurable shared client per language, porting each script to it while proving — via golden request-sequence tests against a stubbed transport — that every port's HTTP sequence is byte-identical to the original.

**Architecture:** A characterization harness runs each *real, unmodified* script as a subprocess under a monkeypatched transport (urllib for Python, global `fetch` for TS) with a deterministic synthetic Directus responder and frozen clock/uuid/random. It records the exact ordered request sequence to a committed JSONL golden. We first lock all goldens against current code, then extract the shared client, then port scripts one at a time — a port is accepted only when its re-recorded sequence equals its golden byte-for-byte.

**Tech Stack:** Python 3.9 (stdlib `urllib`, `runpy`), pytest 8.4, freezegun (test-only, time freezing); TypeScript via `tsx` + vitest (`portal/.build`).

## Global Constraints

- **Byte-identical bar:** a port is accepted iff its recorded sequence of `(method, absolute URL, canonical headers, exact body bytes)` equals the golden. Body bytes must match exactly — the client must serialize with `json.dumps(payload).encode()` (default separators `(', ', ': ')`, **no** `sort_keys`), matching every call site.
- **No secrets in goldens:** the harness injects a FAKE token `SEED_TEST_TOKEN`; a real token must never appear in any golden or output (DevProd §2).
- **Preserve behavior, don't fix it:** reproduce each script's current behavior exactly, including inconsistencies/bugs. Genuine fixes become separate `os_tasks` follow-ups, never folded into a port.
- **Isolation:** all work on branch `chore/muster-seed-shared-client` in worktree `.claude/worktrees/muster-seed-client` (already created off `origin/main` @ 83ecf5b).
- **Local-green before push (DevProd §11):** `pytest` (and `vitest` for the TS half) must pass locally before any push.
- **Determinism:** freeze `time`/`datetime` (freezegun), no-op `time.sleep`, deterministic `uuid.uuid4` (counter), seed `random`. TS: freeze `Date`/`Date.now`, `Math.random`, `crypto.randomUUID`.
- **Scope:** in = ~49 `provision/**.py` that hit Directus + 3 `portal/.build/scripts/seed-*.ts`. Out = 4 `.js` screenshot/render scripts, 3 no-HTTP `.py` (`env-wire-run2.py`, `set-portal-image*.py`).

---

## File Structure

```
tests/characterization/
  harness/
    __init__.py
    determinism.py        # freeze clock/uuid/random; no-op sleep
    responder.py          # deterministic Directus-shaped response policy + per-script overrides
    recorder.py           # RequestRecord dataclass, canonicalization, JSONL (de)serialize
    transport.py          # fake urlopen + FakeResponse/HTTPError construction; installs monkeypatch
    run_script.py         # CLI: runpy a target script under stubs, emit JSONL to stdout/file
  goldens/                # <script-stem>.jsonl  (committed baseline)
  overrides/              # <script-stem>.py  (optional per-script responder fixtures)
  conftest.py             # discovers in-scope scripts; fixtures
  test_seed_sequences.py  # per-script: run under harness, compare to golden
  test_harness_selfcheck.py
  SCOPE.txt               # explicit in-scope script list (generated + committed)
  pytest.ini

provision/seed-full/_client/
  __init__.py
  directus_client.py      # load_env, make_req, make_request, make_upsert, DirectusClient

portal/.build/scripts/_client/          # TS twin (Phase 2)
  directus-seed-client.ts
portal/.build/__tests__/seed-sequences/ # TS goldens + harness (Phase 2)
```

---

## Phase 0 — Characterization harness (Python)

### Task 1: Recorder + canonical golden format

**Files:**
- Create: `tests/characterization/harness/__init__.py` (empty)
- Create: `tests/characterization/harness/recorder.py`
- Test: `tests/characterization/harness/test_recorder.py`

**Interfaces:**
- Produces: `RequestRecord(seq:int, method:str, url:str, headers:dict, body_b64:str, body_sha256:str)`; `canonical_headers(items) -> dict`; `dumps_jsonl(records) -> str`; `loads_jsonl(text) -> list[RequestRecord]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/characterization/harness/test_recorder.py
from harness.recorder import RequestRecord, canonical_headers, dumps_jsonl, loads_jsonl

def test_canonical_headers_sorts_and_masks_bearer():
    h = canonical_headers([("Content-Type", "application/json"),
                            ("Authorization", "Bearer REALTOKEN")])
    assert list(h.items()) == [("authorization", "Bearer <token>"),
                               ("content-type", "application/json")]

def test_jsonl_roundtrip_is_stable():
    r = RequestRecord.build(0, "POST", "https://x/y", [("Authorization", "Bearer t")],
                            b'{"a":1}')
    text = dumps_jsonl([r])
    assert loads_jsonl(text) == [r]
    assert dumps_jsonl(loads_jsonl(text)) == text  # idempotent serialization
```

- [ ] **Step 2: Run it, verify it fails** — `cd tests/characterization && python -m pytest harness/test_recorder.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `recorder.py`**

```python
# tests/characterization/harness/recorder.py
import base64, hashlib, json
from dataclasses import dataclass, asdict

MASK = "Bearer <token>"

def canonical_headers(items):
    out = {}
    for k, v in items:
        lk = k.lower()
        if lk == "authorization" and str(v).startswith("Bearer "):
            v = MASK
        out[lk] = v
    return dict(sorted(out.items()))

@dataclass(frozen=True)
class RequestRecord:
    seq: int
    method: str
    url: str
    headers: tuple      # tuple of (k, v) pairs, canonical-sorted
    body_b64: str
    body_sha256: str

    @classmethod
    def build(cls, seq, method, url, header_items, body: bytes):
        body = body or b""
        return cls(seq, method.upper(), url,
                   tuple(canonical_headers(header_items).items()),
                   base64.b64encode(body).decode(),
                   hashlib.sha256(body).hexdigest())

def dumps_jsonl(records):
    lines = []
    for r in records:
        d = asdict(r); d["headers"] = [list(p) for p in r.headers]
        lines.append(json.dumps(d, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + ("\n" if lines else "")

def loads_jsonl(text):
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(RequestRecord(d["seq"], d["method"], d["url"],
                                  tuple((k, v) for k, v in d["headers"]),
                                  d["body_b64"], d["body_sha256"]))
    return out
```

- [ ] **Step 4: Run tests, verify pass** — same command → PASS.
- [ ] **Step 5: Commit** — `git add tests/characterization/harness && git commit -m "test(seed): golden request-record format + canonicalization"`

---

### Task 2: Determinism shims

**Files:**
- Create: `tests/characterization/harness/determinism.py`
- Test: `tests/characterization/harness/test_determinism.py`

**Interfaces:**
- Produces: `freeze()` context manager freezing time (`2026-01-01T00:00:00Z`), no-op `time.sleep`, deterministic `uuid.uuid4()` (`00000000-0000-4000-8000-0000000000NN`), `random.seed(0)`.

- [ ] **Step 1: Failing test**

```python
# tests/characterization/harness/test_determinism.py
import time, uuid
from harness.determinism import freeze

def test_uuid_and_sleep_are_deterministic():
    with freeze():
        assert str(uuid.uuid4()) == "00000000-0000-4000-8000-000000000000"
        assert str(uuid.uuid4()) == "00000000-0000-4000-8000-000000000001"
        t0 = time.time(); time.sleep(9999); t1 = time.time()
        assert t0 == t1                       # sleep is a no-op, clock frozen
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** (requires `pip install freezegun` — add to `tests/characterization/requirements-dev.txt`)

```python
# tests/characterization/harness/determinism.py
import contextlib, itertools, random, time, uuid
from freezegun import freeze_time

@contextlib.contextmanager
def freeze():
    counter = itertools.count()
    def fake_uuid4():
        n = next(counter)
        return uuid.UUID(f"00000000-0000-4000-8000-{n:012x}")
    real_sleep = time.sleep
    with freeze_time("2026-01-01T00:00:00Z"):
        orig_uuid4, orig_sleep = uuid.uuid4, time.sleep
        uuid.uuid4 = fake_uuid4
        time.sleep = lambda *_a, **_k: None
        random.seed(0)
        try:
            yield
        finally:
            uuid.uuid4 = orig_uuid4
            time.sleep = orig_sleep
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "test(seed): deterministic clock/uuid/sleep shims"`

---

### Task 3: Synthetic responder

**Files:**
- Create: `tests/characterization/harness/responder.py`
- Test: `tests/characterization/harness/test_responder.py`

**Interfaces:**
- Produces: `Responder(overrides=None)` with `respond(method, path, body_bytes) -> (status:int, json_obj)`. Default policy below. `overrides` is an optional `list[(matcher_fn, (status, json))]` consulted first.

**Default policy** (deterministic; drives scripts down their create paths):
- `POST /auth/login` → `200 {"data":{"access_token":"FAKE_DEMO_TOKEN","refresh_token":"FAKE_REFRESH","expires":900000}}`
- `POST /graphql` → `200 {"data":{}}` (no `errors` key → retry loops exit after one attempt)
- `GET` single-resource existence (`/fields/x/y`, `/relations/x/y`, `/items/coll/<id>` with no `?`) → `404 {"errors":[{"message":"not found"}]}`
- `GET` list/query (contains `?` or ends with a collection) → `200 {"data":[]}`
- `POST /items/...`, `POST /fields/...`, `POST /relations`, `POST /users`, etc. → `200 {"data":{"id": <next synthetic id>, "_echo": <parsed body>}}` where synthetic id is `SEED-0001`, `SEED-0002`, … per POST in call order.
- `PATCH ...` → `200 {"data":{"id":"SEED-PATCHED"}}`
- `DELETE ...` → `204` (empty body)
- Anything else → `200 {"data":null}`

- [ ] **Step 1: Failing test**

```python
# tests/characterization/harness/test_responder.py
from harness.responder import Responder

def test_login_existence_and_create_ids_are_deterministic():
    r = Responder()
    assert r.respond("POST", "/auth/login", b"{}")[1]["data"]["access_token"] == "FAKE_DEMO_TOKEN"
    assert r.respond("GET", "/fields/os_tasks/workspace", None)[0] == 404
    assert r.respond("GET", "/items/os_tasks?limit=1", None) == (200, {"data": []})
    a = r.respond("POST", "/items/os_tasks", b'{"x":1}')[1]["data"]["id"]
    b = r.respond("POST", "/items/os_tasks", b'{"x":2}')[1]["data"]["id"]
    assert (a, b) == ("SEED-0001", "SEED-0002")

def test_override_wins():
    r = Responder(overrides=[(lambda m, p, _b: p == "/items/organizations",
                              (200, {"data": [{"id": 1, "name": "Demo Co"}]}))])
    assert r.respond("GET", "/items/organizations?x=1", None)[1]["data"][0]["id"] == 1
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `responder.py`** per the default-policy list above (a POST counter for `SEED-000N`, `?`/single-resource path heuristics, overrides consulted first).
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "test(seed): deterministic synthetic Directus responder"`

---

### Task 4: Transport monkeypatch + run_script CLI

**Files:**
- Create: `tests/characterization/harness/transport.py`
- Create: `tests/characterization/harness/run_script.py`
- Test: `tests/characterization/harness/test_harness_selfcheck.py` (+ fixture `tests/characterization/harness/_fake_script.py`)

**Interfaces:**
- Consumes: `Responder`, `freeze()`, `RequestRecord`.
- Produces: `install_transport(recorder_list, responder) -> restore_fn` patching `urllib.request.urlopen`; `run_script.main(argv)` → runpy-executes a target under `freeze()` + installed transport and prints `dumps_jsonl(records)` to stdout.

`transport.py` builds a `FakeResponse` (context manager, `.read()`, `.status`, `.headers`) for 2xx and raises `urllib.error.HTTPError(url, code, msg, hdrs, BytesIO(body))` for ≥400 so scripts' `except HTTPError` paths run. It records from the `urllib.request.Request`: `req.get_method()`, `req.full_url`, `req.header_items()`, `req.data`.

- [ ] **Step 1: Failing test** — a tiny `_fake_script.py` that does a GET-existence then a POST via `urllib`, asserting the harness records exactly 2 requests with masked auth and stable body bytes across two runs.

```python
# tests/characterization/harness/test_harness_selfcheck.py
import subprocess, sys, pathlib
from harness.recorder import loads_jsonl
HERE = pathlib.Path(__file__).parent

def _run():
    out = subprocess.run([sys.executable, "-m", "harness.run_script",
                          str(HERE / "_fake_script.py")],
                         cwd=HERE.parent, capture_output=True, text=True, check=True)
    return out.stdout

def test_selfcheck_is_deterministic_and_masked():
    a, b = _run(), _run()
    assert a == b                                   # byte-identical across runs
    recs = loads_jsonl(a)
    assert [r.method for r in recs] == ["GET", "POST"]
    assert all(dict(r.headers).get("authorization") in (None, "Bearer <token>") for r in recs)
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `transport.py` + `run_script.py` + `_fake_script.py`.** `run_script.main`: build `records=[]`, `Responder()`, `install_transport`, then `with freeze(): runpy.run_path(target, run_name="__main__")` inside a try/except that still dumps whatever was recorded (so partial runs lock their prefix); print `dumps_jsonl(records)`. Inject env: set `HOME` to a temp dir containing `elk-os/.env` with `DIRECTUS_ADMIN_TOKEN=SEED_TEST_TOKEN`, and `DIRECTUS_URL` unset.
- [ ] **Step 4: Run, verify pass** (run twice in the test → identical).
- [ ] **Step 5: Commit** — `git commit -am "test(seed): urllib transport stub + run_script harness (self-check green)"`

**Note for implementer:** grep the corpus for `from urllib.request import urlopen` / `from urllib.request import Request`. Any script using the unqualified import needs the patch applied to that name too — handle in `install_transport` by also patching `urllib.request.Request` consumers if found. F1/D1 use qualified `urllib.request.urlopen`, which the module-attribute patch covers.

---

### Task 5: Scope list + per-script golden test + baseline generation

**Files:**
- Create: `tests/characterization/conftest.py`, `test_seed_sequences.py`, `pytest.ini`, `SCOPE.txt`
- Create (generated, committed): `tests/characterization/goldens/*.jsonl`

**Interfaces:**
- Consumes: `run_script` (via subprocess), `loads_jsonl`.
- Produces: `SCOPE.txt` (one script path per line); `gen_goldens.py` runner; `test_seed_sequences.py` parametrized over `SCOPE.txt`.

- [ ] **Step 1:** Build `SCOPE.txt` — enumerate `provision/*.py` + `provision/seed-full/*.py`, drop the 3 no-HTTP scripts (`env-wire-run2.py`, `set-portal-image.py`, `set-portal-image-csp2.py`); commit the list. Add a step in the test that fails if a new in-scope script appears without a golden (drift guard).
- [ ] **Step 2: Write `test_seed_sequences.py`** (parametrized): for each script, run harness subprocess, `loads_jsonl(stdout)`, compare to `goldens/<stem>.jsonl`; on mismatch, emit a unified diff of the two JSONL texts.
- [ ] **Step 3: Generate baseline** — `python gen_goldens.py --all` writes `goldens/<stem>.jsonl` for every scope entry from the **current, unrefactored** code. Manually spot-check 3 goldens (F1, D1, one gapfix) for: masked bearer only, no real secret substring, plausible request count. Add per-script responder `overrides/*.py` where a script crashed too early (iterate until each golden captures a meaningful prefix or full run); document any script that can only be partially exercised in `SCOPE.txt` as `# partial: <reason>`.
- [ ] **Step 4: Run `pytest` — all green against current code** (goldens match themselves). This is the safety net.
- [ ] **Step 5: Commit** — `git add tests/characterization && git commit -m "test(seed): lock baseline HTTP request-sequence goldens for all in-scope scripts"`

**⚠️ Gate:** Do not start Phase 1 until Task 5 is committed and green. The goldens are the only thing that makes the refactor safe.

---

## Phase 1 — Shared Python client + ports

### Task 6: `directus_client.py` (extraction, unit-tested in isolation)

**Files:**
- Create: `provision/seed-full/_client/__init__.py`, `provision/seed-full/_client/directus_client.py`
- Test: `tests/characterization/harness/test_directus_client.py`

**Interfaces:**
- Produces:
  - `load_env(path="~/elk-os/.env") -> dict` — identical to the 47 copies (strip, skip `#`/blank, `partition("=")`).
  - `make_req(base, token, *, timeout=45, none_token_means="no_auth") -> req(method, path, payload=None, token=<default>, raw_url=None) -> (status, json|None)` — reproduces F1-style `req`: swallow all HTTP errors, `(0, {"errors":[...]})` on transport error, `json.dumps(payload).encode()` body, `token=None` ⇒ omit auth header.
  - `make_request(base, token, *, timeout=60, retries=3, no_auth_sentinel="__no_auth__", retry_on=(lambda code: code>=500), backoff=lambda a: 2*(a+1)) -> request(method, path, payload=None, token=None, retries=<default>) -> (status, json|{})` — reproduces D1-style: retry 5xx + URLError with backoff, raise URLError after final attempt, `(code, {"_raw": body})` on <500 HTTPError, `token=None` ⇒ use default TOKEN, `token==sentinel` ⇒ omit auth.
  - `make_upsert(request_fn, bump=None) -> upsert(coll, filters, payload) -> (id, created_bool)` — GET `?filter[f][_eq]=..&fields=id&limit=1`, POST on miss.

- [ ] **Step 1: Failing tests** — drive `make_req` and `make_request` with a fake `urlopen` (reuse `transport.install_transport`) and assert: body bytes equal `json.dumps(payload).encode()`; F1 `token=None` omits the Authorization header; D1 `token=None` sends `Bearer <default>`; D1 `token="__no_auth__"` omits it; D1 retries exactly 3× on a 500 then returns `(500, {"_raw": ...})`.

```python
def test_req_swallows_and_omits_auth_when_token_none(fake_transport):
    req = make_req("https://cms.musterr.dev", "DEF", timeout=45)
    st, _ = req("GET", "/items/x?limit=1", token=None)
    rec = fake_transport.records[-1]
    assert "authorization" not in dict(rec.headers)

def test_request_token_none_uses_default_bearer(fake_transport):
    request = make_request("https://cms.musterr.dev", "DEF")
    request("GET", "/items/x?limit=1")
    assert dict(fake_transport.records[-1].headers)["authorization"] == "Bearer <token>"
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `directus_client.py`** with the three factories + `load_env`, matching the reference bodies in `seed-F1.py:38-58` and `seed-D1.py:56-130` exactly.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(seed): shared directus_client (load_env + req/request/upsert factories)"`

**⚠️ No script is modified in this task.** The client is proven in isolation before any port.

---

### Task 7: Worked port #1 — `seed-F1.py` (req-style)

**Files:** Modify `provision/seed-full/seed-F1.py`

**Port procedure (the template every port follows):**
1. Replace the inline `load_env`, `TOKEN = load_env()[...]`, and `def req(...)` block with:

```python
from _client.directus_client import load_env, make_req   # via sys.path insert of _client's parent
TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]
req = make_req(BASE, TOKEN, timeout=45)     # none_token_means="no_auth" (F1 default)
```
   (Add `import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__)))` so `_client` resolves when run as a script from any cwd.)
2. Leave every call site (`req("GET", ...)`, `req("POST", ...)`) untouched.

- [ ] **Step 1:** Apply the port edit above to `seed-F1.py`.
- [ ] **Step 2: Re-run its golden** — `python -m pytest test_seed_sequences.py -k seed-F1 -v`.
- [ ] **Step 3:** Expected: **PASS** (byte-identical). If FAIL, read the unified diff; the usual culprit is body serialization or an auth-header difference. Fix the client/knobs (never the golden) until identical.
- [ ] **Step 4:** Confirm `python provision/seed-full/seed-F1.py --help`-equivalent import still works (module imports without error under the harness).
- [ ] **Step 5: Commit** — `git commit -am "refactor(seed): port seed-F1 to shared client (golden byte-identical)"`

---

### Task 8: Worked port #2 — `seed-D1.py` (request + upsert, NO_AUTH sentinel)

**Files:** Modify `provision/seed-full/seed-D1.py`

- [ ] **Step 1:** Replace `load_env`/`TOKEN`/`def request`/`def upsert` with:

```python
from _client.directus_client import load_env, make_request, make_upsert
TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]
request = make_request(BASE, TOKEN, timeout=60, retries=3, no_auth_sentinel=NO_AUTH)
upsert = make_upsert(request, bump=bump)   # keep local bump()/COUNTS as-is
```
   Keep `NO_AUTH`, `COUNTS`, `bump`, `q`, `find_one` call sites unchanged (`find_one` may stay local as it only calls `request`).
- [ ] **Step 2: Re-run golden** — `pytest test_seed_sequences.py -k seed-D1 -v`.
- [ ] **Step 3:** Expected PASS. Debug via diff if not (watch the `fields=id&limit=1` query string and retry semantics).
- [ ] **Step 4:** Sanity import.
- [ ] **Step 5: Commit** — `git commit -am "refactor(seed): port seed-D1 to shared client (golden byte-identical)"`

---

### Task 9: Port the remaining in-scope Python scripts (fan-out)

**Files:** Modify each remaining `provision/**.py` in `SCOPE.txt` (≈47).

This task is executed as a **Workflow fan-out**: one sub-agent per script, each following the Task 7/8 port procedure, gated by its golden. Group by helper style so each agent picks the right factory + knobs:

- **req-style** (`timeout=45`, swallow, `token=None`⇒no-auth): most `gapfix-*`, `seed-D2/D3/D6`, `seed-F2/F3`, probes → `make_req`.
- **request-style** (`retries`, 5xx backoff, sentinel): `seed-D4`, `seed-F4`, `run2-*` → `make_request`.
- **get/post/patch wrappers** (e.g. `seed-D5`): port the underlying `request`/`req` to the factory; keep the thin `get/post/patch` wrappers locally (they just prefix method).
- **`ENV[...]` token** (`seed-D5`, `seed-F3`): pass `token=load_env()[...]`; if a script reads `os.environ` for the token, preserve that exact source.

**Per-script procedure (each agent):**
- [ ] Read the script's helper block; identify factory + knobs (timeout, retries, auth-none semantics, token source, BASE source).
- [ ] Apply the port edit (replace helper block with factory call; leave call sites untouched).
- [ ] Run `pytest test_seed_sequences.py -k <stem> -v`.
- [ ] **Accept only on byte-identical PASS.** On mismatch: read the diff, adjust knobs (or, if the script's helper had a genuinely unique behavior not covered by the factories, extend the factory with a new opt-in knob + a unit test — do **not** fork the client per script, and do **not** edit the golden).
- [ ] Commit per script: `refactor(seed): port <stem> to shared client (golden byte-identical)`.

- [ ] **Final step:** run the **full** suite `pytest tests/characterization -q` → all goldens green; confirm no golden file changed in git (`git status` shows only script edits, never `goldens/*.jsonl`). Confirm every in-scope script now imports from `_client` (grep: zero remaining local `def load_env`/`def req`/`def request` in scope, except intentional local wrappers).

---

## Phase 2 — TypeScript twin (`portal/.build`)

### Task 10: TS harness + goldens for the 3 seed scripts

**Files:**
- Regenerate `portal/.build` into the worktree first: `bash portal/prepare-context.sh` (it is gitignored/absent in a fresh worktree).
- Create: `portal/.build/__tests__/seed-sequences/harness.ts` (fetch stub + record + freeze `Date`/`Math.random`/`crypto.randomUUID`), `run-seed.ts` (`--import` preload), `seed-sequences.test.ts`, `goldens/*.jsonl`.

- [ ] **Step 1:** Implement the fetch-stub harness: `vi.stubGlobal("fetch", recorder)`, `vi.setSystemTime(new Date("2026-01-01T00:00:00Z"))`, stub `Math.random`/`crypto.randomUUID`; record `{seq, method, url, headers(canonical, bearer-masked), body_b64, body_sha256}` with the **same** canonical/JSONL format as Python.
- [ ] **Step 2:** Drive each script via subprocess `tsx --import ./run-seed.ts scripts/seed-<x>.ts` with `DIRECTUS_URL`/`DIRECTUS_TOKEN`/`ELK_CMS_TOKEN=SEED_TEST_TOKEN` fixed; same synthetic-responder policy as Python.
- [ ] **Step 3:** Generate + commit `goldens/*.jsonl` for `seed-acme-invoices`, `seed-help-articles`, `seed-kb` from current code. Note: `seed-acme-invoices` uses `new Date()` for `SUFFIX`/due dates — verify the frozen clock makes the invoice numbers/dates deterministic in the golden.
- [ ] **Step 4:** `pnpm test seed-sequences` → green against current code.
- [ ] **Step 5: Commit** — `git commit -m "test(seed): lock TS seed-*.ts request-sequence goldens"`

### Task 11: TS shared client + ports

**Files:** Create `portal/.build/scripts/_client/directus-seed-client.ts`; modify the 3 `seed-*.ts`.

- [ ] **Step 1:** Extract `loadDirectusEnv()` (union of the two env conventions: `DIRECTUS_URL||NEXT_PUBLIC_DIRECTUS_URL||default`, `ELK_CMS_TOKEN||DIRECTUS_TOKEN`) and a configurable `directusFetch(client, method, path, body?)` matching each script's current `api()`/`directusFetch()` (throw-on-!ok, `.data` unwrap, header shape). Unit-test in isolation.
- [ ] **Step 2:** Port `seed-help-articles.ts` and `seed-kb.ts` (already share `directusFetch<T>(client,...)` shape) → shared client; keep their exported pure functions untouched (existing `*.test.ts` must still pass).
- [ ] **Step 3:** Port `seed-acme-invoices.ts` (`api()` → shared client).
- [ ] **Step 4:** Re-run `pnpm test seed-sequences` **and** the existing `seed-help-articles.test.ts`/`seed-kb.test.ts` → all green, goldens byte-identical.
- [ ] **Step 5: Commit** — `git commit -m "refactor(seed): port TS seed-*.ts to shared client (goldens byte-identical)"`

**Caveat (from spec):** `portal/.build` is regenerated by `prepare-context.sh`; these commits are a prototype here. Upstreaming to `analog-elk-front-end` is a separate follow-up (Mike's call) — file it as an `os_tasks` row, do not attempt it under `chore/muster-seed-shared-client`.

---

## Phase 3 — Verification & close

### Task 12: Full green + CLOSE TASK

- [ ] **Step 1:** `pytest tests/characterization -q` (Python) — all goldens green; `git status` shows no golden churn.
- [ ] **Step 2:** `cd portal/.build && pnpm test` — TS suite green (incl. the two pre-existing seed tests).
- [ ] **Step 3:** Confirm DRY win: grep shows the duplicated `load_env`/`req`/`request`/`upsert` bodies are gone from scope (only `_client` + intentional local wrappers remain).
- [ ] **Step 4:** Push branch, open PR targeting `main` (verify base per DevProd §8); PR body summarizes the golden-locked approach and links the spec + this plan. No UI changes → check the "no UI" box (DevProd §5).
- [ ] **Step 5: CLOSE TASK ceremony** (DevProd §10): `os_tasks` row(s) (this task completed + follow-ups: TS upstreaming, any preserved-bug fixes surfaced by goldens); KB `kb_pages` lesson (characterization-harness pattern for urllib scripts); memory file + `MEMORY.md` pointer; `releases` entry; token-ledger sync (`aggregate.ts` + `aggregate-commits.ts`); report "logged to:" trail.

---

## Self-Review

**Spec coverage:** scope in/out ✓ (Global Constraints + SCOPE.txt, Task 5/9); harness+responder+determinism+fake-token ✓ (Tasks 1–4); byte-identical definition ✓ (Global Constraints, recorder Task 1); shared configurable client preserving divergent behavior ✓ (Task 6 knobs, worked ports 7/8 prove both `req` and `request` semantics incl. opposite `token=None` handling); goldens-first workflow ✓ (Task 5 gate before Phase 1); port-one-at-a-time byte-identical ✓ (Tasks 7–9); TS half in portal/.build with regenerate + throwaway caveat ✓ (Tasks 10–11); isolation/worktree ✓ (done); CLOSE TASK ✓ (Task 12).

**Placeholder scan:** foundation tasks carry real code; the ~47-script port phase specifies a complete, concrete port procedure + factory/knob mapping + golden gate rather than 47 near-identical code blocks (the transformation is fully specified by the worked F1/D1 templates). No "TBD"/"handle edge cases"/"write tests for the above".

**Type/name consistency:** `make_req`/`make_request`/`make_upsert`/`load_env`/`RequestRecord`/`Responder`/`freeze()`/`install_transport` used consistently across tasks; golden JSONL format defined once (Task 1) and reused by Python and TS harnesses.
