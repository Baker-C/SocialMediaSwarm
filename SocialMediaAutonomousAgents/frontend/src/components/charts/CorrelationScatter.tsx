import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { CorrelationPoint } from '../../analytics/selectors/engagementCurves';

type CorrelationScatterProps = {
  points: CorrelationPoint[];
};

export function CorrelationScatter({ points }: CorrelationScatterProps) {
  if (points.length === 0) {
    return <p className="page-hint">Not enough posts with reference scores and ER for scatter.</p>;
  }

  const data = points.map((p) => ({
    refScore: p.refScore,
    postEr: p.postEr * 100,
    tweetId: p.tweetId,
  }));

  return (
    <section className="hq-panel" aria-label="Reference score vs post ER">
      <h3 className="hq-panel__title">Ref score vs post ER</h3>
      <div className="time-series-chart" role="img" aria-label="Correlation scatter plot">
        <ResponsiveContainer width="100%" height={280}>
          <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              type="number"
              dataKey="refScore"
              name="Ref score"
              tick={{ fontSize: 12 }}
            />
            <YAxis
              type="number"
              dataKey="postEr"
              name="Post ER %"
              tick={{ fontSize: 12 }}
            />
            <ZAxis range={[40, 40]} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={data} fill="#2563eb" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
