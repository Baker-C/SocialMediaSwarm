export type PipelineOutcome = {
  account_id: string;
  phase: string;
  status: string;
  created_at: string;
  reason?: string | null;
  details?: Record<string, unknown>;
};

export type VoiceRevision = {
  account_id: string;
  seq: number;
  label: string;
  version_hash: string;
  changed_at: string;
};
