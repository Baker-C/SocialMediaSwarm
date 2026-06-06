import type {
  AccountSummary,
  DashboardPayload,
  OAuthAuthorizeResponse,
  OAuthStatus,
} from '../types';
import type { ForcePostStreamEvent } from './forcePostSteps';

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

export function readActiveAccountCount(dashboard: unknown): number | null {
  if (!dashboard || typeof dashboard !== 'object') {
    return null;
  }
  const d = dashboard as DashboardPayload;
  if (typeof d.active_accounts !== 'number' || Number.isNaN(d.active_accounts)) {
    return null;
  }
  return d.active_accounts;
}

export function parseAccounts(raw: unknown): AccountSummary[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((row): row is AccountSummary => {
    if (!row || typeof row !== 'object') {
      return false;
    }
    const r = row as Record<string, unknown>;
    return typeof r.account_id === 'string';
  }) as AccountSummary[];
}

export async function fetchOAuthAuthorizeUrl(
  apiBase: string,
  accountId: string
): Promise<OAuthAuthorizeResponse> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(
    `${prefix}/oauth/x/authorize?account_id=${encodeURIComponent(accountId)}`
  );
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  return (await res.json()) as OAuthAuthorizeResponse;
}

export async function fetchOAuthStatus(apiBase: string, accountId: string): Promise<OAuthStatus> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/oauth/x/status/${encodeURIComponent(accountId)}`);
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  return (await res.json()) as OAuthStatus;
}

export async function disconnectOAuth(apiBase: string, accountId: string): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/oauth/x/disconnect/${encodeURIComponent(accountId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
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

function parseSseData(line: string): ForcePostStreamEvent | null {
  const payload = line.startsWith('data: ') ? line.slice(6) : line;
  if (!payload.trim()) {
    return null;
  }
  try {
    return JSON.parse(payload) as ForcePostStreamEvent;
  } catch {
    return null;
  }
}

export async function streamForcePost(
  apiBase: string,
  accountId: string,
  onEvent: (event: ForcePostStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/accounts/${encodeURIComponent(accountId)}/force-post`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    signal,
  });
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  if (!res.body) {
    throw new Error('No response body from force post stream');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const chunk of parts) {
      for (const line of chunk.split('\n')) {
        const event = parseSseData(line);
        if (event) {
          onEvent(event);
        }
      }
    }
  }

  if (buffer.trim()) {
    for (const line of buffer.split('\n')) {
      const event = parseSseData(line);
      if (event) {
        onEvent(event);
      }
    }
  }
}
