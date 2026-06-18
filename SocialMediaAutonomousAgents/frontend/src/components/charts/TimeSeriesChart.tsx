import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  CHART_AXIS_LINE,
  CHART_AXIS_TICK,
  CHART_GRID_STROKE,
  CHART_LEGEND_STYLE,
  CHART_SERIES_PALETTE,
  CHART_TOOLTIP_CONTENT_STYLE,
  CHART_TOOLTIP_LABEL_STYLE,
} from './chartTheme';

export type TimeSeriesSeries = {
  dataKey: string;
  name: string;
  color?: string;
};

type TimeSeriesChartProps = {
  data: Record<string, unknown>[];
  xKey: string;
  series: TimeSeriesSeries[];
  height?: number;
  ariaLabel?: string;
  /** Human-readable tooltip label when xKey is a unique id (e.g. ISO timestamp). */
  displayLabelKey?: string;
  formatXTick?: (value: string) => string;
  /**
   * When set (e.g. 100), the Y axis is logarithmic with ticks at powers of this
   * base. Lets series of very different magnitudes (views vs comments) share one
   * chart. Non-positive values become gaps since a log axis can't plot 0.
   */
  logBase?: number;
};

const compactNumber = (value: number): string =>
  Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

export function TimeSeriesChart({
  data,
  xKey,
  series,
  height = 280,
  ariaLabel = 'Time series chart',
  displayLabelKey,
  formatXTick,
  logBase,
}: TimeSeriesChartProps) {
  if (data.length === 0) {
    return <p className="time-series-chart__empty">No chart data available.</p>;
  }

  const isLog = typeof logBase === 'number' && logBase > 1;
  const seriesKeys = series.map((s) => s.dataKey);

  // Log axes can't plot 0/negatives — turn those into gaps in the line.
  const plotData = isLog
    ? data.map((row) => {
        const next: Record<string, unknown> = { ...row };
        for (const key of seriesKeys) {
          const v = Number(next[key]);
          if (!Number.isFinite(v) || v <= 0) {
            next[key] = null;
          }
        }
        return next;
      })
    : data;

  // Ticks at powers of the chosen base (1, 100, 10 000, …) up to the data max.
  const logTicks = (() => {
    if (!isLog) return undefined;
    let max = 0;
    for (const row of plotData) {
      for (const key of seriesKeys) {
        const v = Number(row[key]);
        if (Number.isFinite(v) && v > max) max = v;
      }
    }
    if (max <= 0) return undefined;
    const ticks: number[] = [];
    let tick = 1;
    while (tick < max * (logBase as number) && ticks.length <= 6) {
      ticks.push(tick);
      tick *= logBase as number;
    }
    return ticks;
  })();

  return (
    <div className="time-series-chart" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={plotData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
          <XAxis
            dataKey={xKey}
            tick={CHART_AXIS_TICK}
            axisLine={CHART_AXIS_LINE}
            tickLine={CHART_AXIS_LINE}
            tickFormatter={formatXTick}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            tick={CHART_AXIS_TICK}
            axisLine={CHART_AXIS_LINE}
            tickLine={CHART_AXIS_LINE}
            {...(isLog
              ? {
                  scale: 'log' as const,
                  domain: [1, 'auto'] as [number, 'auto'],
                  allowDataOverflow: true,
                  ticks: logTicks,
                  tickFormatter: compactNumber,
                }
              : {})}
          />
          <Tooltip
            contentStyle={CHART_TOOLTIP_CONTENT_STYLE}
            labelStyle={CHART_TOOLTIP_LABEL_STYLE}
            labelFormatter={
              displayLabelKey
                ? (_value, payload) => {
                    const row = payload?.[0]?.payload as Record<string, unknown> | undefined;
                    const label = row?.[displayLabelKey];
                    return typeof label === 'string' ? label : '';
                  }
                : undefined
            }
          />
          <Legend wrapperStyle={CHART_LEGEND_STYLE} />
          {series.map((s, i) => (
            <Line
              key={s.dataKey}
              type="monotone"
              dataKey={s.dataKey}
              name={s.name}
              stroke={s.color ?? CHART_SERIES_PALETTE[i % CHART_SERIES_PALETTE.length]}
              dot={false}
              strokeWidth={2}
              strokeDasharray={i === 1 ? '5 5' : undefined}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
