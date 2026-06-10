export type PulledTweet = {
  tweet_id: string;
  text?: string | null;
  author_id?: string | null;
  created_at?: string | null;
  like_count?: number | null;
  reply_count?: number | null;
  retweet_count?: number | null;
  quote_count?: number | null;
  impression_count?: number | null;
  author_followers_count?: number | null;
  entity_tags?: string[];
  source?: string;
  trend_query?: string | null;
  duplicate_fetch_count?: number;
  pull_count?: number;
  first_pulled_at?: string;
  last_pulled_at?: string;
  tweet_permalink?: string | null;
  primary_media_type?: string | null;
};

export type EnrichedPulledTweet = PulledTweet & {
  popularityScore: number | null;
  normalizedReferenceScore: number | null;
  copyStatus: 'copied' | 'published' | 'unused';
  followerTier: string;
};
