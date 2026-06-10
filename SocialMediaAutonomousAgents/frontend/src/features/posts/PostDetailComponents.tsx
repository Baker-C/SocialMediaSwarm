import type { TrackedPost } from '../../types';
import { FOLLOWER_DELTA_SCOPE } from '../../types/domain/trackedPost';
import { formatNumber, formatPercent } from '../../lib/format';

type PostMetricsGridProps = {
  post: TrackedPost;
};

export function PostMetricsGrid({ post }: PostMetricsGridProps) {
  const tiles = [
    { label: 'Likes', value: formatNumber(post.like_count) },
    { label: 'Replies', value: formatNumber(post.reply_count) },
    { label: 'Retweets', value: formatNumber(post.retweet_count) },
    { label: 'Quotes', value: formatNumber(post.quote_count) },
    { label: 'Impressions', value: formatNumber(post.impression_count) },
    { label: 'Profile clicks', value: formatNumber(post.profile_click_count) },
    { label: 'ER', value: formatPercent(post.engagement_rate, 2) },
    { label: 'Reply rate', value: formatPercent(post.reply_rate, 2) },
    { label: 'Like rate', value: formatPercent(post.like_rate, 2) },
    {
      label: 'Follower Δ (account)',
      value: formatNumber(post.follower_delta),
      title: FOLLOWER_DELTA_SCOPE,
    },
    { label: 'Velocity', value: post.engagement_velocity?.toFixed(4) ?? '—' },
  ];

  return (
    <div className="metrics-grid" aria-label="Post metrics">
      {tiles.map((t) => (
        <div key={t.label} className="metrics-grid__tile" title={t.title}>
          <span className="metrics-grid__label">{t.label}</span>
          <span className="metrics-grid__value">{t.value}</span>
        </div>
      ))}
    </div>
  );
}

type PostCreationCardProps = {
  post: TrackedPost;
};

export function PostCreationCard({ post }: PostCreationCardProps) {
  const cm = post.creation_metrics;
  if (!cm) {
    return <p className="page-hint">No creation metrics recorded for this post.</p>;
  }

  return (
    <section className="hq-panel" aria-label="Post creation metrics">
      <h3 className="hq-panel__title">Creation metrics</h3>
      <dl className="detail-dl">
        <dt>Voice</dt>
        <dd>
          {cm.voice_version_label ?? '—'} (seq {cm.voice_version_seq ?? '—'})
        </dd>
        <dt>Regeneration round</dt>
        <dd>{cm.regeneration_round ?? 0}</dd>
        <dt>Source reference</dt>
        <dd>{cm.source_reference_tweet_id ?? '—'}</dd>
        <dt>Chosen topic</dt>
        <dd>{cm.chosen_topic ?? '—'}</dd>
        <dt>Tweets pulled</dt>
        <dd>{cm.tweets_pulled ?? 0} (new {cm.tweets_pulled_new ?? 0})</dd>
      </dl>
      {cm.source_reference_metrics_at_pick ? (
        <details className="detail-expand">
          <summary>Reference metrics at pick</summary>
          <pre>{JSON.stringify(cm.source_reference_metrics_at_pick, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}

type ReferencePickCompareProps = {
  post: TrackedPost;
};

export function ReferencePickCompare({ post }: ReferencePickCompareProps) {
  const refMetrics = post.creation_metrics?.source_reference_metrics_at_pick;
  const refScore =
    typeof refMetrics?.popularity_score === 'number' ? refMetrics.popularity_score : null;
  const postEr = post.engagement_rate;

  if (refScore == null && postEr == null) {
    return null;
  }

  return (
    <section className="hq-panel" aria-label="Reference vs post ER">
      <h3 className="hq-panel__title">Reference pick vs post ER</h3>
      <div className="compare-strip">
        <div>
          <span className="compare-strip__label">Ref score at pick</span>
          <span className="compare-strip__value">
            {refScore != null ? refScore.toFixed(3) : '—'}
          </span>
        </div>
        <div>
          <span className="compare-strip__label">Post ER</span>
          <span className="compare-strip__value">{formatPercent(postEr, 2)}</span>
        </div>
      </div>
    </section>
  );
}
