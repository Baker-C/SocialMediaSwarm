import { useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  computeReferenceFunnel,
  enrichPulledTweets,
  searchQueryYield,
} from '../../analytics/selectors/referenceFunnel';
import { referenceFiltersFromSearchParams } from '../../lib/urlFilters';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import { useAccount } from '../../hooks/queries/useAccounts';
import { usePulledTweets } from '../../hooks/queries/usePulledTweets';
import { useTrackedPosts } from '../../hooks/queries/useTrackedPosts';
import type { EnrichedPulledTweet } from '../../types';
import { formatShortDate } from '../../lib/format';

export function ReferencesLabPage() {
  const { accountId } = useParams();
  const [searchParams] = useSearchParams();
  const refFilters = useMemo(
    () => referenceFiltersFromSearchParams(searchParams),
    [searchParams]
  );
  const accountQuery = useAccount(accountId);
  const pulledQuery = usePulledTweets(accountId, refFilters.since);
  const postsQuery = useTrackedPosts(accountId);

  const publishedRefIds = useMemo(() => {
    const ids = new Set<string>();
    for (const p of postsQuery.data?.posts ?? []) {
      const refId = p.creation_metrics?.source_reference_tweet_id;
      if (refId) {
        ids.add(refId);
      }
    }
    return ids;
  }, [postsQuery.data]);

  const copiedIds = accountQuery.data?.copied_reference_tweet_ids ?? [];

  const enriched = useMemo(() => {
    let rows = enrichPulledTweets(pulledQuery.data?.tweets ?? [], copiedIds, publishedRefIds);
    if (refFilters.source) {
      rows = rows.filter((r) => r.source === refFilters.source);
    }
    if (refFilters.entityTag) {
      rows = rows.filter((r) => r.entity_tags?.includes(refFilters.entityTag!));
    }
    if (refFilters.followerTier) {
      rows = rows.filter((r) => r.followerTier === refFilters.followerTier);
    }
    if (refFilters.copyStatus) {
      rows = rows.filter((r) => r.copyStatus === refFilters.copyStatus);
    }
    return rows;
  }, [pulledQuery.data, copiedIds, publishedRefIds, refFilters]);

  const funnel = computeReferenceFunnel(
    pulledQuery.data?.tweets ?? [],
    copiedIds,
    publishedRefIds
  );
  const yieldRows = searchQueryYield(enriched);

  const tweetColumns: DataTableColumn<EnrichedPulledTweet>[] = [
    {
      id: 'source',
      header: 'Source',
      accessor: (r) => r.source || '—',
      sortValue: (r) => r.source,
    },
    {
      id: 'query',
      header: 'Query',
      accessor: (r) => r.trend_query ?? '—',
      sortValue: (r) => r.trend_query ?? '',
    },
    {
      id: 'score',
      header: 'Popularity',
      accessor: (r) => (r.popularityScore != null ? r.popularityScore.toFixed(3) : '—'),
      sortValue: (r) => r.popularityScore ?? -1,
      align: 'right',
    },
    {
      id: 'norm',
      header: 'Norm score',
      accessor: (r) =>
        r.normalizedReferenceScore != null ? r.normalizedReferenceScore.toFixed(3) : '—',
      sortValue: (r) => r.normalizedReferenceScore ?? -1,
      align: 'right',
    },
    {
      id: 'status',
      header: 'Status',
      accessor: (r) => r.copyStatus,
      sortValue: (r) => r.copyStatus,
    },
    {
      id: 'tier',
      header: 'Author tier',
      accessor: (r) => r.followerTier,
    },
    {
      id: 'pulled',
      header: 'Last pulled',
      accessor: (r) => formatShortDate(r.last_pulled_at),
      sortValue: (r) => r.last_pulled_at ?? '',
    },
  ];

  return (
    <div className="page-content">
      <PageHeader title="References Lab" subtitle="Pulled tweets, funnel, and query yield" />

      <div className="funnel-strip" aria-label="Reference funnel">
        <div className="funnel-strip__step">
          <span className="funnel-strip__label">Pulled</span>
          <span className="funnel-strip__value">{funnel.pulled}</span>
        </div>
        <div className="funnel-strip__step">
          <span className="funnel-strip__label">Copied</span>
          <span className="funnel-strip__value">{funnel.copied}</span>
        </div>
        <div className="funnel-strip__step">
          <span className="funnel-strip__label">Published from</span>
          <span className="funnel-strip__value">{funnel.published}</span>
        </div>
      </div>

      <section className="hq-panel" aria-label="Search query yield">
        <h3 className="hq-panel__title">Search query yield</h3>
        <DataTable
          columns={[
            { id: 'q', header: 'Query', accessor: (r) => r.query, sortValue: (r) => r.query },
            {
              id: 'count',
              header: 'Count',
              accessor: (r) => r.count,
              sortValue: (r) => r.count,
              align: 'right',
            },
            {
              id: 'avg',
              header: 'Avg score',
              accessor: (r) => (r.avgScore != null ? r.avgScore.toFixed(3) : '—'),
              sortValue: (r) => r.avgScore ?? -1,
              align: 'right',
            },
          ]}
          rows={yieldRows}
          rowKey={(r) => r.query}
          emptyMessage="No queries."
          ariaLabel="Search query yield"
        />
      </section>

      {pulledQuery.isLoading ? <p className="App-loading">Loading references…</p> : null}
      {!pulledQuery.isLoading ? (
        <section className="hq-panel" aria-label="Pulled tweets">
          <h3 className="hq-panel__title">Pulled tweets</h3>
          <DataTable
            columns={tweetColumns}
            rows={enriched}
            rowKey={(r) => r.tweet_id}
            emptyMessage="No pulled tweets."
            ariaLabel="Pulled tweets table"
          />
        </section>
      ) : null}
    </div>
  );
}
