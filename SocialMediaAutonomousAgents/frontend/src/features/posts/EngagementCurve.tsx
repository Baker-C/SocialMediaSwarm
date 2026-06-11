import { TimeSeriesChart } from '../../components/charts/TimeSeriesChart';
import type { EngagementCurvePoint } from '../../analytics/selectors/engagementCurves';

type EngagementCurveProps = {
  points: EngagementCurvePoint[];
};

export function EngagementCurve({ points }: EngagementCurveProps) {
  const chartData = points.map((p) => ({
    label: p.label,
    impressions: p.impressions,
    engagements: p.engagements,
    er: p.engagementRate != null ? p.engagementRate * 100 : null,
    velocity: p.velocity,
  }));

  return (
    <section className="hq-panel" aria-label="Engagement curve">
      <h3 className="hq-panel__title">Engagement over time</h3>
      <TimeSeriesChart
        data={chartData}
        xKey="label"
        series={[
          { dataKey: 'impressions', name: 'Impressions', color: '#f97316' },
          { dataKey: 'engagements', name: 'Engagements', color: '#ffffff' },
          { dataKey: 'er', name: 'ER %', color: '#ef4444' },
        ]}
        height={320}
        ariaLabel="Post engagement curve"
      />
    </section>
  );
}
