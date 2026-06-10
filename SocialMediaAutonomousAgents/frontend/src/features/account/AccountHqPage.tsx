import { useParams } from 'react-router-dom';
import { normalizeAccountSnapshots } from '../../analytics/normalize/accountSnapshot';
import { POST_INTERVAL_MINUTES } from '../../analytics/constants';
import { TimeSeriesChart } from '../../components/charts/TimeSeriesChart';
import { EmptyState } from '../../components/layout/EmptyState';
import { ErrorBanner } from '../../components/layout/ErrorBanner';
import { PageHeader } from '../../components/layout/PageHeader';
import { useAccount } from '../../hooks/queries/useAccounts';
import { useAccountMetrics } from '../../hooks/queries/useAccountMetrics';
import { useAccountSnapshots } from '../../hooks/queries/useAccountSnapshots';
import { useOAuthStatus } from '../../hooks/queries/useOAuthStatus';
import { OAuthStatusCard } from '../operations/OAuthStatusCard';
import {
  AccountHeader,
  AccountKpiStrip,
  AccountQuickLinks,
  CadenceGauge,
} from './AccountHqComponents';

export function AccountHqPage() {
  const { accountId } = useParams();
  const accountQuery = useAccount(accountId);
  const metricsQuery = useAccountMetrics(accountId);
  const snapshotsQuery = useAccountSnapshots(accountId);
  const oauthQuery = useOAuthStatus(accountId);

  if (accountQuery.isLoading) {
    return <p className="App-loading">Loading account HQ…</p>;
  }

  if (!accountQuery.data) {
    return <EmptyState message="Account not found." />;
  }

  const account = accountQuery.data;
  const metrics = metricsQuery.data;
  const chartData = normalizeAccountSnapshots(snapshotsQuery.data?.snapshots ?? []);

  return (
    <div className="page-content">
      <PageHeader title="Account HQ" subtitle={`Operational overview for ${account.account_id}`} />
      {metricsQuery.isError ? (
        <ErrorBanner message="Account metrics unavailable — showing profile data only." />
      ) : null}

      <AccountHeader account={account} />
      <AccountKpiStrip
        trackedPosts={account.posts_total}
        avgEr={metrics?.avg_engagement_rate ?? null}
        avgReply={metrics?.avg_reply_rate ?? null}
        avgLike={metrics?.avg_like_rate ?? null}
        followerDeltaGap={metrics?.follower_delta_engagement_gap ?? null}
      />

      <div className="hq-grid">
        <section className="hq-panel" aria-label="Follower trend">
          <h3 className="hq-panel__title">Follower & views trend</h3>
          <TimeSeriesChart
            data={chartData}
            xKey="label"
            series={[
              { dataKey: 'followers', name: 'Followers', color: '#2563eb' },
              { dataKey: 'totalViews', name: 'Total views', color: '#059669' },
            ]}
            ariaLabel="Follower and total views over time"
          />
        </section>

        <section className="hq-panel" aria-label="Cadence and OAuth">
          <CadenceGauge
            lastPostAt={account.recent_post?.posted_at}
            intervalMinutes={POST_INTERVAL_MINUTES}
          />
          <OAuthStatusCard
            accountId={account.account_id}
            status={oauthQuery.data}
            loading={oauthQuery.isLoading}
            hasCredentials={account.has_credentials !== false}
          />
        </section>
      </div>

      <AccountQuickLinks accountId={account.account_id} />
    </div>
  );
}
