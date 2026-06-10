import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ForcePostHistory } from '../../components/ForcePostHistory';
import { streamForcePost } from '../../lib/api';
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
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<ForcePostRun[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const abortRef = useRef<AbortController | null>(null);
  const activeRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!accountId && activeAccounts.length > 0) {
      setAccountId(activeAccounts[0].account_id);
    }
  }, [accountId, activeAccounts]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [running]);

  const updateActiveRun = useCallback((updater: (run: ForcePostRun) => ForcePostRun) => {
    const id = activeRunIdRef.current;
    if (!id) {
      return;
    }
    setHistory((prev) => prev.map((run) => (run.id === id ? updater(run) : run)));
  }, []);

  const handleForcePost = useCallback(async () => {
    const aid = accountId.trim();
    if (!aid || running) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const run = createForcePostRun(aid);
    activeRunIdRef.current = run.id;
    setHistory((prev) => [run, ...prev].slice(0, FORCE_POST_HISTORY_LIMIT));
    setNow(Date.now());
    setRunning(true);

    let finalized = false;
    const finalize = (
      outcome: 'success' | 'error',
      options?: { error?: string | null; postedText?: string | null }
    ) => {
      if (finalized) {
        return;
      }
      finalized = true;
      updateActiveRun((r) => finalizeForcePostRun(r, outcome, options));
    };

    try {
      await streamForcePost(
        apiBase,
        aid,
        (event) => {
          if (event.type === 'progress') {
            updateActiveRun((r) => applyProgressToRun(r, event.step_id, event.status, event.label));
            if (event.status === 'error') {
              updateActiveRun((r) => ({ ...r, error: errorFromProgressLabel(event.label) }));
            }
          } else if (event.type === 'error') {
            finalize('error', { error: formatPipelineError(event.message) });
          } else if (event.type === 'complete') {
            const failure =
              (typeof event.failure === 'string' && event.failure.trim()) ||
              extractPipelineFailure(event.result);
            if (failure) {
              finalize('error', { error: formatPipelineError(failure) });
            } else {
              finalize('success', { postedText: extractPostedText(event.result) });
            }
            onComplete?.();
          }
        },
        controller.signal
      );
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      const message = err instanceof Error ? err.message : 'Force post failed';
      finalize('error', { error: formatPipelineError(message) });
    } finally {
      if (abortRef.current === controller) {
        if (!finalized) {
          finalize('error', { error: 'Force post ended unexpectedly.' });
        }
        setNow(Date.now());
        setRunning(false);
        abortRef.current = null;
        activeRunIdRef.current = null;
      }
    }
  }, [accountId, running, apiBase, onComplete, updateActiveRun]);

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
                  {a.account_id} · {a.niche}
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
