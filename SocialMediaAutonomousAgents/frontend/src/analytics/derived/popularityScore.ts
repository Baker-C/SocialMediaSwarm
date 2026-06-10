import type { PulledTweet } from '../../types';

export function popularityScore(tweet: PulledTweet): number | null {
  const likes = tweet.like_count ?? 0;
  const replies = tweet.reply_count ?? 0;
  const retweets = tweet.retweet_count ?? 0;
  const quotes = tweet.quote_count ?? 0;
  const impressions = tweet.impression_count;
  const engagement = likes + replies + retweets + quotes;
  if (impressions && impressions > 0) {
    return engagement / impressions;
  }
  if (engagement > 0) {
    return engagement;
  }
  return null;
}

export function normalizedReferenceScore(
  tweet: PulledTweet,
  maxScore: number
): number | null {
  const score = popularityScore(tweet);
  if (score === null || maxScore <= 0) {
    return null;
  }
  return score / maxScore;
}

export function followerTier(followers: number | null | undefined): string {
  const f = followers ?? 0;
  if (f >= 100_000) {
    return '100K+';
  }
  if (f >= 10_000) {
    return '10K–100K';
  }
  if (f >= 1_000) {
    return '1K–10K';
  }
  return '<1K';
}
