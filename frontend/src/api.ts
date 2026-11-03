// API client: access token in memory, refresh token in an httpOnly cookie (design doc 8.2).

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function setAccessToken(t: string | null) {
  accessToken = t;
}

/** Raw fetch with auth (for file downloads). Refreshes the token once on 401. */
export async function authFetch(path: string): Promise<Response> {
  const go = () =>
    fetch(`/api/v1${path}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: "include",
    });
  const r = await go();
  return r.status === 401 && (await refresh()) ? go() : r;
}

async function refresh(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    .then(async (r) => {
      if (!r.ok) return false;
      accessToken = (await r.json()).access_token;
      return true;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const r = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  if (r.status === 401 && retry && (await refresh())) return api<T>(path, init, false);
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const body = await r.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function login(email: string, password: string) {
  const r = await api<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  accessToken = r.access_token;
}

export async function tryRestoreSession(): Promise<boolean> {
  return refresh();
}

export async function logout() {
  await api("/auth/logout", { method: "POST" }).catch(() => undefined);
  accessToken = null;
}
