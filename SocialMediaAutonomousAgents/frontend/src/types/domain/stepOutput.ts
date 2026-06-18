// Mirror of backend app/models/step_output.py (doc 08).
export type StepOutputArtifact = {
  artifact: string;         // ArtifactKey.value
  present: boolean;
  size_bytes?: number | null;
  value?: unknown;          // FULL untruncated payload; absent only when present=false
};

export type StepOutputDocument = {
  run_id: string;
  account_id: string;
  step_id: string;          // dotted flat id
  scope: string;            // runbook | orchestrator
  parent_id?: string | null;
  purpose?: string | null;
  seq: number;
  status: string;           // ok | skipped | error
  skip_reason?: string | null;
  error?: { type?: string; message?: string; traceback?: string } | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  inputs: StepOutputArtifact[];
  outputs: StepOutputArtifact[];
  result_payload?: Record<string, unknown>;
};

export type StepLink = {
  step_id: string;
  scope: string;
  seq: number;
  status: string;
  duration_ms?: number | null;
  doc_id: string;           // stepoutputs/{run_id}/{step_id}
};
