import type { FlowNodeState, PipelineProgressPayload } from '../../types/pipelineProgress';

// The valid step-id set is derived per-account from the rendered spec
// (sectionStepIds), so live progress lights up exactly that account's steps.
export function initialFlowState(stepIds: readonly string[]): FlowNodeState {
  return Object.fromEntries(stepIds.map((id) => [id, 'pending']));
}

export function applyFlowProgress(
  state: FlowNodeState,
  event: PipelineProgressPayload,
  validIds: ReadonlySet<string>
): FlowNodeState {
  if (!validIds.has(event.step_id)) {
    return state;
  }
  const next: FlowNodeState = { ...state };
  next[event.step_id] = event.status === 'active' ? 'active' : event.status === 'done' ? 'done' : 'error';
  return next;
}

export function resetFlowState(stepIds: readonly string[]): FlowNodeState {
  return initialFlowState(stepIds);
}
