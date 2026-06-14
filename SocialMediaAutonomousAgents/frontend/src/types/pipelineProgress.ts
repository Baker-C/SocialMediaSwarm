export type FlowNodeStatus = 'pending' | 'active' | 'done' | 'error';

export type FlowNodeState = Record<string, FlowNodeStatus>;

export type PipelineProgressStatus = 'active' | 'done' | 'error';

export type PipelineProgressScope = 'orchestrator' | 'runbook';

export type PipelineProgressPayload = {
  step_id: string;
  label: string;
  status: PipelineProgressStatus;
  scope?: PipelineProgressScope;
  parent_id?: string | null;
  purpose?: string | null;
};

export type PipelineRunCompletePayload = {
  type: 'complete';
  result: unknown;
  failure?: string | null;
};

export type PipelineRunErrorPayload = {
  type: 'error';
  message: string;
};

export type PipelineRunStreamEvent =
  | ({ type: 'progress' } & PipelineProgressPayload)
  | PipelineRunCompletePayload
  | PipelineRunErrorPayload;
