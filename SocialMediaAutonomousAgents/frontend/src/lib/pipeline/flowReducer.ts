import { PIPELINE_FLOW_STEP_IDS } from './flowGraph';
import type { FlowNodeState, PipelineProgressPayload } from '../../types/pipelineProgress';

const STEP_NODE_IDS = new Set(PIPELINE_FLOW_STEP_IDS);

export function initialFlowState(): FlowNodeState {
  return Object.fromEntries(PIPELINE_FLOW_STEP_IDS.map((id) => [id, 'pending']));
}

export function applyFlowProgress(
  state: FlowNodeState,
  event: PipelineProgressPayload
): FlowNodeState {
  if (!STEP_NODE_IDS.has(event.step_id)) {
    return state;
  }
  const next: FlowNodeState = { ...state };
  next[event.step_id] = event.status === 'active' ? 'active' : event.status === 'done' ? 'done' : 'error';
  return next;
}

export function resetFlowState(): FlowNodeState {
  return initialFlowState();
}
