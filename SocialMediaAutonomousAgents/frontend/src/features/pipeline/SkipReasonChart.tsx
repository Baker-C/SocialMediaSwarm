import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { SkipReasonRow } from '../../analytics/selectors/pipelineOps';
import {
  CHART_AXIS_LINE,
  CHART_AXIS_TICK,
  CHART_COLORS,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_CONTENT_STYLE,
  CHART_TOOLTIP_LABEL_STYLE,
} from '../../components/charts/chartTheme';

type SkipReasonChartProps = {
  rows: SkipReasonRow[];
};

export function SkipReasonChart({ rows }: SkipReasonChartProps) {
  const top = rows.slice(0, 10);
  if (top.length === 0) {
    return <p className="page-hint">No skip/reject reasons in window.</p>;
  }

  return (
    <div className="time-series-chart" role="img" aria-label="Skip reason pareto chart">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={top} layout="vertical" margin={{ top: 8, right: 16, left: 80, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
          <XAxis
            type="number"
            tick={CHART_AXIS_TICK}
            axisLine={CHART_AXIS_LINE}
            tickLine={CHART_AXIS_LINE}
          />
          <YAxis
            type="category"
            dataKey="reason"
            width={120}
            tick={CHART_AXIS_TICK}
            axisLine={CHART_AXIS_LINE}
            tickLine={CHART_AXIS_LINE}
          />
          <Tooltip
            cursor={{ fill: 'rgba(249, 115, 22, 0.08)' }}
            contentStyle={CHART_TOOLTIP_CONTENT_STYLE}
            labelStyle={CHART_TOOLTIP_LABEL_STYLE}
          />
          <Bar dataKey="count" fill={CHART_COLORS.orange} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
