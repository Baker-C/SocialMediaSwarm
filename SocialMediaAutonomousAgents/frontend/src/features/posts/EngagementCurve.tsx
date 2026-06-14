import { useMemo, useState } from 'react';
import type { EngagementCurvePoint } from '../../analytics/selectors/engagementCurves';
import { formatShortDate } from '../../lib/format';
import { TimeSeriesChart, type TimeSeriesSeries } from '../../components/charts/TimeSeriesChart';
import { CHART_COLORS } from '../../components/charts/chartTheme';

type EngagementCurveProps = {
  points: EngagementCurvePoint[];
};

type CurveMetricKey = 'impressions' | 'engagements' | 'er' | 'velocity';

const CURVE_METRICS: { key: CurveMetricKey; label: string; color: string }[] = [
  { key: 'impressions', label: 'Impressions', color: CHART_COLORS.orange },
  { key: 'engagements', label: 'Engagements', color: CHART_COLORS.white },
  { key: 'er', label: 'ER %', color: CHART_COLORS.red },
  { key: 'velocity', label: 'Velocity', color: CHART_COLORS.yellow },
];

const DEFAULT_ENABLED_METRICS: CurveMetricKey[] = [
  'impressions',
  'engagements',
  'er',
  'velocity',
];

type CurveTimeRange = 'day' | 'week' | 'all';

const TIME_RANGES: { key: CurveTimeRange; label: string }[] = [
  { key: 'day', label: 'Day' },
  { key: 'week', label: 'Week' },
  { key: 'all', label: 'All time' },
];

const MS_PER_DAY = 86_400_000;

function filterByTimeRange(points: EngagementCurvePoint[], range: CurveTimeRange): EngagementCurvePoint[] {
  if (range === 'all' || points.length === 0) {
    return points;
  }
  const windowMs = range === 'day' ? MS_PER_DAY : 7 * MS_PER_DAY;
  const cutoff = Date.now() - windowMs;
  return points.filter((point) => {
    const capturedAt = Date.parse(point.capturedAt);
    return !Number.isNaN(capturedAt) && capturedAt >= cutoff;
  });
}

export function EngagementCurve({ points }: EngagementCurveProps) {
  const [enabled, setEnabled] = useState<Set<CurveMetricKey>>(
    () => new Set<CurveMetricKey>(DEFAULT_ENABLED_METRICS)
  );
  const [timeRange, setTimeRange] = useState<CurveTimeRange>('all');

  const filteredPoints = useMemo(() => filterByTimeRange(points, timeRange), [points, timeRange]);

  const chartData = useMemo(
    () =>
      filteredPoints.map((p) => ({
        capturedAt: p.capturedAt,
        label: p.label,
        impressions: p.impressions,
        engagements: p.engagements,
        er: p.engagementRate != null ? p.engagementRate * 100 : null,
        velocity: p.velocity,
      })),
    [filteredPoints]
  );

  const toggleMetric = (key: CurveMetricKey) => {
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
      CURVE_METRICS.filter((m) => enabled.has(m.key)).map((m) => ({
        dataKey: m.key,
        name: m.label,
        color: m.color,
      })),
    [enabled]
  );

  const enabledLabels = series.map((s) => s.name).join(', ');

  return (
    <section className="hq-panel" aria-label="Engagement curve">
      <h3 className="hq-panel__title">Engagement over time</h3>
      <div className="chart-toolbar">
        <div className="chart-series-toggles" role="group" aria-label="Chart metrics">
          {CURVE_METRICS.map((m) => {
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
                name="engagement-time-range"
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
        height={320}
        ariaLabel={`Post engagement over time: ${enabledLabels}`}
      />
    </section>
  );
}
