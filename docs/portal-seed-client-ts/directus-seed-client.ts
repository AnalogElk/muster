/**
 * Shared Directus client for the portal seed scripts. Centralizes env
 * resolution and the fetch-with-bearer transport that seed-acme-invoices,
 * seed-help-articles, and seed-kb each re-implemented. Behavior of each
 * script's original helper is preserved exactly (verified by golden
 * request-sequence tests under scripts/seed-golden/).
 */

export interface DirectusClient {
  url: string;
  token: string;
}

/** seed-acme-invoices convention: DIRECTUS_URL || NEXT_PUBLIC_DIRECTUS_URL || default; ELK_CMS_TOKEN || DIRECTUS_TOKEN. */
export function resolveDirectusEnv(): { url: string; token: string | undefined } {
  const url =
    process.env.DIRECTUS_URL ||
    process.env.NEXT_PUBLIC_DIRECTUS_URL ||
    "https://cms.analogelk.com";
  const token = process.env.ELK_CMS_TOKEN || process.env.DIRECTUS_TOKEN;
  return { url, token };
}

/**
 * seed-acme-invoices `api()`: throws on !ok, unwraps `.data`.
 */
export function makeApi(url: string, token: string) {
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  return async function api<T = Record<string, unknown>>(
    method: "GET" | "POST" | "PATCH",
    path: string,
    body?: unknown,
  ): Promise<T> {
    const res = await fetch(`${url}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`${method} ${path} → ${res.status}: ${txt}`);
    }
    const json = (await res.json()) as { data?: T };
    return (json.data ?? (json as unknown)) as T;
  };
}

/**
 * seed-help-articles / seed-kb `directusFetch()`: throws on !ok, returns RAW json.
 */
export async function directusFetch<T>(
  client: DirectusClient,
  method: string,
  pathName: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${client.url}${pathName}`, {
    method,
    headers: {
      Authorization: `Bearer ${client.token}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${method} ${pathName} failed (${res.status}): ${detail}`);
  }
  return (await res.json()) as T;
}
