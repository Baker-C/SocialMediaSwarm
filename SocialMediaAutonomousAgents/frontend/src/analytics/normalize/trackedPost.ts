import type { TrackedPost, DataQualityLevel } from '../../types';

export function totalEngagements(post: TrackedPost): number | null {
  const parts = [
    post.like_count,
    post.reply_count,
    post.retweet_count,
    post.quote_count,
  ];
  if (parts.every((p) => p === null || p === undefined)) {
    return null;
  }
  return parts.reduce<number>((sum, p) => sum + (p ?? 0), 0);
}

export function inferDataQuality(post: TrackedPost): DataQualityLevel {
  const hasCounts =
    post.like_count !== null &&
    post.like_count !== undefined &&
    post.reply_count !== null &&
    post.reply_count !== undefined;
  const hasImpressions =
    post.impression_count !== null && post.impression_count !== undefined;
  if (hasCounts && hasImpressions) {
    return 'full';
  }
  if (hasCounts || hasImpressions) {
    return 'partial';
  }
  return 'missing';
}

export function textSnippet(post: TrackedPost, maxLen = 80): string {
  const raw =
    post.text ??
    (typeof post.raw_metrics?.text === 'string' ? post.raw_metrics.text : '') ??
    '';
  const trimmed = raw.trim();
  if (!trimmed) {
    return post.tweet_id;
  }
  return trimmed.length > maxLen ? `${trimmed.slice(0, maxLen)}…` : trimmed;
}

export function normalizeTrackedPost(post: TrackedPost) {
  return {
    ...post,
    dataQuality: inferDataQuality(post),
    totalEngagements: totalEngagements(post),
    textSnippet: textSnippet(post),
  };
}

export function normalizeTrackedPosts(posts: TrackedPost[]) {
  return posts.map(normalizeTrackedPost);
}
