import type { AccountSummary, DashboardPayload } from '../../types';

export type FleetKpis = {
  activeAccounts: number | null;
  avgEngagement: number | null;
  avgReplyRate: number | null;
  topNiche: string | null;
  totalTrackedPosts: number | null;
  accountsWithoutPosts: number | null;
  dataCompletenessPct: number | null;
  computedAt: string | null;
};

export type LeaderboardRow = {
  accountId: string;
  niche: string;
  avgEr: number | null;
  followerGrowth: number | null;
  lastPostAge: string | null;
  trackedPosts: number | null;
  hasOAuth: boolean;
};

export type OpsAlert = {
  kind: 'no_oauth' | 'zero_posts' | 'stale_fetch';
  accountId: string;
  message: string;
};

export function computeFleetKpis(
  dashboard: DashboardPayload | undefined,
  accounts: AccountSummary[]
): FleetKpis {
  const withCredentials = accounts.filter((a) => a.has_credentials !== false).length;
  const completeness =
    accounts.length > 0 ? Math.round((withCredentials / accounts.length) * 100) : null;

  return {
    activeAccounts: dashboard?.active_accounts ?? null,
    avgEngagement: dashboard?.avg_engagement ?? null,
    avgReplyRate: dashboard?.avg_reply_rate ?? null,
    topNiche: dashboard?.top_niche ?? null,
    totalTrackedPosts: dashboard?.total_tracked_posts ?? null,
    accountsWithoutPosts: dashboard?.accounts_without_posts ?? null,
    dataCompletenessPct: completeness,
    computedAt: dashboard?.computed_at ?? null,
  };
}

export function buildLeaderboard(
  accounts: AccountSummary[],
  metricsByAccount: Record<string, { avg_engagement_rate?: number | null; post_count?: number }>
): LeaderboardRow[] {
  return accounts
    .map((a) => ({
      accountId: a.account_id,
      niche: a.niche,
      avgEr: metricsByAccount[a.account_id]?.avg_engagement_rate ?? null,
      followerGrowth: a.follower_growth_vs_registered ?? null,
      lastPostAge: a.recent_post?.posted_at ?? null,
      trackedPosts: metricsByAccount[a.account_id]?.post_count ?? a.posts_total ?? null,
      hasOAuth: a.has_credentials !== false,
    }))
    .sort((x, y) => (y.avgEr ?? -1) - (x.avgEr ?? -1));
}

export function buildOpsAlerts(
  accounts: AccountSummary[],
  staleAccountIds: Set<string>
): OpsAlert[] {
  const alerts: OpsAlert[] = [];
  for (const a of accounts) {
    if (a.has_credentials === false) {
      alerts.push({
        kind: 'no_oauth',
        accountId: a.account_id,
        message: 'X OAuth not connected',
      });
    }
    if ((a.posts_total ?? 0) === 0) {
      alerts.push({
        kind: 'zero_posts',
        accountId: a.account_id,
        message: 'No tracked posts',
      });
    }
    if (staleAccountIds.has(a.account_id)) {
      alerts.push({
        kind: 'stale_fetch',
        accountId: a.account_id,
        message: 'Stale metrics fetch (>2h)',
      });
    }
  }
  return alerts;
}
