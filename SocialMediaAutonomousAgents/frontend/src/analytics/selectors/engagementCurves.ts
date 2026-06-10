import type { PostMetricSnapshot } from '../../types';
import { formatShortDate } from '../../lib/format';

export type EngagementCurvePoint = {
  capturedAt: string;
  label: string;
  impressions: number | null;
  engagements: number | null;
  engagementRate: number | null;
  velocity: number | null;
};

function totalEngagements(s: PostMetricSnapshot): number | null {
  const parts = [s.like_count, s.reply_count, s.retweet_count, s.quote_count];
  if (parts.every((p) => p === null || p === undefined)) {
    return null;
  }
  return parts.reduce<number>((sum, p) => sum + (p ?? 0), 0);
}

export function buildEngagementCurve(snapshots: PostMetricSnapshot[]): EngagementCurvePoint[] {
  return [...snapshots]
    .sort((a, b) => a.captured_at.localeCompare(b.captured_at))
    .map((s) => ({
      capturedAt: s.captured_at,
      label: formatShortDate(s.captured_at),
      impressions: s.impression_count ?? null,
      engagements: totalEngagements(s),
      engagementRate: s.engagement_rate ?? null,
      velocity: s.engagement_velocity ?? null,
    }));
}

export type CorrelationPoint = {
  refScore: number;
  postEr: number;
  tweetId: string;
};

type CorrelationPostInput = {
  tweet_id: string;
  engagement_rate?: number | null;
  creation_metrics?: {
    source_reference_metrics_at_pick?: Record<string, unknown> | null;
  } | null;
};

export function buildCorrelationPoints(posts: CorrelationPostInput[]): CorrelationPoint[] {
  return posts
    .map((p) => {
      const refScore = p.creation_metrics?.source_reference_metrics_at_pick?.popularity_score;
      if (typeof refScore !== 'number' || p.engagement_rate == null) {
        return null;
      }
      return {
        refScore,
        postEr: p.engagement_rate,
        tweetId: p.tweet_id,
      };
    })
    .filter((p): p is CorrelationPoint => p !== null);
}
