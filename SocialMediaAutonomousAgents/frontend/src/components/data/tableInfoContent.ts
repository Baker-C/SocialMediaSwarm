export type TableInfoColumn = {
  name: string;
  description: string;
};

export type TableInfoContent = {
  title: string;
  measures: string;
  columns: TableInfoColumn[];
  analysis: string;
};

export type TableInfoId =
  | 'tracked-posts'
  | 'voice-comparison'
  | 'pipeline-phase-health'
  | 'pipeline-outcomes'
  | 'fleet-leaderboard'
  | 'references-query-yield'
  | 'references-pulled-tweets'
  | 'post-snapshots';

export const TABLE_INFO: Record<TableInfoId, TableInfoContent> = {
  'tracked-posts': {
    title: 'Tracked posts',
    measures:
      'Published tweets for this account with latest engagement metrics, creation context, and data quality flags. Rows link to post detail.',
    columns: [
      { name: 'Posted', description: 'When the tweet was published (local short date).' },
      { name: 'Text', description: 'Truncated tweet body for quick scanning.' },
      {
        name: 'Impressions',
        description: 'Latest impression count from X analytics (views of the tweet).',
      },
      {
        name: 'Engagements',
        description: 'Sum of likes, replies, retweets, and quotes on the latest fetch.',
      },
      {
        name: 'ER',
        description: 'Engagement rate: engagements divided by impressions (shown as %).',
      },
      {
        name: 'Velocity',
        description: 'Rate of engagement accumulation over time; higher values suggest faster pickup.',
      },
      {
        name: 'Voice',
        description: 'Voice version label used when the post was generated.',
      },
      {
        name: 'Ref score',
        description: 'Normalized reference tweet score at pick time (0–1 scale when available).',
      },
      {
        name: 'Regen',
        description: 'How many regeneration rounds ran before this draft was chosen.',
      },
      {
        name: 'Follower Δ',
        description:
          'Account-level follower change since registration — not attributed to this post alone.',
      },
      {
        name: 'Quality',
        description: 'Data completeness badge: full, partial, or missing key metrics.',
      },
    ],
    analysis:
      'Sort by ER or velocity to find top performers. Compare voice and ref score columns to see whether higher-scored references or newer voice versions correlate with engagement. Click a row for snapshots and creation details. Treat follower Δ as account context, not per-post ROI.',
  },
  'voice-comparison': {
    title: 'Performance by voice version',
    measures:
      'Aggregated engagement for each voice revision used on tracked posts — compares how different voice prompts perform in the wild.',
    columns: [
      { name: 'Voice', description: 'Human-readable label for the voice revision.' },
      { name: 'Seq', description: 'Revision sequence number (order of voice changes).' },
      { name: 'Posts', description: 'Count of tracked posts created under this voice version.' },
      { name: 'Avg ER', description: 'Mean engagement rate across posts for this version.' },
      {
        name: 'Avg impressions',
        description: 'Mean impression count across posts for this version.',
      },
    ],
    analysis:
      'Compare avg ER across versions with similar post counts — small samples can skew results. Newer seq numbers are not automatically better; look for sustained lift over multiple posts. Cross-check with the revision timeline and correlation scatter to spot outliers vs trends.',
  },
  'pipeline-phase-health': {
    title: 'Phase health (7d)',
    measures:
      'Success vs failure counts per pipeline phase over the last seven days — a quick health check for each stage of post creation.',
    columns: [
      { name: 'Phase', description: 'Pipeline stage (e.g. pull, draft, publish).' },
      { name: 'Total', description: 'All outcomes recorded for this phase in the window.' },
      { name: 'Success', description: 'Outcomes with success status.' },
      { name: 'Success rate', description: 'Success divided by total, shown as a percentage.' },
    ],
    analysis:
      'Phases with low success rate need attention first. A high total with moderate rate may be noisy; a low total with 0% success is a blocker. Pair with skip/reject reasons and the outcomes log to find root causes.',
  },
  'pipeline-outcomes': {
    title: 'Pipeline outcomes',
    measures:
      'Chronological log of pipeline events — each row is one phase outcome (success, skip, reject, etc.) for an account.',
    columns: [
      { name: 'Time', description: 'When the outcome was recorded.' },
      {
        name: 'Account',
        description: 'Account id (fleet view only; hidden on single-account pipeline page).',
      },
      { name: 'Phase', description: 'Which pipeline stage produced this outcome.' },
      { name: 'Status', description: 'Result: success, skip, reject, or other terminal state.' },
      {
        name: 'Reason',
        description: 'Machine or human-readable reason when status is not success.',
      },
    ],
    analysis:
      'Sort by time to trace recent failures. Filter mentally by phase and status to spot recurring skips. Fleet view: scan Account column for noisy accounts. Cross-reference highlighted ops alerts and the skip-reason chart for patterns.',
  },
  'fleet-leaderboard': {
    title: 'Account leaderboard',
    measures:
      'Cross-account ranking for operational comparison — engagement, growth, cadence, and OAuth connectivity.',
    columns: [
      { name: 'Account', description: 'Account id; links to account HQ.' },
      { name: 'Niche', description: 'Content niche assigned to the account.' },
      { name: 'Avg ER', description: 'Average engagement rate across tracked posts (when metrics exist).' },
      {
        name: 'Follower growth',
        description: 'Followers gained vs count at registration.',
      },
      { name: 'Last post', description: 'How long ago the most recent post was published.' },
      { name: 'OAuth', description: 'Whether X OAuth is connected (✓ = connected).' },
    ],
    analysis:
      'Sort by avg ER to find top performers; sort by last post to find stale accounts. Accounts without OAuth may lack fresh metrics. Use alongside ops alerts before forcing posts or changing voice.',
  },
  'references-query-yield': {
    title: 'Search query yield',
    measures:
      'How many reference tweets each search query returned and their average quality score — helps tune reference discovery.',
    columns: [
      { name: 'Query', description: 'Search or trend query used to pull references.' },
      { name: 'Count', description: 'Number of pulled tweets matching this query.' },
      {
        name: 'Avg score',
        description: 'Mean normalized reference score for tweets from this query.',
      },
    ],
    analysis:
      'Queries with high count but low avg score may be too broad. Queries with high avg score and low count may be worth expanding. Retire queries that consistently produce unused or low-scoring references.',
  },
  'references-pulled-tweets': {
    title: 'Pulled tweets',
    measures:
      'Reference tweets fetched for inspiration — scored, tagged, and tracked through copy/publish funnel status.',
    columns: [
      { name: 'Source', description: 'Where the tweet was discovered (search, trend, etc.).' },
      { name: 'Query', description: 'Specific query or trend that surfaced this tweet.' },
      {
        name: 'Popularity',
        description: 'Raw popularity score before normalization.',
      },
      {
        name: 'Norm score',
        description: 'Normalized reference score (0–1) for cross-query comparison.',
      },
      {
        name: 'Status',
        description: 'Funnel state: unused, copied into drafts, or published from this reference.',
      },
      {
        name: 'Author tier',
        description: 'Follower-count bucket for the reference author.',
      },
      { name: 'Last pulled', description: 'Most recent time this reference was fetched.' },
    ],
    analysis:
      'Sort by norm score to prioritize strong references. Compare status to funnel counts above — many high-score unused rows suggest selection bottlenecks. Filter by source/query/tier to refine what the pipeline pulls next.',
  },
  'post-snapshots': {
    title: 'Metric snapshots',
    measures:
      'Point-in-time captures of a single post’s metrics over its lifetime — powers the engagement curve and staleness checks.',
    columns: [
      { name: 'Captured', description: 'When this snapshot was taken.' },
      { name: 'Impressions', description: 'Impression count at capture time.' },
      { name: 'ER', description: 'Engagement rate at capture time (%).' },
      {
        name: 'Velocity',
        description: 'Engagement velocity at capture — useful for early vs late performance.',
      },
    ],
    analysis:
      'Read chronologically to see growth phases. Early snapshots with rising velocity indicate strong launch; flat ER after impressions plateau suggests the post has saturated. Compare first vs latest snapshot against the engagement curve chart.',
  },
};
