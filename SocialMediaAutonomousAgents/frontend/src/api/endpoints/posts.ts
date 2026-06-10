import { apiFetch } from '../client';
import type { TrackedPost, PostMetricSnapshot } from '../../types';

export type TrackedPostsResponse = {
  account_id: string;
  count: number;
  posts: TrackedPost[];
};

export type PostSnapshotsResponse = {
  account_id: string;
  tweet_id: string;
  count: number;
  snapshots: PostMetricSnapshot[];
};

export async function fetchTrackedPosts(
  accountId: string,
  params?: { limit?: number; since?: string }
): Promise<TrackedPostsResponse> {
  const qs = new URLSearchParams();
  if (params?.limit) {
    qs.set('limit', String(params.limit));
  }
  if (params?.since) {
    qs.set('since', params.since);
  }
  const query = qs.toString();
  return apiFetch<TrackedPostsResponse>(
    `/accounts/${encodeURIComponent(accountId)}/tracked-posts${query ? `?${query}` : ''}`
  );
}

export async function fetchTrackedPost(
  accountId: string,
  tweetId: string
): Promise<TrackedPost> {
  return apiFetch<TrackedPost>(
    `/accounts/${encodeURIComponent(accountId)}/posts/${encodeURIComponent(tweetId)}`
  );
}

export async function fetchPostSnapshots(
  accountId: string,
  tweetId: string,
  limit = 500
): Promise<PostSnapshotsResponse> {
  return apiFetch<PostSnapshotsResponse>(
    `/accounts/${encodeURIComponent(accountId)}/posts/${encodeURIComponent(tweetId)}/snapshots?limit=${limit}`
  );
}
