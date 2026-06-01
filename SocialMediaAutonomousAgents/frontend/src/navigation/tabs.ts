import type { AccountSummary } from '../types';

export type TabId = { kind: 'overview' } | { kind: 'account'; accountId: string };

export type NavItem = {
  id: TabId;
  label: string;
  subtitle?: string;
};

export function tabKey(id: TabId): string {
  return id.kind === 'overview' ? 'overview' : `account:${id.accountId}`;
}

export function tabEquals(a: TabId, b: TabId): boolean {
  if (a.kind === 'overview' && b.kind === 'overview') {
    return true;
  }
  if (a.kind === 'account' && b.kind === 'account') {
    return a.accountId === b.accountId;
  }
  return false;
}

/** Single place to define sidebar tabs. Add static entries here; accounts are appended. */
export function buildNavItems(accounts: AccountSummary[]): NavItem[] {
  const overview: NavItem = { id: { kind: 'overview' }, label: 'Overview' };

  const accountItems = [...accounts]
    .sort((a, b) => a.account_id.localeCompare(b.account_id))
    .map(
      (a): NavItem => ({
        id: { kind: 'account', accountId: a.account_id },
        label: a.account_id,
        subtitle: a.niche?.trim() || undefined,
      })
    );

  return [overview, ...accountItems];
}
