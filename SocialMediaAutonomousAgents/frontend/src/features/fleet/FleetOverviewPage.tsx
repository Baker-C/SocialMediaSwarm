import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  buildLeaderboard,
  buildOpsAlerts,
  computeFleetKpis,
} from '../../analytics/selectors/fleetKpis';
import { isStaleFetch } from '../../lib/format';
import { apiBaseUrl } from '../../api/client';
import { ForcePostSection } from '../operations/ForcePostSection';
import { PageHeader } from '../../components/layout/PageHeader';
import { StatTile } from '../../components/layout/StatTile';
import { useAccounts } from '../../hooks/queries/useAccounts';
import { useDashboard } from '../../hooks/queries/useDashboard';
import { useAppContext } from '../../app/AppContext';
import { AccountLeaderboard, OpsAlertStrip } from './FleetComponents';

export function FleetOverviewPage() {
  const dashboardQuery = useDashboard();
  const accountsQuery = useAccounts();
  const queryClient = useQueryClient();
  const { apiBase } = useAppContext();

  const accounts = accountsQuery.data ?? [];
  const kpis = computeFleetKpis(dashboardQuery.data, accounts);

  const staleAccountIds = useMemo(() => {
    const ids = new Set<string>();
    for (const a of accounts) {
      if (a.recent_post?.posted_at && isStaleFetch(a.recent_post.posted_at)) {
        ids.add(a.account_id);
      }
    }
    return ids;
  }, [accounts]);

  const leaderboard = useMemo(
    () => buildLeaderboard(accounts, {}),
    [accounts]
  );

  const alerts = useMemo(
    () => buildOpsAlerts(accounts, staleAccountIds),
    [accounts, staleAccountIds]
  );

  const refresh = () => {
    void queryClient.invalidateQueries();
  };

  return (
    <div className="page-content">
      <PageHeader
        title="Fleet Overview"
        subtitle="Cross-account KPIs and operations"
        actions={
          <button type="button" className="btn btn--ghost" onClick={refresh}>
            Refresh
          </button>
        }
      />

      <section className="kpi-grid" aria-label="Fleet KPIs">
        <StatTile kicker="Fleet" title="Active accounts" value={kpis.activeAccounts ?? '—'} />
        <StatTile
          kicker="Engagement"
          title="Avg engagement"
          value={kpis.avgEngagement != null ? `${(kpis.avgEngagement * 100).toFixed(2)}%` : '—'}
        />
        <StatTile kicker="Niche" title="Top niche" value={kpis.topNiche ?? '—'} />
        <StatTile
          kicker="Posts"
          title="Total tracked posts"
          value={kpis.totalTrackedPosts ?? '—'}
        />
        <StatTile
          kicker="Quality"
          title="Data completeness"
          value={kpis.dataCompletenessPct != null ? `${kpis.dataCompletenessPct}%` : '—'}
          caption="Accounts with OAuth connected"
        />
        <StatTile
          kicker="Gaps"
          title="Accounts without posts"
          value={kpis.accountsWithoutPosts ?? '—'}
        />
      </section>

      <OpsAlertStrip alerts={alerts} />
      <AccountLeaderboard rows={leaderboard} />

      <section className="fleet-operations" aria-label="Operations">
        <ForcePostSection
          apiBase={apiBase || apiBaseUrl()}
          accounts={accounts}
          onComplete={() => void queryClient.invalidateQueries()}
        />
      </section>
    </div>
  );
}
