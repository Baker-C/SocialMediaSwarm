export const FOLLOWER_DELTA_SCOPE =
  'Account-level: followers minus followers at registration, not per-post attribution.';

export type PostCreationMetrics = {
  candidates_created?: number;
  tweets_pulled?: number;
  tweets_pulled_new?: number;
  tweets_pulled_duplicates?: number;
  regeneration_round?: number;
  chosen_topic?: string | null;
  chosen_topic_id?: string | null;
  source_reference_tweet_id?: string | null;
  chosen_embed_url?: string | null;
  voice_version_hash?: string | null;
  voice_version_seq?: number | null;
  voice_version_label?: string | null;
  source_reference_metrics_at_pick?: Record<string, unknown> | null;
};

export type TrackedPost = {
  account_id: string;
  tweet_id: string;
  posted_at?: string;
  text?: string | null;
  last_fetched_at?: string | null;
  like_count?: number | null;
  reply_count?: number | null;
  retweet_count?: number | null;
  quote_count?: number | null;
  impression_count?: number | null;
  engagement_rate?: number | null;
  reply_rate?: number | null;
  like_rate?: number | null;
  followers_at_post?: number | null;
  follower_delta?: number | null;
  profile_click_count?: number | null;
  engagement_velocity?: number | null;
  raw_metrics?: Record<string, unknown>;
  creation_metrics?: PostCreationMetrics | null;
  tweet_permalink?: string | null;
  media_types?: string[];
  primary_media_type?: string | null;
};

export type PostMetricSnapshot = {
  account_id: string;
  tweet_id: string;
  captured_at: string;
  like_count?: number | null;
  reply_count?: number | null;
  retweet_count?: number | null;
  quote_count?: number | null;
  impression_count?: number | null;
  profile_click_count?: number | null;
  engagement_rate?: number | null;
  reply_rate?: number | null;
  like_rate?: number | null;
  engagement_velocity?: number | null;
};

export type DataQualityLevel = 'full' | 'partial' | 'missing';

export type EnrichedTrackedPost = TrackedPost & {
  dataQuality: DataQualityLevel;
  totalEngagements: number | null;
  textSnippet: string;
};
