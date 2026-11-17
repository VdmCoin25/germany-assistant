import { tg } from "./tg";

export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}

/** Calls our FastAPI with the signed Telegram initData; the server verifies the signature. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);   // weak mobile networks: fail visibly instead of hanging
  try {
    const r = await fetch(path, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tg?.initData ?? "", ...init.headers },
    });
    if (!r.ok) {
      let code = String(r.status);
      try { code = (await r.json()).detail ?? code; } catch { /* not JSON */ }
      throw new ApiError(r.status, code);
    }
    try { return (await r.json()) as T; } catch { throw new ApiError(r.status, "bad_response"); }
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, ctrl.signal.aborted ? "timeout" : "network");
  } finally {
    clearTimeout(timer);
  }
}
