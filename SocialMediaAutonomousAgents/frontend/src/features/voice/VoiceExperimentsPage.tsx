import { Link, useParams } from 'react-router-dom';
import { useMemo } from 'react';
import { compareVoiceVersions, revisionTimeline } from '../../analytics/selectors/voiceComparison';
import { normalizeTrackedPosts } from '../../analytics/normalize/trackedPost';
import { buildCorrelationPoints } from '../../analytics/selectors/engagementCurves';
import { CorrelationScatter } from '../../components/charts/CorrelationScatter';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import { useAccount } from '../../hooks/queries/useAccounts';
import { useTrackedPosts } from '../../hooks/queries/useTrackedPosts';
import { useVoiceRevisions } from '../../hooks/queries/useVoiceRevisions';
import { formatPercent, formatShortDate } from '../../lib/format';
import type { VoiceVersionStats } from '../../analytics/selectors/voiceComparison';

export function VoiceExperimentsPage() {
  const { accountId } = useParams();
  const accountQuery = useAccount(accountId);
  const revisionsQuery = useVoiceRevisions(accountId);
  const postsQuery = useTrackedPosts(accountId);

  const posts = useMemo(
    () => normalizeTrackedPosts(postsQuery.data?.posts ?? []),
    [postsQuery.data]
  );

  const comparison = useMemo(
    () => compareVoiceVersions(posts, revisionsQuery.data?.revisions ?? []),
    [posts, revisionsQuery.data]
  );

  const timeline = revisionTimeline(revisionsQuery.data?.revisions ?? []);
  const correlationPoints = useMemo(() => buildCorrelationPoints(posts), [posts]);

  const comparisonColumns: DataTableColumn<VoiceVersionStats>[] = [
    { id: 'label', header: 'Voice', accessor: (r) => r.label, sortValue: (r) => r.label },
    {
      id: 'seq',
      header: 'Seq',
      accessor: (r) => r.seq ?? '—',
      sortValue: (r) => r.seq ?? -1,
      align: 'right',
    },
    {
      id: 'posts',
      header: 'Posts',
      accessor: (r) => r.postCount,
      sortValue: (r) => r.postCount,
      align: 'right',
    },
    {
      id: 'er',
      header: 'Avg ER',
      accessor: (r) => formatPercent(r.avgEr, 2),
      sortValue: (r) => r.avgEr ?? -1,
      align: 'right',
    },
    {
      id: 'imp',
      header: 'Avg impressions',
      accessor: (r) =>
        r.avgImpressions != null ? Math.round(r.avgImpressions).toLocaleString() : '—',
      sortValue: (r) => r.avgImpressions ?? -1,
      align: 'right',
    },
  ];

  const currentVoice = accountQuery.data?.voice_version_label ?? 'default';

  return (
    <div className="page-content">
      <PageHeader
        title="Voice & Experiments"
        subtitle="Revision history and performance by voice version"
        actions={
          <Link to={`/accounts/${accountId}/settings`} className="voice-badge">
            Current: {currentVoice}
          </Link>
        }
      />

      <section className="hq-panel" aria-label="Revision timeline">
        <h3 className="hq-panel__title">Revision timeline</h3>
        {revisionsQuery.isLoading ? (
          <p className="App-loading">Loading revisions…</p>
        ) : timeline.length === 0 ? (
          <p className="page-hint">No voice revisions recorded.</p>
        ) : (
          <ol className="revision-timeline">
            {timeline.map((r) => (
              <li key={r.seq} className="revision-timeline__item">
                <span className="revision-timeline__seq">#{r.seq}</span>
                <span className="revision-timeline__label">{r.label}</span>
                <span className="revision-timeline__date">{formatShortDate(r.changed_at)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="hq-panel" aria-label="Voice comparison">
        <h3 className="hq-panel__title">Performance by voice version</h3>
        <DataTable
          columns={comparisonColumns}
          rows={comparison}
          rowKey={(r) => String(r.seq ?? r.label)}
          emptyMessage="No voice comparison data."
          ariaLabel="Voice version comparison"
        />
      </section>

      <CorrelationScatter points={correlationPoints} />
    </div>
  );
}
