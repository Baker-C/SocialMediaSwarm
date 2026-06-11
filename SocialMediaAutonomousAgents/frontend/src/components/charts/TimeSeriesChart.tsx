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
};

export function TimeSeriesChart({
  data,
  xKey,
  series,
  height = 280,
  ariaLabel = 'Time series chart',
}: TimeSeriesChartProps) {
  if (data.length === 0) {
    return <p className="time-series-chart__empty">No chart data available.</p>;
  }

  return (
    <div className="time-series-chart" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
          <XAxis
            dataKey={xKey}
            tick={CHART_AXIS_TICK}
            axisLine={CHART_AXIS_LINE}
            tickLine={CHART_AXIS_LINE}
          />
          <YAxis tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
          <Tooltip
            contentStyle={CHART_TOOLTIP_CONTENT_STYLE}
            labelStyle={CHART_TOOLTIP_LABEL_STYLE}
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
