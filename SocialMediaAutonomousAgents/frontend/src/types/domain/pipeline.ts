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
  // soul snapshot (Task 02)
  personality?: string;
  posting_prompt?: string;
  contrast_patterns?: { text: string; correlation: 'positive' | 'negative' }[];
  punctuation_rules?: { pattern: string; replacement: string | null }[];
  // legacy (older revisions) — kept optional for graceful display
  system_prompt?: string;
  negative_semantics?: string[];
};
