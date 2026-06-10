export function apiBaseUrl(): string {
  const fromEnv = process.env.REACT_APP_API_URL?.trim();
  if (fromEnv) {
    return fromEnv.replace(/\/$/, '');
  }
  if (process.env.NODE_ENV === 'development') {
    return '';
  }
  return '';
}

export function apiPrefix(apiBase: string): string {
  return apiBase ? `${apiBase}/api` : '/api';
}

export async function parseHttpError(res: Response): Promise<string> {
  const text = await res.text();
  let detail: unknown;
  try {
    detail = JSON.parse(text).detail;
  } catch {
    return `${res.status} ${res.statusText}${text ? `: ${text}` : ''}`;
  }
  if (typeof detail === 'string') {
    return `${res.status}: ${detail}`;
  }
  if (Array.isArray(detail)) {
    return `${res.status}: ${detail.map((d) => JSON.stringify(d)).join('; ')}`;
  }
  if (detail && typeof detail === 'object') {
    return `${res.status}: ${JSON.stringify(detail)}`;
  }
  return `${res.status} ${res.statusText}`;
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const prefix = apiPrefix(apiBaseUrl());
  const res = await fetch(`${prefix}${path}`, options);
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  return (await res.json()) as T;
}
