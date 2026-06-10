export type RecentPost = {
  snippet?: string;
  posted_at?: string | null;
  post_id?: string | null;
  views?: number | null;
};

export type AccountSummary = {
  account_id: string;
  niche: string;
  twitter_handle: string;
  status: string;
  followers: number;
  posts_total: number;
  has_credentials?: boolean;
  registered_at?: string | null;
  follower_growth_vs_registered?: number | null;
  last_interval_slot?: string | null;
  recent_post?: RecentPost | null;
  voice_version_label?: string | null;
  voice_version_seq?: number | null;
  search_queries_count?: number | null;
  copied_reference_count?: number | null;
  copied_reference_tweet_ids?: string[];
};

export type AccountEditPayload = {
  account_id: string;
  niche: string;
  twitter_handle: string;
  status: string;
  system_prompt: string;
  followers: number;
  posts_total: number;
  registered_at?: string | null;
  last_interval_slot?: string | null;
  last_post_id?: string | null;
  credential_mode: string;
  oauth_connected?: boolean;
  oauth_expires_at?: string | null;
};

export type OAuthStatus = {
  account_id: string;
  connected: boolean;
  expires_at?: string | null;
  scopes?: string | null;
  x_user_id?: string | null;
  updated_at?: string | null;
};

export type OAuthAuthorizeResponse = {
  account_id: string;
  authorization_url: string;
  state: string;
  redirect_uri?: string;
};

export type AccountSnapshot = {
  account_id: string;
  created_at: string;
  niche?: string;
  twitter_handle?: string;
  followers?: number;
  following_count?: number;
  posts_total?: number;
  total_likes?: number;
  total_views?: number;
};

export type AccountMetrics = {
  account_id: string;
  computed_at?: string;
  avg_engagement_rate?: number | null;
  avg_reply_rate?: number | null;
  avg_like_rate?: number | null;
  avg_follower_delta?: number | null;
  positive_delta_avg_engagement?: number | null;
  non_positive_delta_avg_engagement?: number | null;
  follower_delta_engagement_gap?: number | null;
};

export type DashboardPayload = {
  active_accounts?: number;
  top_niche?: string;
  avg_engagement?: number;
  total_tracked_posts?: number;
  avg_reply_rate?: number;
  accounts_without_posts?: number;
  computed_at?: string;
};
