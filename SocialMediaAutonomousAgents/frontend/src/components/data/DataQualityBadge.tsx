export type DataQualityLevel = 'full' | 'partial' | 'missing';

type DataQualityBadgeProps = {
  level: DataQualityLevel;
  label?: string;
};

const LEVEL_LABELS: Record<DataQualityLevel, string> = {
  full: 'Complete',
  partial: 'Partial',
  missing: 'Missing',
};

export function DataQualityBadge({ level, label }: DataQualityBadgeProps) {
  const text = label ?? LEVEL_LABELS[level];
  return (
    <span className={`data-quality-badge data-quality-badge--${level}`} title={text}>
      {text}
    </span>
  );
}
