export const SAVED_FILTERS_KEY = 'sma-post-filter-presets';

export const POST_INTERVAL_MINUTES = 30;

export const PHASE_LABELS: Record<string, string> = {
  runner: 'Post runner',
  reference_phase: 'Reference phase',
  engagement_job: 'Engagement job',
  metrics_job: 'Metrics job',
};

export const STATUS_LABELS: Record<string, string> = {
  success: 'Success',
  skip: 'Skipped',
  reject: 'Rejected',
  error: 'Error',
  partial_or_failed: 'Partial / failed',
};

export const OPS_HIGHLIGHT_REASONS = new Set(['x_metrics_402', 'partial_or_failed']);

export const LIFECYCLE_LABELS = {
  early: 'Early (<6h)',
  maturing: 'Maturing (6–48h)',
  mature: 'Mature (>48h)',
} as const;
