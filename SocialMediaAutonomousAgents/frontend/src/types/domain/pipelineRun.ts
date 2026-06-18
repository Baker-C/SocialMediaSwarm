// Materialized pipeline-run projection (mirrors backend app/models/pipeline_run.py).
import type { StepLink } from './stepOutput';

export type StepArtifact = {
  artifact: string;
  present: boolean;
  size_bytes?: number;
  truncated?: boolean;
  value?: unknown;
};

export type PipelineStepError = {
  type?: string;
  message?: string;
  traceback?: string;
  occurred_at?: string;
};

export type PipelineStepRecord = {
  step_id: string;
  scope: string; // orchestrator | runbook
  parent_id?: string | null;
  purpose?: string | null;
  status: string; // active | ok | skipped | error
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  inputs: StepArtifact[];
  outputs: StepArtifact[];
  skip_reason?: string | null;
  error?: PipelineStepError | null;
};

export type PipelineRun = {
  run_id: string;
  account_id: string;
  slot: string;
  mode: string;
  niche: string;
  status: string; // running | ok | skipped | rejected | error
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  step_count: number;
  steps: PipelineStepRecord[];
  summary?: Record<string, unknown>;
  step_links?: StepLink[];   // doc 08: ordered links to StepOutputDocument; empty when NATS-only
};
