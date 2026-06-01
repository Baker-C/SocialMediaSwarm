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
};

export type AccountEditPayload = {
  account_id: string;
  niche: string;
  twitter_handle: string;
  status: string;
  system_prompt: string;
  buffer_organization_id: string;
  buffer_channel_id: string;
  followers: number;
  posts_total: number;
  registered_at?: string | null;
  last_interval_slot?: string | null;
  last_post_id?: string | null;
  credential_mode: string;
};

export type ApiState = {
  health?: unknown;
  accounts?: unknown;
  posts?: unknown;
  patterns?: unknown;
  dashboard?: unknown;
};

export type DashboardPayload = {
  active_accounts?: number;
  top_niche?: string;
  avg_engagement?: number;
};
