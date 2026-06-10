import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { SkipReasonRow } from '../../analytics/selectors/pipelineOps';

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
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis type="number" tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="reason" width={120} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="count" fill="#7c3aed" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
