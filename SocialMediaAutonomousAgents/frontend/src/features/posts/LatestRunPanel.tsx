import type { CSSProperties } from 'react';
import { useLatestPipelineRun } from '../../hooks/queries/usePipelineRuns';
import type {
  PipelineRun,
  PipelineStepRecord,
  StepArtifact,
} from '../../types/domain/pipelineRun';

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

function fmtTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function stepDurationMs(step: PipelineStepRecord): number | null {
  if (typeof step.duration_ms === 'number') return step.duration_ms;
  if (step.started_at && step.ended_at) {
    const ms = new Date(step.ended_at).getTime() - new Date(step.started_at).getTime();
    return Number.isFinite(ms) && ms >= 0 ? ms : null;
  }
  return null;
}

function fmtDuration(ms: number | null): string {
  if (ms == null) return '';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms} ms`;
}

function fmtBytes(n?: number): string {
  if (n == null) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const card: CSSProperties = {
  background: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 'var(--radius)',
  padding: '1rem 1.25rem',
  marginBottom: '1.25rem',
  color: 'hsl(var(--card-foreground))',
};

const badge = (color: string): CSSProperties => ({
  display: 'inline-block',
  padding: '0.1rem 0.5rem',
  borderRadius: '999px',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  color: '#fff',
  background: color,
});

const tag: CSSProperties = {
  fontSize: 11,
  color: 'hsl(var(--muted-foreground))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 4,
  padding: '0.05rem 0.4rem',
};

const metaText: CSSProperties = { fontSize: 12, color: 'hsl(var(--muted-foreground))' };

const stepCard: CSSProperties = {
  border: '1px solid hsl(var(--border))',
  borderRadius: 'var(--radius)',
  padding: '0.75rem 0.85rem',
  marginBottom: '0.6rem',
};

const docPre: CSSProperties = {
  maxHeight: 220,
  overflow: 'auto',
  background: 'hsl(var(--background))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 6,
  padding: '0.5rem 0.65rem',
  margin: '0.25rem 0 0',
  fontSize: 12,
  lineHeight: 1.45,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

function ArtifactList({ label, items }: { label: string; items: StepArtifact[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ ...metaText, fontWeight: 600, marginBottom: '0.2rem' }}>{label}</div>
      {items.map((art, i) => (
        <div key={`${art.artifact}-${i}`} style={{ marginBottom: '0.4rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <code style={{ fontSize: 12, color: 'hsl(var(--foreground))' }}>{art.artifact}</code>
            {!art.present ? <span style={tag}>absent</span> : null}
            {art.size_bytes != null ? <span style={tag}>{fmtBytes(art.size_bytes)}</span> : null}
            {art.truncated ? <span style={tag}>truncated</span> : null}
            {art.present && art.value === undefined ? <span style={tag}>metadata only</span> : null}
          </div>
          {art.present && art.value !== undefined ? (
            <pre style={docPre}>{formatValue(art.value)}</pre>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function StepRow({ step }: { step: PipelineStepRecord }) {
  const dur = fmtDuration(stepDurationMs(step));
  return (
    <li style={stepCard}>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={badge(statusColor(step.status))}>{step.status}</span>
        <strong style={{ fontSize: 13 }}>{step.step_id}</strong>
        <span style={tag}>{step.scope}</span>
        {dur ? <span style={metaText}>{dur}</span> : null}
      </div>
      {step.purpose ? (
        <div style={{ ...metaText, marginTop: '0.25rem' }}>{step.purpose}</div>
      ) : null}
      <div style={{ ...metaText, marginTop: '0.2rem' }}>
        {fmtTime(step.started_at)} {step.ended_at ? `→ ${fmtTime(step.ended_at)}` : ''}
      </div>

      {step.skip_reason ? (
        <div style={{ ...metaText, marginTop: '0.3rem' }}>Skip reason: {step.skip_reason}</div>
      ) : null}

      {step.error ? (
        <div style={{ marginTop: '0.4rem' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'hsl(var(--destructive))' }}>
            {step.error.type || 'Error'}: {step.error.message}
          </div>
          {step.error.traceback ? <pre style={docPre}>{step.error.traceback}</pre> : null}
        </div>
      ) : null}

      <ArtifactList label="Inputs" items={step.inputs} />
      <ArtifactList label="Outputs" items={step.outputs} />
    </li>
  );
}

function RunHeader({ run }: { run: PipelineRun }) {
  return (
    <header style={{ marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Latest post · pipeline run</h3>
        <span style={badge(statusColor(run.status))}>{run.status}</span>
        <span style={metaText}>{run.step_count} steps</span>
        {run.duration_ms != null ? (
          <span style={metaText}>{fmtDuration(run.duration_ms)}</span>
        ) : null}
      </div>
      <div style={{ ...metaText, marginTop: '0.3rem' }}>
        <code>{run.run_id}</code> · {run.mode} · slot {run.slot} · started {fmtTime(run.started_at)}
      </div>
    </header>
  );
}

export function LatestRunPanel({ accountId }: { accountId: string }) {
  const { data, isLoading, error } = useLatestPipelineRun(accountId);
  const run = data?.runs?.[0];

  if (isLoading) {
    return <section style={card}>Loading latest pipeline run…</section>;
  }
  if (error) {
    return (
      <section style={card}>
        <span style={{ color: 'hsl(var(--destructive))' }}>
          Failed to load pipeline run: {error instanceof Error ? error.message : 'unknown error'}
        </span>
      </section>
    );
  }
  if (!run) {
    return <section style={card}>No pipeline runs recorded yet for this account.</section>;
  }

  return (
    <section style={card} aria-label="Latest post pipeline run">
      <RunHeader run={run} />
      <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {run.steps.map((step: PipelineStepRecord) => (
          <StepRow key={`${step.scope}:${step.step_id}`} step={step} />
        ))}
      </ol>
    </section>
  );
}
