import type { PipelineOutcome } from '../../types';
import { OPS_HIGHLIGHT_REASONS } from '../constants';

export type SkipReasonRow = {
  reason: string;
  count: number;
  highlighted: boolean;
};

export type PhaseHealthRow = {
  phase: string;
  total: number;
  success: number;
  successRate: number;
};

export function skipReasonPareto(outcomes: PipelineOutcome[]): SkipReasonRow[] {
  const counts = new Map<string, number>();
  for (const o of outcomes) {
    if (o.status !== 'skip' && o.status !== 'reject') {
      continue;
    }
    const reason = o.reason?.trim() || '(none)';
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  const rows: SkipReasonRow[] = [];
  counts.forEach((count, reason) => {
    rows.push({
      reason,
      count,
      highlighted: OPS_HIGHLIGHT_REASONS.has(reason),
    });
  });
  return rows.sort((a, b) => b.count - a.count);
}

export function phaseHealth(outcomes: PipelineOutcome[]): PhaseHealthRow[] {
  const byPhase = new Map<string, { total: number; success: number }>();
  for (const o of outcomes) {
    const entry = byPhase.get(o.phase) ?? { total: 0, success: 0 };
    entry.total += 1;
    if (o.status === 'success') {
      entry.success += 1;
    }
    byPhase.set(o.phase, entry);
  }
  const rows: PhaseHealthRow[] = [];
  byPhase.forEach(({ total, success }, phase) => {
    rows.push({
      phase,
      total,
      success,
      successRate: total > 0 ? success / total : 0,
    });
  });
  return rows.sort((a, b) => b.total - a.total);
}

export function opsHighlights(outcomes: PipelineOutcome[]): PipelineOutcome[] {
  return outcomes.filter(
    (o) =>
      OPS_HIGHLIGHT_REASONS.has(o.reason ?? '') ||
      o.status === 'partial_or_failed' ||
      o.status === 'error'
  );
}
