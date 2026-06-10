import type { AccountEditPayload, AccountSummary, DashboardPayload } from '../../types';
import { apiFetch } from '../client';

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

export async function fetchAccounts(): Promise<AccountSummary[]> {
  const raw = await apiFetch<unknown>('/accounts');
  return parseAccounts(raw);
}

export async function fetchAccountEditPayload(accountId: string): Promise<AccountEditPayload> {
  return apiFetch<AccountEditPayload>(`/accounts/${encodeURIComponent(accountId)}`);
}

export async function updateAccount(
  accountId: string,
  payload: Partial<AccountEditPayload>
): Promise<AccountEditPayload> {
  return apiFetch<AccountEditPayload>(`/accounts/${encodeURIComponent(accountId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
