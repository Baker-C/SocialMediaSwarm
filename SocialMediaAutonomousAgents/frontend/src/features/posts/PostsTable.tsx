import { useNavigate } from 'react-router-dom';
import type { EnrichedTrackedPost } from '../../types/domain/trackedPost';
import { FOLLOWER_DELTA_SCOPE } from '../../types/domain/trackedPost';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { DataQualityBadge } from '../../components/data/DataQualityBadge';
import { formatPercent, formatShortDate } from '../../lib/format';

type PostRow = EnrichedTrackedPost & { refScoreAtPick?: number | null };

type PostsTableProps = {
  accountId: string;
  rows: PostRow[];
};

export function PostsTable({ accountId, rows }: PostsTableProps) {
  const navigate = useNavigate();

  const columns: DataTableColumn<PostRow>[] = [
    {
      id: 'posted',
      header: 'Posted',
      accessor: (r) => formatShortDate(r.posted_at),
      sortValue: (r) => r.posted_at ?? '',
    },
    {
      id: 'text',
      header: 'Text',
      accessor: (r) => <span className="post-snippet">{r.textSnippet}</span>,
    },
    {
      id: 'impressions',
      header: 'Impressions',
      accessor: (r) => r.impression_count?.toLocaleString() ?? '—',
      sortValue: (r) => r.impression_count ?? -1,
      align: 'right',
    },
    {
      id: 'engagements',
      header: 'Engagements',
      accessor: (r) => r.totalEngagements?.toLocaleString() ?? '—',
      sortValue: (r) => r.totalEngagements ?? -1,
      align: 'right',
    },
    {
      id: 'er',
      header: 'ER',
      accessor: (r) => formatPercent(r.engagement_rate, 2),
      sortValue: (r) => r.engagement_rate ?? -1,
      align: 'right',
    },
    {
      id: 'velocity',
      header: 'Velocity',
      accessor: (r) => (r.engagement_velocity != null ? r.engagement_velocity.toFixed(3) : '—'),
      sortValue: (r) => r.engagement_velocity ?? -1,
      align: 'right',
    },
    {
      id: 'voice',
      header: 'Voice',
      accessor: (r) => r.creation_metrics?.voice_version_label ?? '—',
    },
    {
      id: 'refScore',
      header: 'Ref score',
      accessor: (r) => (r.refScoreAtPick != null ? r.refScoreAtPick.toFixed(3) : '—'),
      sortValue: (r) => r.refScoreAtPick ?? -1,
      align: 'right',
    },
    {
      id: 'regen',
      header: 'Regen',
      accessor: (r) => r.creation_metrics?.regeneration_round ?? 0,
      sortValue: (r) => r.creation_metrics?.regeneration_round ?? 0,
      align: 'right',
    },
    {
      id: 'followerDelta',
      header: 'Follower Δ',
      accessor: (r) => (
        <span title={FOLLOWER_DELTA_SCOPE}>{r.follower_delta ?? '—'}</span>
      ),
      sortValue: (r) => r.follower_delta ?? -Infinity,
      align: 'right',
    },
    {
      id: 'quality',
      header: 'Quality',
      accessor: (r) => <DataQualityBadge level={r.dataQuality} />,
    },
  ];

  return (
    <div className="posts-table-wrap">
      <p className="field-hint" title={FOLLOWER_DELTA_SCOPE}>
        Follower Δ is account-level since registration, not per-post attribution.
      </p>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.tweet_id}
        emptyMessage="No posts match filters."
        ariaLabel="Tracked posts"
        onRowClick={(r) => navigate(`/accounts/${accountId}/posts/${r.tweet_id}`)}
      />
    </div>
  );
}
