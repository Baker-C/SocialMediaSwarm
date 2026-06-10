import { apiFetch } from '../client';
import type { PulledTweet } from '../../types';

export type PulledTweetsResponse = {
  account_id: string;
  count: number;
  tweets: PulledTweet[];
};

export async function fetchPulledTweets(
  accountId: string,
  params?: { limit?: number; since?: string }
): Promise<PulledTweetsResponse> {
  const qs = new URLSearchParams();
  if (params?.limit) {
    qs.set('limit', String(params.limit));
  }
  if (params?.since) {
    qs.set('since', params.since);
  }
  const query = qs.toString();
  return apiFetch<PulledTweetsResponse>(
    `/accounts/${encodeURIComponent(accountId)}/pulled-tweets${query ? `?${query}` : ''}`
  );
}
