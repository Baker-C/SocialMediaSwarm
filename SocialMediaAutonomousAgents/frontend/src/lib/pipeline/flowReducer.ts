import {
  PIPELINE_FLOW_NODE_IDS,
  PIPELINE_FLOW_NODES,
  type FlowNodeDef,
} from './flowGraph';
import type { FlowNodeState, FlowNodeStatus, PipelineProgressPayload } from '../../types/pipelineProgress';

const STEP_NODE_IDS = new Set(
  PIPELINE_FLOW_NODES.filter((n) => n.kind !== 'satellite').map((n) => n.id)
);

const SATELLITE_NODES = PIPELINE_FLOW_NODES.filter((n) => n.kind === 'satellite');

export function initialFlowState(): FlowNodeState {
  return Object.fromEntries(PIPELINE_FLOW_NODE_IDS.map((id) => [id, 'pending']));
}

function resolveStepNodeId(stepId: string): string | null {
  if (STEP_NODE_IDS.has(stepId)) {
    return stepId;
  }
  return null;
}

function satelliteStatus(node: FlowNodeDef, stepState: FlowNodeState): FlowNodeStatus {
  const watched = node.watchSteps ?? [];
  if (watched.some((id) => stepState[id] === 'error')) {
    return 'error';
  }
  if (watched.some((id) => stepState[id] === 'active')) {
    return 'active';
  }
  if (watched.length > 0 && watched.every((id) => stepState[id] === 'done')) {
    return 'done';
  }
  return 'pending';
}

function applySatellites(state: FlowNodeState): FlowNodeState {
  const next = { ...state };
  for (const node of SATELLITE_NODES) {
    next[node.id] = satelliteStatus(node, next);
  }
  return next;
}

export function applyFlowProgress(
  state: FlowNodeState,
  event: PipelineProgressPayload
): FlowNodeState {
  const nodeId = resolveStepNodeId(event.step_id);
  if (!nodeId) {
    return state;
  }

  const next: FlowNodeState = { ...state };

  if (event.status === 'active') {
    next[nodeId] = 'active';
  } else if (event.status === 'done') {
    next[nodeId] = 'done';
  } else {
    next[nodeId] = 'error';
  }

  return applySatellites(next);
}

export function resetFlowState(): FlowNodeState {
  return initialFlowState();
}
