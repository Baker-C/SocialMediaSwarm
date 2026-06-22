import type { AccountSummary } from '../types';

export type AccountSubNavItem = {
  segment: string;
  label: string;
  end?: boolean;
};

export type TopNavItem = {
  path: string;
  label: string;
};

// Top-level (non-account) nav entries rendered by the Sidebar.
export const TOP_NAV: TopNavItem[] = [{ path: '/provision', label: 'New Account' }];

export const ACCOUNT_SUB_NAV: AccountSubNavItem[] = [
  { segment: '', label: 'HQ', end: true },
  { segment: 'posts', label: 'Posts' },
  { segment: 'references', label: 'References' },
  { segment: 'pipeline', label: 'Pipeline' },
  { segment: 'builder', label: 'Builder' },
  { segment: 'voice', label: 'Voice' },
  { segment: 'settings', label: 'Settings' },
];

export function buildAccountNavItems(accounts: AccountSummary[]) {
  return [...accounts]
    .sort((a, b) => a.account_id.localeCompare(b.account_id))
    .map((account) => ({
      accountId: account.account_id,
      label: account.account_id,
      subtitle: account.category?.trim() || undefined,
      retired: account.retired === true,
    }));
}

export function accountSubNavPath(accountId: string, segment: string): string {
  if (!segment) {
    return `/accounts/${accountId}`;
  }
  return `/accounts/${accountId}/${segment}`;
}
