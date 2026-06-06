import type { ForcePostRun, ForcePostRunOutcome } from '../lib/forcePostSteps';
import { formatClockTime, formatDuration, runDurationMs } from '../lib/forcePostSteps';
import { ForcePostTracker } from './ForcePostTracker';

type ForcePostHistoryProps = {
  runs: ForcePostRun[];
  now: number;
};

const OUTCOME_LABELS: Record<ForcePostRunOutcome, string> = {
  running: 'Running',
  success: 'Posted',
  error: 'Failed',
};

function OutcomeBadge({ outcome }: { outcome: ForcePostRunOutcome }) {
  return (
    <span className={`force-post-run__badge force-post-run__badge--${outcome}`}>
      {OUTCOME_LABELS[outcome]}
    </span>
  );
}

export function ForcePostHistory({ runs, now }: ForcePostHistoryProps) {
  if (runs.length === 0) {
    return null;
  }
  return (
    <div className="force-post-history" aria-label="Force post history">
      <h3 className="force-post-history__title">Recent runs</h3>
      <ol className="force-post-history__list">
        {runs.map((run) => {
          const total = formatDuration(runDurationMs(run, now));
          return (
            <li key={run.id} className={`force-post-run force-post-run--${run.outcome}`}>
              <div className="force-post-run__header">
                <OutcomeBadge outcome={run.outcome} />
                <span className="force-post-run__account">{run.accountId}</span>
                <span className="force-post-run__meta">
                  {formatClockTime(run.startedAt)}
                  {total ? ` · ${total}` : ''}
                </span>
              </div>
              <ForcePostTracker steps={run.steps} now={now} />
              {run.postedText ? (
                <p className="force-post-run__posted">{run.postedText}</p>
              ) : null}
              {run.outcome === 'error' && run.error ? (
                <p className="force-post-run__error" role="alert">
                  {run.error}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
