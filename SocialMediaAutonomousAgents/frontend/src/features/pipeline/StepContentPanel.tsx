import type { StepOutputDocument, StepOutputArtifact } from '../../types/domain/stepOutput';

function fmtTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function fmtDuration(ms: number | null | undefined): string {
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

const card = {
  background: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 'var(--radius)',
  padding: '1rem 1.25rem',
  marginBottom: '1.25rem',
  color: 'hsl(var(--card-foreground))',
} as const;

function ArtifactBlock({ art }: { art: StepOutputArtifact }) {
  return (
    <div style={{ marginBottom: '0.8rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
        <code style={{ fontSize: 12, color: 'hsl(var(--foreground))' }}>{art.artifact}</code>
        {!art.present ? <span style={tag}>absent</span> : null}
        {art.size_bytes != null ? <span style={tag}>{fmtBytes(art.size_bytes)}</span> : null}
      </div>
      {art.present && art.value !== undefined ? (
        <pre
          style={{
            background: 'hsl(var(--background))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 6,
            padding: '0.5rem 0.65rem',
            fontSize: 12,
            lineHeight: 1.45,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            overflow: 'auto',
            margin: 0,
          }}
        >
          {formatValue(art.value)}
        </pre>
      ) : null}
    </div>
  );
}

export function StepContentPanel({ stepOutput }: { stepOutput: StepOutputDocument }) {
  return (
    <div style={card}>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
        <span style={badge(statusColor(stepOutput.status))}>{stepOutput.status}</span>
        <strong style={{ fontSize: 13 }}>{stepOutput.step_id}</strong>
        <span style={tag}>{stepOutput.scope}</span>
        {stepOutput.duration_ms != null ? (
          <span style={metaText}>{fmtDuration(stepOutput.duration_ms)}</span>
        ) : null}
      </div>

      {stepOutput.purpose ? (
        <div style={{ ...metaText, marginBottom: '0.3rem' }}>{stepOutput.purpose}</div>
      ) : null}

      <div style={{ ...metaText, marginBottom: '0.5rem' }}>
        {fmtTime(stepOutput.started_at)} {stepOutput.ended_at ? `→ ${fmtTime(stepOutput.ended_at)}` : ''}
      </div>

      {stepOutput.status === 'error' && stepOutput.error ? (
        <div
          style={{
            ...metaText,
            background: 'hsl(var(--destructive) / 0.1)',
            border: '1px solid hsl(var(--destructive) / 0.3)',
            borderRadius: 4,
            padding: '0.5rem 0.65rem',
            marginBottom: '0.5rem',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '0.2rem' }}>
            {stepOutput.error.type || 'Error'}
          </div>
          {stepOutput.error.message ? <div>{stepOutput.error.message}</div> : null}
          {stepOutput.error.traceback ? (
            <pre
              style={{
                fontSize: 11,
                background: 'hsl(var(--background))',
                border: '1px solid hsl(var(--border))',
                borderRadius: 4,
                padding: '0.3rem 0.4rem',
                overflow: 'auto',
                margin: '0.3rem 0 0 0',
              }}
            >
              {stepOutput.error.traceback}
            </pre>
          ) : null}
        </div>
      ) : null}

      {stepOutput.status === 'skipped' && stepOutput.skip_reason ? (
        <div
          style={{
            ...metaText,
            background: 'hsl(var(--muted) / 0.5)',
            border: '1px solid hsl(var(--border))',
            borderRadius: 4,
            padding: '0.5rem 0.65rem',
            marginBottom: '0.5rem',
          }}
        >
          Skipped: {stepOutput.skip_reason}
        </div>
      ) : null}

      {stepOutput.inputs && stepOutput.inputs.length > 0 ? (
        <div style={{ marginTop: '0.5rem' }}>
          <div style={{ ...metaText, fontWeight: 600, marginBottom: '0.3rem' }}>Inputs</div>
          {stepOutput.inputs.map((art, i) => (
            <ArtifactBlock key={`input-${i}`} art={art} />
          ))}
        </div>
      ) : null}

      {stepOutput.outputs && stepOutput.outputs.length > 0 ? (
        <div style={{ marginTop: '0.5rem' }}>
          <div style={{ ...metaText, fontWeight: 600, marginBottom: '0.3rem' }}>Outputs</div>
          {stepOutput.outputs.map((art, i) => (
            <ArtifactBlock key={`output-${i}`} art={art} />
          ))}
        </div>
      ) : null}

      {stepOutput.result_payload ? (
        <div style={{ marginTop: '0.5rem' }}>
          <div style={{ ...metaText, fontWeight: 600, marginBottom: '0.3rem' }}>Result payload</div>
          <pre
            style={{
              background: 'hsl(var(--background))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 6,
              padding: '0.5rem 0.65rem',
              fontSize: 12,
              lineHeight: 1.45,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              overflow: 'auto',
              margin: 0,
            }}
          >
            {formatValue(stepOutput.result_payload)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
