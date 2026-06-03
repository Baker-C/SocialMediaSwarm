import type { AccountSummary, DashboardPayload } from '../types';

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
