import { Link, useParams } from 'react-router-dom';
import { useMemo } from 'react';
import {
  buildCorrelationPoints,
  buildEngagementCurve,
} from '../../analytics/selectors/engagementCurves';
import { CorrelationScatter } from '../../components/charts/CorrelationScatter';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { EmptyState } from '../../components/layout/EmptyState';
import { PageHeader } from '../../components/layout/PageHeader';
import { usePostSnapshots } from '../../hooks/queries/usePostSnapshots';
import { useTrackedPost } from '../../hooks/queries/useTrackedPost';
import { useTrackedPosts } from '../../hooks/queries/useTrackedPosts';
import { formatShortDate, isStaleFetch } from '../../lib/format';
import type { PostMetricSnapshot } from '../../types';
import { EngagementCurve } from './EngagementCurve';
import {
  PostCreationCard,
  PostMetricsGrid,
  ReferencePickCompare,
} from './PostDetailComponents';

export function PostDetailPage() {
  const { accountId, tweetId } = useParams();
  const postQuery = useTrackedPost(accountId, tweetId);
  const snapshotsQuery = usePostSnapshots(accountId, tweetId);
  const accountPostsQuery = useTrackedPosts(accountId);

  const curve = useMemo(
    () => buildEngagementCurve(snapshotsQuery.data?.snapshots ?? []),
    [snapshotsQuery.data]
  );

  const correlationPoints = useMemo(
    () => buildCorrelationPoints(accountPostsQuery.data?.posts ?? []),
    [accountPostsQuery.data]
  );

  const snapshotColumns: DataTableColumn<PostMetricSnapshot>[] = [
    {
      id: 'captured',
      header: 'Captured',
      accessor: (s) => formatShortDate(s.captured_at),
      sortValue: (s) => s.captured_at,
    },
    {
      id: 'impressions',
      header: 'Impressions',
      accessor: (s) => s.impression_count?.toLocaleString() ?? '—',
      sortValue: (s) => s.impression_count ?? -1,
      align: 'right',
    },
    {
      id: 'er',
      header: 'ER',
      accessor: (s) =>
        s.engagement_rate != null ? `${(s.engagement_rate * 100).toFixed(2)}%` : '—',
      sortValue: (s) => s.engagement_rate ?? -1,
      align: 'right',
    },
    {
      id: 'velocity',
      header: 'Velocity',
      accessor: (s) => s.engagement_velocity?.toFixed(4) ?? '—',
      sortValue: (s) => s.engagement_velocity ?? -1,
      align: 'right',
    },
  ];

  if (postQuery.isLoading) {
    return <p className="App-loading">Loading post…</p>;
  }

  if (!postQuery.data) {
    return <EmptyState message="Post not found." />;
  }

  const post = postQuery.data;
  const stale = isStaleFetch(post.last_fetched_at);

  return (
    <div className="page-content">
      <PageHeader
        title={`Post ${tweetId}`}
        subtitle={formatShortDate(post.posted_at)}
        actions={
          <Link to={`/accounts/${accountId}/posts`} className="btn btn--ghost">
            ← Back to posts
          </Link>
        }
      />

      {stale ? (
        <div className="stale-banner" role="status">
          Metrics may be stale (last fetched &gt; 2h ago).
        </div>
      ) : null}

      <PostMetricsGrid post={post} />
      <EngagementCurve points={curve} />
      <PostCreationCard post={post} />
      <ReferencePickCompare post={post} />
      <CorrelationScatter points={correlationPoints} />

      <section className="hq-panel" aria-label="Metric snapshots">
        <h3 className="hq-panel__title">Snapshots</h3>
        <DataTable
          columns={snapshotColumns}
          rows={snapshotsQuery.data?.snapshots ?? []}
          rowKey={(s) => s.captured_at}
          emptyMessage="No snapshots yet."
          ariaLabel="Post metric snapshots"
        />
      </section>
    </div>
  );
}
