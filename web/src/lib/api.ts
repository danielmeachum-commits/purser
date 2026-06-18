// Single fetch wrapper. Cookies carry the admin session.
// For service-token use (read-only dashboard), pass `token` and it goes
// in the URL as ?token=... so the WebSocket can read it too.

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  token?: string;
  signal?: AbortSignal;
}

function buildQuery(query?: RequestOptions["query"], token?: string): string {
  const params = new URLSearchParams();
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      params.append(k, String(v));
    }
  }
  if (token) params.set("token", token);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}${buildQuery(opts.query, opts.token)}`;
  const res = await fetch(url, {
    method: opts.method ?? "GET",
    credentials: "include",
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (res.status === 204) return undefined as T;
  let payload: unknown = null;
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    payload = await res.json();
  } else {
    payload = await res.text();
  }
  if (!res.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, payload, detail);
  }
  return payload as T;
}

export function wsUrl(token?: string): string {
  const base = import.meta.env.VITE_WS_BASE ?? "";
  const scheme =
    typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws";
  let path = "/ws";
  if (token) path += `?token=${encodeURIComponent(token)}`;
  if (base) return `${base}${path}`;
  return `${scheme}://${window.location.host}${path}`;
}
