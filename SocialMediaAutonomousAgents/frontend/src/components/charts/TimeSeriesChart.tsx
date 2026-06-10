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
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          {series.map((s) => (
            <Line
              key={s.dataKey}
              type="monotone"
              dataKey={s.dataKey}
              name={s.name}
              stroke={s.color ?? '#2563eb'}
              dot={false}
              strokeWidth={2}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
