import { PIPELINE_FLOW_STEP_IDS } from './flowGraph';
import type { FlowNodeState, PipelineProgressPayload } from '../../types/pipelineProgress';

// Default known-id set (the static fallback graph). Callers that render a
// per-account spec pass their own id set so live progress lights up the spec's
// actual steps (e.g. compose_until_safe / publish_post) instead of these.
const DEFAULT_STEP_NODE_IDS = new Set(PIPELINE_FLOW_STEP_IDS);

export function initialFlowState(stepIds: readonly string[] = PIPELINE_FLOW_STEP_IDS): FlowNodeState {
  return Object.fromEntries(stepIds.map((id) => [id, 'pending']));
}

export function applyFlowProgress(
  state: FlowNodeState,
  event: PipelineProgressPayload,
  validIds: ReadonlySet<string> = DEFAULT_STEP_NODE_IDS
): FlowNodeState {
  if (!validIds.has(event.step_id)) {
    return state;
  }
  const next: FlowNodeState = { ...state };
  next[event.step_id] = event.status === 'active' ? 'active' : event.status === 'done' ? 'done' : 'error';
  return next;
}

export function resetFlowState(stepIds?: readonly string[]): FlowNodeState {
  return initialFlowState(stepIds);
}
