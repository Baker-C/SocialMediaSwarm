import { useParams } from 'react-router-dom';
import { useBuilderChat } from '../../hooks/useBuilderChat';
import { useAccountSpec } from '../../hooks/queries/useAccountSpec';
import { apiBaseUrl } from '../../api/client';
import { flowFromSpec } from '../../lib/pipeline/specToFlow';
import { PipelineFlowDiagram } from '../pipeline/PipelineFlowDiagram';
import type { FlowNodeState } from '../../types/pipelineProgress';

export function AgentBuilderPage() {
  const { accountId } = useParams();

  const specQuery = useAccountSpec(accountId, 'champion');
  const {
    messages,
    running,
    error: chatError,
    proposal,
    written,
    send,
    approve,
  } = useBuilderChat({
    apiBase: apiBaseUrl(),
    accountId: accountId ?? '',
    mode: 'edit',
  });

  const currentSpec = specQuery.data;
  const proposedSpec = proposal?.spec ?? currentSpec;

  // For rendering: all nodes are 'pending' in preview mode (not a live run).
  const nodeState: FlowNodeState = {};

  const handleSend = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    await send(trimmed);
  };

  const handleApprove = async () => {
    await approve();
  };

  if (!accountId) {
    return <div style={{ padding: '1rem', color: 'hsl(var(--muted-foreground))' }}>Invalid account.</div>;
  }

  if (specQuery.isLoading) {
    return <div style={{ padding: '1rem', color: 'hsl(var(--muted-foreground))' }}>Loading spec…</div>;
  }

  if (specQuery.error) {
    return (
      <div style={{ padding: '1rem', color: 'hsl(var(--destructive))' }}>
        Error loading spec: {specQuery.error instanceof Error ? specQuery.error.message : String(specQuery.error)}
      </div>
    );
  }

  if (!currentSpec) {
    return <div style={{ padding: '1rem', color: 'hsl(var(--muted-foreground))' }}>No spec available.</div>;
  }

  const sections = proposedSpec ? flowFromSpec(proposedSpec) : [];
  const showValidation = proposal || (messages.length > 0 && messages[messages.length - 1]?.validation_errors);
  const validationErrors = messages.length > 0 ? messages[messages.length - 1]?.validation_errors : null;
  const isValid = proposal != null;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', minHeight: '100vh' }}>
      {/* Left pane: chat */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          borderRight: '1px solid hsl(var(--border))',
          overflow: 'hidden',
        }}
      >
        <div style={{ flex: 1, overflow: 'auto', padding: '1rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  gap: '0.5rem',
                }}
              >
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '0.75rem 1rem',
                    borderRadius: 'var(--radius)',
                    background:
                      msg.role === 'user'
                        ? 'hsl(var(--primary))'
                        : 'hsl(var(--card))',
                    color:
                      msg.role === 'user'
                        ? 'hsl(var(--primary-foreground))'
                        : 'hsl(var(--card-foreground))',
                    fontSize: 14,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            {chatError && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--radius)',
                  background: 'hsl(var(--destructive) / 0.1)',
                  color: 'hsl(var(--destructive))',
                  fontSize: 14,
                }}
              >
                Error: {chatError}
              </div>
            )}
          </div>
        </div>

        <div style={{ borderTop: '1px solid hsl(var(--border))', padding: '1rem', display: 'flex', gap: '0.5rem' }}>
          <textarea
            value={messages.length > 0 && messages[messages.length - 1]?.role === 'assistant' ? '' : ''}
            placeholder="Describe the change you want to make…"
            onChange={() => {}}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                const input = e.currentTarget;
                handleSend(input.value);
                input.value = '';
              }
            }}
            disabled={running}
            style={{
              flex: 1,
              padding: '0.5rem',
              borderRadius: 'var(--radius)',
              border: '1px solid hsl(var(--border))',
              fontFamily: 'inherit',
              fontSize: 14,
              resize: 'none',
              maxHeight: 100,
            }}
          />
          <button
            onClick={() => {
              const textarea = document.querySelector('textarea');
              if (textarea) {
                handleSend(textarea.value);
                textarea.value = '';
              }
            }}
            disabled={running}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 'var(--radius)',
              border: '1px solid hsl(var(--border))',
              background: 'hsl(var(--primary))',
              color: 'hsl(var(--primary-foreground))',
              cursor: running ? 'not-allowed' : 'pointer',
              opacity: running ? 0.5 : 1,
            }}
          >
            Send
          </button>
        </div>
      </div>

      {/* Right pane: graph + validation */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          overflow: 'auto',
          padding: '1rem',
        }}
      >
        {proposedSpec && (
          <div style={{ marginBottom: '1.5rem' }}>
            <PipelineFlowDiagram
              sections={sections}
              nodeState={nodeState}
              running={false}
              error={null}
            />
          </div>
        )}

        {showValidation && (
          <div
            style={{
              padding: '1rem',
              borderRadius: 'var(--radius)',
              border: `1px solid ${isValid ? 'hsl(var(--primary))' : 'hsl(var(--destructive))'}`,
              background: isValid ? 'hsl(var(--primary) / 0.05)' : 'hsl(var(--destructive) / 0.05)',
            }}
          >
            {isValid ? (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ color: 'hsl(var(--primary))', fontWeight: 600, marginBottom: '0.5rem' }}>
                  ✓ Valid — ready to write
                </div>
                <button
                  onClick={handleApprove}
                  disabled={running}
                  style={{
                    padding: '0.5rem 1rem',
                    borderRadius: 'var(--radius)',
                    border: 'none',
                    background: 'hsl(var(--primary))',
                    color: 'hsl(var(--primary-foreground))',
                    cursor: running ? 'not-allowed' : 'pointer',
                    opacity: running ? 0.5 : 1,
                  }}
                >
                  {running ? 'Writing…' : 'Approve & Write'}
                </button>
              </div>
            ) : null}

            {validationErrors && validationErrors.length > 0 && (
              <div>
                <div style={{ color: 'hsl(var(--destructive))', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Validation errors:
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {validationErrors.map((err, i) => (
                    <li
                      key={i}
                      style={{
                        padding: '0.25rem 0',
                        fontSize: 13,
                        color: 'hsl(var(--foreground))',
                      }}
                    >
                      <strong>{err.code}</strong>
                      {err.step_id ? ` (${err.step_id})` : ''}
                      {err.detail ? ` — ${err.detail}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {written && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--radius)',
                  background: 'hsl(var(--primary) / 0.1)',
                  color: 'hsl(var(--primary))',
                  fontSize: 13,
                  marginTop: '0.5rem',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                  ✓ Written as {written.status}
                </div>
                <div>
                  Version: {written.version_label}
                  {written.soul_bumped ? ' (soul bumped)' : ''}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
