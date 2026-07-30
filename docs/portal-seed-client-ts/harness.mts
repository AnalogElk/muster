/**
 * TS fetch-stub harness — mirrors the Python characterization harness.
 * Records the exact request sequence a seed script makes under a deterministic
 * synthetic Directus responder, with frozen Date/Math.random/crypto.randomUUID.
 * Golden = JSONL of {seq, method, url, headers(canonical, bearer-masked),
 * body_b64, body_sha256}. Byte-identical comparison is TS-vs-TS.
 */
import { createHash } from "node:crypto";

const MASK = "Bearer <token>";

type Rec = {
  body_b64: string;
  body_sha256: string;
  headers: Array<[string, string]>;
  method: string;
  seq: number;
  url: string;
};

export const records: Rec[] = [];

function canonicalHeaders(h: unknown): Array<[string, string]> {
  const out: Record<string, string> = {};
  const entries: Array<[string, string]> =
    h instanceof Headers
      ? [...h.entries()]
      : Array.isArray(h)
        ? (h as Array<[string, string]>)
        : Object.entries((h ?? {}) as Record<string, string>);
  for (const [k, v] of entries) {
    const lk = String(k).toLowerCase();
    out[lk] = lk === "authorization" && String(v).startsWith("Bearer ") ? MASK : String(v);
  }
  return Object.keys(out)
    .sort()
    .map((k) => [k, out[k]] as [string, string]);
}

function toBytes(body: unknown): Buffer {
  if (body == null) return Buffer.alloc(0);
  if (typeof body === "string") return Buffer.from(body);
  if (Buffer.isBuffer(body)) return body;
  return Buffer.from(String(body));
}

function record(seq: number, method: string, url: string, headers: unknown, body: unknown): void {
  const bytes = toBytes(body);
  records.push({
    body_b64: bytes.toString("base64"),
    body_sha256: createHash("sha256").update(bytes).digest("hex"),
    headers: canonicalHeaders(headers),
    method: method.toUpperCase(),
    seq,
    url,
  });
}

// ---- deterministic synthetic Directus responder (same policy as Python) ----
let postCounter = 0;
const COLL = ["items", "fields", "relations", "permissions"];
const ROOT = ["users", "roles", "policies", "files", "folders", "presets"];

function respond(method: string, pathWithQuery: string, body: string | undefined): [number, unknown] {
  const u = new URL("http://x" + pathWithQuery);
  const p = u.pathname;
  const hasQuery = u.search !== "";
  method = method.toUpperCase();

  if (method === "POST" && (p === "/auth/login" || p === "/auth/refresh"))
    return [200, { data: { access_token: "FAKE_DEMO_TOKEN", refresh_token: "FAKE_REFRESH", expires: 900000 } }];
  if (method === "POST" && p.replace(/\/$/, "").endsWith("/graphql")) return [200, { data: {} }];

  if (method === "GET") {
    const segs = p.split("/").filter(Boolean);
    const existence =
      !hasQuery &&
      ((segs.length >= 3 && COLL.includes(segs[0])) || (segs.length === 2 && ROOT.includes(segs[0])));
    return existence ? [404, { errors: [{ message: "not found" }] }] : [200, { data: [] }];
  }
  if (method === "POST") {
    postCounter++;
    const sid = "SEED-" + String(postCounter).padStart(4, "0");
    let echo: unknown = null;
    try {
      echo = body ? JSON.parse(body) : null;
    } catch {
      echo = null;
    }
    let data: unknown;
    if (echo && typeof echo === "object" && !Array.isArray(echo)) {
      data = { ...(echo as object) };
      if ((data as Record<string, unknown>).id === undefined) (data as Record<string, unknown>).id = sid;
    } else if (Array.isArray(echo)) data = echo;
    else data = { id: sid };
    return [200, { data }];
  }
  if (method === "PATCH") {
    let echo: unknown = null;
    try {
      echo = body ? JSON.parse(body) : null;
    } catch {
      echo = null;
    }
    const data =
      echo && typeof echo === "object" && !Array.isArray(echo) ? { ...(echo as object) } : {};
    if ((data as Record<string, unknown>).id === undefined) (data as Record<string, unknown>).id = "SEED-PATCHED";
    return [200, { data }];
  }
  if (method === "DELETE") return [204, null];
  return [200, { data: null }];
}

export function installFetch(): void {
  let seq = 0;
  globalThis.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : (input as Request).url;
    const method = (init.method || "GET").toUpperCase();
    const body = init.body;
    record(seq++, method, url, init.headers, body);
    const u = new URL(url);
    const [status, obj] = respond(method, u.pathname + (u.search || ""), typeof body === "string" ? body : undefined);
    const payload = obj === null ? "" : JSON.stringify(obj);
    return new Response(payload, { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
}

export function freezeTime(): void {
  const FIXED = new Date("2026-01-01T00:00:00Z").getTime();
  const RealDate = Date;
  class FrozenDate extends RealDate {
    constructor(...args: unknown[]) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (args.length === 0) super(FIXED);
      else super(...(args as [any]));
    }
    static now(): number {
      return FIXED;
    }
  }
  globalThis.Date = FrozenDate as DateConstructor;
  globalThis.Math.random = () => 0;
  try {
    (globalThis.crypto as unknown as { randomUUID: () => string }).randomUUID = () =>
      "00000000-0000-4000-8000-000000000000";
  } catch {
    /* ignore */
  }
}

export function dumpJsonl(): string {
  // keys are already in sorted order in Rec; stable stringify.
  return records.map((r) => JSON.stringify(r)).join("\n") + (records.length ? "\n" : "");
}
