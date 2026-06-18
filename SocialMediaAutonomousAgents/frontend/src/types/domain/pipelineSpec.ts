// Mirror of backend app/models/pipeline_spec.py (doc 04). Read-only on the frontend.
export type SpecStep = {
  kind: 'step';
  id: string;
  tool_id: string;
  reads: string[];          // ArtifactKey .value strings
  writes: string[];
  reads_optional?: string[];
  config?: Record<string, unknown>;
  purpose?: string;
};

export type SpecComposite = {
  kind: 'parallel' | 'chain';
  id: string;
  children: SpecNode[];
  purpose?: string;
};

export type SpecNode = SpecStep | SpecComposite;

export type PipelineSpec = {
  account_id: string;
  steps: SpecNode[];
  status: 'champion' | 'challenger';
  parent_hash?: string | null;
  version_hash?: string | null;
  version_seq?: number;
  version_label?: string | null;
};

export const isComposite = (n: SpecNode): n is SpecComposite =>
  n.kind === 'parallel' || n.kind === 'chain';
