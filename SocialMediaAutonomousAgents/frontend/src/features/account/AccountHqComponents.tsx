import { useMemo, useState } from 'react';
import type { NormalizedSnapshotPoint } from '../../analytics/normalize/accountSnapshot';
import { TimeSeriesChart, type TimeSeriesSeries } from '../../components/charts/TimeSeriesChart';
import { CHART_COLORS } from '../../components/charts/chartTheme';
import type { AccountSummary } from '../../types';
import { formatGrowth, formatShortDate } from '../../lib/format';

type AccountHeaderProps = {
  account: AccountSummary;
};

export function AccountHeader({ account }: AccountHeaderProps) {
  const voiceLabel = account.voice_version_label ?? 'default';
  const voiceSeq = account.voice_version_seq;

  return (
    <header className="account-header">
      <div>
        <h2 className="account-header__title">{account.account_id}</h2>
        <p className="account-header__meta">
          {account.category} · @{account.twitter_handle?.replace(/^@/, '') || '—'} ·{' '}
          {account.followers.toLocaleString()} followers · {formatGrowth(account.follower_growth_vs_registered)}
        </p>
      </div>
      <span className="voice-badge" title="Current voice version">
        Voice {voiceLabel}
        {voiceSeq != null ? ` (#${voiceSeq})` : ''}
      </span>
    </header>
  );
}

type AccountKpiStripProps = {
  trackedPosts: number | null;
  avgEr: number | null;
  avgReply: number | null;
  avgLike: number | null;
  followerDeltaGap: number | null;
};

export function AccountKpiStrip({
  trackedPosts,
  avgEr,
  avgReply,
  avgLike,
  followerDeltaGap,
}: AccountKpiStripProps) {
  const tiles = [
    { label: 'Tracked posts', value: trackedPosts?.toLocaleString() ?? '—' },
    { label: 'Avg ER', value: avgEr != null ? `${(avgEr * 100).toFixed(2)}%` : '—' },
    { label: 'Avg reply rate', value: avgReply != null ? `${(avgReply * 100).toFixed(2)}%` : '—' },
    { label: 'Avg like rate', value: avgLike != null ? `${(avgLike * 100).toFixed(2)}%` : '—' },
    {
      label: 'Follower Δ gap',
      value: followerDeltaGap != null ? followerDeltaGap.toFixed(3) : '—',
      title: 'Engagement gap between positive vs non-positive follower delta buckets',
    },
  ];

  return (
    <div className="kpi-strip" aria-label="Account KPIs">
      {tiles.map((t) => (
        <div key={t.label} className="kpi-strip__tile" title={t.title}>
          <span className="kpi-strip__label">{t.label}</span>
          <span className="kpi-strip__value">{t.value}</span>
        </div>
      ))}
    </div>
  );
}

type CadenceGaugeProps = {
  lastPostAt: string | null | undefined;
  intervalMinutes?: number;
};

export function CadenceGauge({ lastPostAt, intervalMinutes = 30 }: CadenceGaugeProps) {
  const ageMs = lastPostAt ? Date.now() - Date.parse(lastPostAt) : null;
  const ageHours = ageMs != null && !Number.isNaN(ageMs) ? ageMs / 3600000 : null;
  const overdue = ageHours != null && ageHours > intervalMinutes / 60;

  return (
    <div className={`cadence-gauge${overdue ? ' cadence-gauge--overdue' : ''}`}>
      <span className="cadence-gauge__label">Posting cadence</span>
      <span className="cadence-gauge__value">
        Last post {lastPostAt ? formatShortDate(lastPostAt) : 'never'} · target every{' '}
        {intervalMinutes}m
      </span>
      {overdue ? (
        <span className="cadence-gauge__warn">Past expected interval</span>
      ) : null}
    </div>
  );
}

type TrendMetricKey =
  | 'followers'
  | 'totalViews'
  | 'totalLikes'
  | 'totalReposts'
  | 'totalComments';

const TREND_METRICS: { key: TrendMetricKey; label: string; color: string }[] = [
  { key: 'followers', label: 'Followers', color: CHART_COLORS.orange },
  { key: 'totalViews', label: 'Views (1k)', color: CHART_COLORS.neutral },
  { key: 'totalLikes', label: 'Likes', color: CHART_COLORS.white },
  { key: 'totalReposts', label: 'Reposts', color: CHART_COLORS.yellow },
  { key: 'totalComments', label: 'Comments', color: CHART_COLORS.red },
];

type TrendTimeRange = 'day' | 'week' | 'all';

const TIME_RANGES: { key: TrendTimeRange; label: string }[] = [
  { key: 'day', label: 'Day' },
  { key: 'week', label: 'Week' },
  { key: 'all', label: 'All time' },
];

const MS_PER_DAY = 86_400_000;

function filterByTimeRange(
  data: NormalizedSnapshotPoint[],
  range: TrendTimeRange
): NormalizedSnapshotPoint[] {
  if (range === 'all' || data.length === 0) {
    return data;
  }
  const windowMs = range === 'day' ? MS_PER_DAY : 7 * MS_PER_DAY;
  const cutoff = Date.now() - windowMs;
  return data.filter((point) => {
    const capturedAt = Date.parse(point.capturedAt);
    return !Number.isNaN(capturedAt) && capturedAt >= cutoff;
  });
}

type AccountTrendChartProps = {
  data: NormalizedSnapshotPoint[];
};

const DEFAULT_ENABLED_METRICS: TrendMetricKey[] = [
  'followers',
  'totalViews',
  'totalLikes',
  'totalReposts',
  'totalComments',
];

export function AccountTrendChart({ data }: AccountTrendChartProps) {
  const [enabled, setEnabled] = useState<Set<TrendMetricKey>>(
    () => new Set<TrendMetricKey>(DEFAULT_ENABLED_METRICS)
  );
  const [timeRange, setTimeRange] = useState<TrendTimeRange>('all');

  const filteredData = useMemo(() => filterByTimeRange(data, timeRange), [data, timeRange]);

  // Views (impressions) are large — plot them in thousands so "24" means 24k.
  const chartData = useMemo(
    () => filteredData.map((point) => ({ ...point, totalViews: point.totalViews / 1000 })),
    [filteredData]
  );

  const toggleMetric = (key: TrendMetricKey) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size <= 1) return prev;
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const series = useMemo<TimeSeriesSeries[]>(
    () =>
      TREND_METRICS.filter((m) => enabled.has(m.key)).map((m) => ({
        dataKey: m.key,
        name: m.label,
        color: m.color,
      })),
    [enabled]
  );

  const enabledLabels = series.map((s) => s.name).join(', ');

  return (
    <>
      <div className="chart-toolbar">
        <div className="chart-series-toggles" role="group" aria-label="Chart metrics">
          {TREND_METRICS.map((m) => {
            const active = enabled.has(m.key);
            return (
              <button
                key={m.key}
                type="button"
                className={`chart-series-toggle${active ? ' chart-series-toggle--active' : ''}`}
                aria-pressed={active}
                onClick={() => toggleMetric(m.key)}
              >
                <span
                  className="chart-series-toggle__swatch"
                  style={{ backgroundColor: active ? m.color : undefined }}
                  aria-hidden
                />
                {m.label}
              </button>
            );
          })}
        </div>
        <div className="chart-time-range" role="radiogroup" aria-label="Time range">
          {TIME_RANGES.map((range) => (
            <label
              key={range.key}
              className={`chart-time-range__option${
                timeRange === range.key ? ' chart-time-range__option--active' : ''
              }`}
            >
              <input
                type="radio"
                name="trend-time-range"
                value={range.key}
                checked={timeRange === range.key}
                onChange={() => setTimeRange(range.key)}
                className="chart-time-range__input"
              />
              {range.label}
            </label>
          ))}
        </div>
      </div>
      <TimeSeriesChart
        data={chartData}
        xKey="capturedAt"
        displayLabelKey="label"
        formatXTick={(value) => formatShortDate(value)}
        series={series}
        logBase={100}
        ariaLabel={`Account metrics over time (log base 100, views in 1k): ${enabledLabels}`}
      />
    </>
  );
}

