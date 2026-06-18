import { apiBaseUrl, apiPrefix, parseHttpError } from './client';

// The login token is stored on the user's device (localStorage) and sent on every
// request as `Authorization: Bearer <token>`. It is a signed, self-expiring token —
// the backend keeps no session state. Cleared on logout or any 401.
const TOKEN_KEY = 'smd.session.token';

const listeners = new Set<() => void>();

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function setToken(token: string | null): void {
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    /* storage unavailable (private mode) — session just won't persist */
  }
  listeners.forEach((fn) => fn());
}

export function isAuthed(): boolean {
  return Boolean(getToken());
}

/** Subscribe to auth changes (login / logout / 401). Returns an unsubscribe fn. */
export function onAuthChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function logout(): void {
  setToken(null);
}

/** Called by the API layer when the backend rejects our token. */
export function handleUnauthorized(): void {
  if (getToken()) {
    setToken(null);
  }
}

export async function login(password: string): Promise<void> {
  const prefix = apiPrefix(apiBaseUrl());
  const res = await fetch(`${prefix}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  const data = (await res.json()) as { token: string };
  setToken(data.token);
}
