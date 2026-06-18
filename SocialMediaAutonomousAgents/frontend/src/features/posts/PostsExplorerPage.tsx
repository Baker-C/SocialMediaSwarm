import { useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { normalizeTrackedPosts } from '../../analytics/normalize/trackedPost';
import { filterPosts, postTableRows } from '../../analytics/selectors/filterPosts';
import { postFiltersFromSearchParams } from '../../lib/urlFilters';
import { isStaleFetch } from '../../lib/format';
import { FilterBar } from '../../components/filters/FilterBar';
import { useTrackedPosts } from '../../hooks/queries/useTrackedPosts';
import type { TrackedPost } from '../../types';
import { LatestRunPanel } from './LatestRunPanel';
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

  return (
    <div className="page-content">
      {staleBanner ? (
        <div className="stale-banner" role="status">
          Some recent posts have stale metrics (last fetch &gt; 2h ago).
        </div>
      ) : null}

      {accountId ? <LatestRunPanel accountId={accountId} /> : null}

      <FilterBar onChange={() => undefined} />

      {postsQuery.isLoading ? <p className="App-loading">Loading posts…</p> : null}
      {!postsQuery.isLoading ? <PostsTable accountId={accountId!} rows={rows} /> : null}
    </div>
  );
}
