import { useState } from 'react';
import type { PipelineRun, PipelineStepRecord } from '../../types/domain/pipelineRun';
import type { StepLink } from '../../types/domain/stepOutput';
import { useStepOutput } from '../../hooks/queries/useStepOutput';
import { StepContentPanel } from './StepContentPanel';

type ChainRow = {
  stepId: string;
  scope: string;
  seq: number;
  status: string;
  durationMs?: number | null;
};

// Source of truth for the chain: step_links (doc 08, full+durable); fall back to
// the NATS-projected nested steps only when step_links is empty/absent.
function chainRows(run: PipelineRun): ChainRow[] {
  if (run.step_links && run.step_links.length) {
    return [...run.step_links]
      .sort((a, b) => a.seq - b.seq)
      .map((l) => ({ stepId: l.step_id, scope: l.scope, seq: l.seq,
                     status: l.status, durationMs: l.duration_ms }));
  }
  // legacy fallback: nested steps carry no seq; preserve array order.
  return run.steps.map((s, i) => ({ stepId: s.step_id, scope: s.scope, seq: i + 1,
                                    status: s.status, durationMs: s.duration_ms }));
}

const STATUS_COLOR: Record<string, string> = {
  ok: '#22c55e',
  active: '#3b82f6',
  running: '#3b82f6',
  error: 'hsl(var(--destructive))',
  rejected: '#f59e0b',
  skipped: 'hsl(var(--muted-foreground))',
};

function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? 'hsl(var(--muted-foreground))';
}

function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return '';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms} ms`;
}

const badge = (color: string) => ({
  display: 'inline-block',
  padding: '0.1rem 0.5rem',
  borderRadius: '999px',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  color: '#fff',
  background: color,
} as const);

const tag = {
  fontSize: 11,
  color: 'hsl(var(--muted-foreground))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 4,
  padding: '0.05rem 0.4rem',
} as const;

const metaText = { fontSize: 12, color: 'hsl(var(--muted-foreground))' } as const;

function TraceRow({ row, run, onExpand }: { row: ChainRow; run: PipelineRun; onExpand: (stepId: string) => void }) {
  return (
    <li
      style={{
        border: '1px solid hsl(var(--border))',
        borderRadius: 'var(--radius)',
        padding: '0.75rem 0.85rem',
        marginBottom: '0.6rem',
        cursor: 'pointer',
      }}
      onClick={() => onExpand(row.stepId)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onExpand(row.stepId);
        }
      }}
    >
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={badge(statusColor(row.status))}>{row.status}</span>
        <strong style={{ fontSize: 13 }}>{row.stepId}</strong>
        <span style={tag}>{row.scope}</span>
        {row.durationMs != null ? <span style={metaText}>{fmtDuration(row.durationMs)}</span> : null}
      </div>
    </li>
  );
}

export function RunTraceViewer({ run }: { run: PipelineRun | undefined }) {
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);
  const stepOutput = useStepOutput(
    run?.run_id,
    expandedStepId ?? undefined,
    expandedStepId != null
  );

  if (!run) {
    return (
      <div style={{ padding: '1rem', textAlign: 'center', color: 'hsl(var(--muted-foreground))' }}>
        No run available.
      </div>
    );
  }

  const rows = chainRows(run);
  if (rows.length === 0) {
    return (
      <div style={{ padding: '1rem', textAlign: 'center', color: 'hsl(var(--muted-foreground))' }}>
        No steps recorded.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div>
        <h4 style={{ marginBottom: '0.5rem', fontSize: 13, fontWeight: 600 }}>
          Run trace ({rows.length} steps)
        </h4>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {rows.map((row) => (
            <TraceRow
              key={row.stepId}
              row={row}
              run={run}
              onExpand={(stepId) => setExpandedStepId(stepId === expandedStepId ? null : stepId)}
            />
          ))}
        </ul>
      </div>

      {expandedStepId && (
        <div>
          <h4 style={{ marginBottom: '0.5rem', fontSize: 13, fontWeight: 600 }}>
            Step content: {expandedStepId}
          </h4>
          {stepOutput.isLoading && <div style={metaText}>Loading…</div>}
          {stepOutput.error && (
            <div style={{ ...metaText, color: 'hsl(var(--destructive))' }}>
              Error: {stepOutput.error instanceof Error ? stepOutput.error.message : String(stepOutput.error)}
            </div>
          )}
          {stepOutput.data && <StepContentPanel stepOutput={stepOutput.data} />}
        </div>
      )}
    </div>
  );
}
