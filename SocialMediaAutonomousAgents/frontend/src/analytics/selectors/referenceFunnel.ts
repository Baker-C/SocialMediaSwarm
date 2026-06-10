import type { PulledTweet } from '../../types';
import type { EnrichedPulledTweet } from '../../types/domain/reference';
import {
  followerTier,
  normalizedReferenceScore,
  popularityScore,
} from '../derived/popularityScore';

export type ReferenceFunnelStats = {
  pulled: number;
  copied: number;
  published: number;
};

export type SearchQueryYieldRow = {
  query: string;
  count: number;
  avgScore: number | null;
};

export function computeReferenceFunnel(
  tweets: PulledTweet[],
  copiedIds: string[],
  publishedRefIds: Set<string>
): ReferenceFunnelStats {
  const copiedSet = new Set(copiedIds);
  let copied = 0;
  let published = 0;
  for (const t of tweets) {
    if (copiedSet.has(t.tweet_id)) {
      copied += 1;
    }
    if (publishedRefIds.has(t.tweet_id)) {
      published += 1;
    }
  }
  return { pulled: tweets.length, copied, published };
}

export function enrichPulledTweets(
  tweets: PulledTweet[],
  copiedIds: string[],
  publishedRefIds: Set<string>
): EnrichedPulledTweet[] {
  const copiedSet = new Set(copiedIds);
  const scores = tweets.map((t) => popularityScore(t)).filter((s): s is number => s !== null);
  const maxScore = scores.length > 0 ? Math.max(...scores) : 0;

  return tweets.map((t) => {
    let copyStatus: EnrichedPulledTweet['copyStatus'] = 'unused';
    if (publishedRefIds.has(t.tweet_id)) {
      copyStatus = 'published';
    } else if (copiedSet.has(t.tweet_id)) {
      copyStatus = 'copied';
    }
    return {
      ...t,
      popularityScore: popularityScore(t),
      normalizedReferenceScore: normalizedReferenceScore(t, maxScore),
      copyStatus,
      followerTier: followerTier(t.author_followers_count),
    };
  });
}

export function searchQueryYield(tweets: EnrichedPulledTweet[]): SearchQueryYieldRow[] {
  const byQuery = new Map<string, { count: number; scores: number[] }>();
  for (const t of tweets) {
    const q = t.trend_query?.trim() || t.source?.trim() || '(unknown)';
    const entry = byQuery.get(q) ?? { count: 0, scores: [] };
    entry.count += 1;
    if (t.popularityScore !== null) {
      entry.scores.push(t.popularityScore);
    }
    byQuery.set(q, entry);
  }
  const rows: SearchQueryYieldRow[] = [];
  byQuery.forEach(({ count, scores }, query) => {
    rows.push({
      query,
      count,
      avgScore: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    });
  });
  return rows.sort((a, b) => b.count - a.count);
}
