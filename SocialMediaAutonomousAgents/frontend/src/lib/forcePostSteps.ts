export type ForcePostStepStatus = 'pending' | 'active' | 'done' | 'error';

export type ForcePostStep = {
  stepId: string;
  label: string;
};

export const FORCE_POST_STEPS: ForcePostStep[] = [
  { stepId: 'start', label: 'Starting pipeline' },
  { stepId: 'load_account', label: 'Loading account' },
  { stepId: 'post_lock', label: 'Acquiring post lock' },
  { stepId: 'fetch_profile', label: 'Fetching profile' },
  { stepId: 'fetch_timeline', label: 'Fetching timeline references' },
  { stepId: 'rank_references', label: 'Ranking references' },
  { stepId: 'compose', label: 'Composing post' },
  { stepId: 'safety', label: 'Safety review' },
  { stepId: 'publish', label: 'Publishing to X' },
  { stepId: 'complete', label: 'Done' },
];

export type ForcePostProgressEvent = {
  type: 'progress';
  step_id: string;
  label: string;
  status: 'active' | 'done' | 'error';
};

export type ForcePostCompleteEvent = {
  type: 'complete';
  result: unknown;
  failure?: string | null;
};

export type ForcePostErrorEvent = {
  type: 'error';
  message: string;
};

export type ForcePostStreamEvent =
  | ForcePostProgressEvent
  | ForcePostCompleteEvent
  | ForcePostErrorEvent;

export function initialForcePostStepStatuses(): Record<string, ForcePostStepStatus> {
  return Object.fromEntries(FORCE_POST_STEPS.map((s) => [s.stepId, 'pending']));
}

const PIPELINE_ERROR_LABELS: Record<string, string> = {
  account_not_found: 'Account not found in the database.',
  already_posted_this_interval: 'This account already posted in the current interval.',
  inactive_account: 'Account is inactive.',
  no_oauth_tokens: 'X is not connected. Connect OAuth first.',
  reauth_required: 'X session expired. Reconnect OAuth.',
  account_post_lock_held: 'Another post is already in progress for this account.',
  ravendb_post_lock_held: 'Another post lock is held in the database.',
  slot_lock_held: 'This interval slot is locked by another process.',
  slot_claim_lost: 'Lost the race to claim this interval slot.',
  no_reference_with_urls: 'No usable reference tweets with URLs were found.',
  all_references_already_copied: 'All timeline references were already used recently.',
  all_compose_attempts_failed: 'Could not compose an acceptable post.',
  safety_rejected: 'Post failed safety review.',
};

export function formatPipelineError(codeOrMessage: string): string {
  const trimmed = codeOrMessage.trim();
  if (!trimmed) {
    return 'Force post failed.';
  }
  if (PIPELINE_ERROR_LABELS[trimmed]) {
    return PIPELINE_ERROR_LABELS[trimmed];
  }
  const cooldownMatch = /^posted_within_cooldown_(\d+)m$/.exec(trimmed);
  if (cooldownMatch) {
    return `Post cooldown is still active (${cooldownMatch[1]} minutes).`;
  }
  return trimmed.replace(/_/g, ' ');
}

export function extractPipelineFailure(result: unknown): string | null {
  if (!result || typeof result !== 'object') {
    return null;
  }
  const root = result as Record<string, unknown>;
  const rows = Array.isArray(root.results) ? root.results : [root];
  for (const row of rows) {
    if (!row || typeof row !== 'object') {
      continue;
    }
    const entry = row as Record<string, unknown>;
    if (typeof entry.skipped === 'string' && entry.skipped.trim()) {
      return entry.skipped.trim();
    }
    if (typeof entry.rejected === 'string' && entry.rejected.trim()) {
      return entry.rejected.trim();
    }
    if (typeof entry.error === 'string' && entry.error.trim()) {
      return entry.error.trim();
    }
  }
  return null;
}

export function splitStepErrorLabel(label: string): { title: string; detail: string | null } {
  const idx = label.indexOf(': ');
  if (idx === -1) {
    return { title: label, detail: null };
  }
  return {
    title: label.slice(0, idx),
    detail: label.slice(idx + 2).trim() || null,
  };
}

export function extractPostedText(result: unknown): string | null {
  if (!result || typeof result !== 'object') {
    return null;
  }
  const root = result as Record<string, unknown>;
  const rows = Array.isArray(root.results) ? root.results : [root];
  for (const row of rows) {
    if (!row || typeof row !== 'object') {
      continue;
    }
    const tweet = (row as Record<string, unknown>).tweet;
    if (tweet && typeof tweet === 'object') {
      const text = (tweet as Record<string, unknown>).text;
      if (typeof text === 'string' && text.trim()) {
        return text.trim();
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// In-memory force-post run history (local state only, not persisted)
// ---------------------------------------------------------------------------

export type ForcePostRunOutcome = 'running' | 'success' | 'error';

export type ForcePostStepRecord = {
  stepId: string;
  label: string;
  status: ForcePostStepStatus;
  startedAt: number | null;
  endedAt: number | null;
  durationMs: number | null;
};

export type ForcePostRun = {
  id: string;
  accountId: string;
  startedAt: number;
  endedAt: number | null;
  outcome: ForcePostRunOutcome;
  error: string | null;
  postedText: string | null;
  steps: ForcePostStepRecord[];
};

export const FORCE_POST_HISTORY_LIMIT = 25;

export function createForcePostRun(accountId: string): ForcePostRun {
  const now = Date.now();
  return {
    id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
    accountId,
    startedAt: now,
    endedAt: null,
    outcome: 'running',
    error: null,
    postedText: null,
    steps: FORCE_POST_STEPS.map((s) => ({
      stepId: s.stepId,
      label: s.label,
      status: 'pending' as ForcePostStepStatus,
      startedAt: null,
      endedAt: null,
      durationMs: null,
    })),
  };
}

export function applyProgressToRun(
  run: ForcePostRun,
  stepId: string,
  status: 'active' | 'done' | 'error',
  label: string,
  at: number = Date.now()
): ForcePostRun {
  const steps = run.steps.map((s) => ({ ...s }));
  const index = steps.findIndex((s) => s.stepId === stepId);
  if (index === -1) {
    return run;
  }
  const target = steps[index];
  if (label) {
    target.label = label;
  }

  if (status === 'active') {
    for (let i = 0; i < index; i += 1) {
      const s = steps[i];
      if (s.status === 'pending' || s.status === 'active') {
        s.status = 'done';
        if (s.startedAt == null) {
          s.startedAt = at;
        }
        s.endedAt = at;
        s.durationMs = at - s.startedAt;
      }
    }
    target.status = 'active';
    if (target.startedAt == null) {
      target.startedAt = at;
    }
    target.endedAt = null;
    target.durationMs = null;
  } else if (status === 'done') {
    target.status = 'done';
    if (target.startedAt == null) {
      target.startedAt = at;
    }
    target.endedAt = at;
    target.durationMs = at - target.startedAt;
  } else {
    target.status = 'error';
    if (target.startedAt == null) {
      target.startedAt = at;
    }
    target.endedAt = at;
    target.durationMs = at - target.startedAt;
    for (const s of steps) {
      if (s.stepId !== stepId && s.status === 'active') {
        s.status = 'pending';
      }
    }
  }

  return { ...run, steps };
}

export function finalizeForcePostRun(
  run: ForcePostRun,
  outcome: 'success' | 'error',
  options?: { error?: string | null; postedText?: string | null; at?: number }
): ForcePostRun {
  const at = options?.at ?? Date.now();
  const steps = run.steps.map((s) => {
    if (s.status !== 'active') {
      return s;
    }
    if (outcome === 'success') {
      const startedAt = s.startedAt ?? at;
      return { ...s, status: 'done' as ForcePostStepStatus, startedAt, endedAt: at, durationMs: at - startedAt };
    }
    return { ...s, status: 'pending' as ForcePostStepStatus };
  });
  return {
    ...run,
    steps,
    outcome,
    endedAt: at,
    error: options?.error ?? run.error,
    postedText: options?.postedText ?? run.postedText,
  };
}

export function stepDurationMs(step: ForcePostStepRecord, now: number): number | null {
  if (step.durationMs != null) {
    return step.durationMs;
  }
  if (step.status === 'active' && step.startedAt != null) {
    return now - step.startedAt;
  }
  return null;
}

export function runDurationMs(run: ForcePostRun, now: number): number {
  return (run.endedAt ?? now) - run.startedAt;
}

export function formatDuration(ms: number | null): string {
  if (ms == null || ms < 0) {
    return '';
  }
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatClockTime(epochMs: number): string {
  try {
    return new Date(epochMs).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '';
  }
}
