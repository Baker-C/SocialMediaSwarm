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
import { TablePanelHeader } from '../data/TablePanelHeader';
import {
  CHART_AXIS_LINE,
  CHART_AXIS_TICK,
  CHART_COLORS,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_CONTENT_STYLE,
  CHART_TOOLTIP_LABEL_STYLE,
} from './chartTheme';

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
      <TablePanelHeader title="Ref score vs post ER" tableId="ref-score-vs-er" />
      <div className="time-series-chart" role="img" aria-label="Correlation scatter plot">
        <ResponsiveContainer width="100%" height={280}>
          <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
            <XAxis
              type="number"
              dataKey="refScore"
              name="Ref score"
              tick={CHART_AXIS_TICK}
              axisLine={CHART_AXIS_LINE}
              tickLine={CHART_AXIS_LINE}
            />
            <YAxis
              type="number"
              dataKey="postEr"
              name="Post ER %"
              tick={CHART_AXIS_TICK}
              axisLine={CHART_AXIS_LINE}
              tickLine={CHART_AXIS_LINE}
            />
            <ZAxis range={[40, 40]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3', stroke: CHART_GRID_STROKE }}
              contentStyle={CHART_TOOLTIP_CONTENT_STYLE}
              labelStyle={CHART_TOOLTIP_LABEL_STYLE}
            />
            <Scatter data={data} fill={CHART_COLORS.orange} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
