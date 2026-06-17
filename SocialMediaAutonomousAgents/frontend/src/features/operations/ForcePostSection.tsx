import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ForcePostHistory } from '../../components/ForcePostHistory';
import { usePipelineRunStream } from '../../hooks/usePipelineRunStream';
import { toLinearStepId } from '../../lib/pipeline/linearProjection';
import type { ForcePostRun } from '../../lib/forcePostSteps';
import {
  applyProgressToRun,
  createForcePostRun,
  extractPipelineFailure,
  extractPostedText,
  finalizeForcePostRun,
  formatPipelineError,
  FORCE_POST_HISTORY_LIMIT,
} from '../../lib/forcePostSteps';
import type { AccountSummary } from '../../types';

type ForcePostSectionProps = {
  apiBase: string;
  accounts: AccountSummary[];
  onComplete?: () => void;
};

function errorFromProgressLabel(label: string): string {
  const idx = label.indexOf(': ');
  const code = idx === -1 ? label : label.slice(idx + 2);
  return formatPipelineError(code);
}

export function ForcePostSection({ apiBase, accounts, onComplete }: ForcePostSectionProps) {
  const activeAccounts = useMemo(
    () => accounts.filter((a) => a.status === 'active'),
    [accounts]
  );
  const [accountId, setAccountId] = useState('');
  const [history, setHistory] = useState<ForcePostRun[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const activeRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!accountId && activeAccounts.length > 0) {
      setAccountId(activeAccounts[0].account_id);
    }
  }, [accountId, activeAccounts]);

  const updateActiveRun = useCallback((updater: (run: ForcePostRun) => ForcePostRun) => {
    const id = activeRunIdRef.current;
    if (!id) {
      return;
    }
    setHistory((prev) => prev.map((run) => (run.id === id ? updater(run) : run)));
  }, []);

  const handleProgress = useCallback(
    (event: { step_id: string; label: string; status: 'active' | 'done' | 'error' }) => {
      const linearId = toLinearStepId(event.step_id);
      if (!linearId) {
        return;
      }
      updateActiveRun((r) => applyProgressToRun(r, linearId, event.status, event.label));
      if (event.status === 'error') {
        updateActiveRun((r) => ({ ...r, error: errorFromProgressLabel(event.label) }));
      }
    },
    [updateActiveRun]
  );

  const handleRunComplete = useCallback(
    (result: unknown, failure: string | null) => {
      const resolvedFailure =
        (typeof failure === 'string' && failure.trim()) || extractPipelineFailure(result);
      if (resolvedFailure) {
        updateActiveRun((r) =>
          finalizeForcePostRun(r, 'error', { error: formatPipelineError(resolvedFailure) })
        );
      } else {
        updateActiveRun((r) =>
          finalizeForcePostRun(r, 'success', { postedText: extractPostedText(result) })
        );
        onComplete?.();
      }
      setNow(Date.now());
    },
    [onComplete, updateActiveRun]
  );

  const { running, run, abort } = usePipelineRunStream({
    apiBase,
    accountId,
    onProgress: handleProgress,
    onComplete: handleRunComplete,
  });

  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    return () => abort();
  }, [abort]);

  const handleForcePost = useCallback(async () => {
    const aid = accountId.trim();
    if (!aid || running) {
      return;
    }

    const runRecord = createForcePostRun(aid);
    activeRunIdRef.current = runRecord.id;
    setHistory((prev) => [runRecord, ...prev].slice(0, FORCE_POST_HISTORY_LIMIT));
    setNow(Date.now());
    await run();
    activeRunIdRef.current = null;
  }, [accountId, running, run]);

  const canRun = Boolean(accountId.trim()) && !running && activeAccounts.length > 0;

  return (
    <section className="force-post-section" aria-label="Force post">
      <h2 className="accounts-section__title">Force post</h2>
      <p className="force-post-section__hint">
        Run the full posting pipeline immediately for one active account (bypasses cooldown).
      </p>
      {activeAccounts.length === 0 ? (
        <p className="accounts-section__empty">No active accounts available for force post.</p>
      ) : (
        <div className="force-post-section__controls">
          <label className="force-post-section__field">
            Account
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              disabled={running}
            >
              {activeAccounts.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.account_id} · {a.category}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="force-post-section__btn"
            onClick={() => void handleForcePost()}
            disabled={!canRun}
          >
            {running ? 'Running…' : 'Force post'}
          </button>
        </div>
      )}
      <ForcePostHistory runs={history} now={now} />
    </section>
  );
}
