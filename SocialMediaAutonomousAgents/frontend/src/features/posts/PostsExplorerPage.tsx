import { useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { normalizeTrackedPosts } from '../../analytics/normalize/trackedPost';
import { filterPosts, postTableRows } from '../../analytics/selectors/filterPosts';
import { postFiltersFromSearchParams } from '../../lib/urlFilters';
import { downloadCsv, rowsToCsv } from '../../lib/csv';
import { isStaleFetch } from '../../lib/format';
import { FilterBar } from '../../components/filters/FilterBar';
import { PageHeader } from '../../components/layout/PageHeader';
import { useTrackedPosts } from '../../hooks/queries/useTrackedPosts';
import type { TrackedPost } from '../../types';
import { PostsTable } from './PostsTable';

export function PostsExplorerPage() {
  const { accountId } = useParams();
  const [searchParams] = useSearchParams();
  const filters = useMemo(() => postFiltersFromSearchParams(searchParams), [searchParams]);
  const postsQuery = useTrackedPosts(accountId, filters);

  const rows = useMemo(() => {
    const normalized = normalizeTrackedPosts(postsQuery.data?.posts ?? []);
    const filtered = filterPosts(normalized, filters);
    return postTableRows(filtered);
  }, [postsQuery.data, filters]);

  const staleBanner = useMemo(() => {
    const posts = postsQuery.data?.posts ?? [];
    const recent = posts.slice(0, 5);
    return recent.some((p: TrackedPost) => isStaleFetch(p.last_fetched_at));
  }, [postsQuery.data]);

  const exportCsv = () => {
    const headers = [
      'tweet_id',
      'posted_at',
      'impressions',
      'engagement_rate',
      'velocity',
      'voice',
      'regen_round',
      'follower_delta',
    ];
    const data = rows.map((r) => ({
      tweet_id: r.tweet_id,
      posted_at: r.posted_at,
      impressions: r.impression_count,
      engagement_rate: r.engagement_rate,
      velocity: r.engagement_velocity,
      voice: r.creation_metrics?.voice_version_label,
      regen_round: r.creation_metrics?.regeneration_round,
      follower_delta: r.follower_delta,
    }));
    downloadCsv(`${accountId}-posts.csv`, rowsToCsv(headers, data));
  };

  return (
    <div className="page-content">
      <PageHeader
        title="Posts Explorer"
        subtitle="Tracked posts with filters and export"
        actions={
          <button type="button" className="btn btn--ghost" onClick={exportCsv} disabled={rows.length === 0}>
            Export CSV
          </button>
        }
      />

      {staleBanner ? (
        <div className="stale-banner" role="status">
          Some recent posts have stale metrics (last fetch &gt; 2h ago).
        </div>
      ) : null}

      <FilterBar onChange={() => undefined} />

      {postsQuery.isLoading ? <p className="App-loading">Loading posts…</p> : null}
      {!postsQuery.isLoading ? <PostsTable accountId={accountId!} rows={rows} /> : null}
    </div>
  );
}
