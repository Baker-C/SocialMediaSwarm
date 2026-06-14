import type { CSSProperties } from 'react';
import {
  PIPELINE_FLOW_LANE_LABELS,
  PIPELINE_FLOW_LANE_ORDER,
  PIPELINE_FLOW_NODES,
  type FlowLayer,
} from '../../lib/pipeline/flowGraph';
import type { FlowNodeState } from '../../types/pipelineProgress';

type PipelineFlowDiagramProps = {
  nodeState: FlowNodeState;
  running: boolean;
  error: string | null;
};

const LANE_ACCENT: Record<FlowLayer, string> = {
  entry: '#a855f7',
  orchestrator: '#3b82f6',
  runbook: '#3b82f6',
  tools: '#f97316',
  persistence: '#22c55e',
  external: '#22c55e',
};

function nodesForLayer(layer: FlowLayer) {
  return PIPELINE_FLOW_NODES.filter((n) => n.layer === layer);
}

export function PipelineFlowDiagram({ nodeState, running, error }: PipelineFlowDiagramProps) {
  return (
    <div className="pipeline-flow" role="region" aria-label="Pipeline flow diagram">
      <div className="pipeline-flow__meta">
        <span
          className={`pipeline-flow__badge ${
            error ? 'pipeline-flow__badge--error' : running ? 'pipeline-flow__badge--running' : ''
          }`}
        >
          {error ? 'Error' : running ? 'Running' : 'Idle'}
        </span>
        {error ? (
          <p className="pipeline-flow__error" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <div className="pipeline-flow__lanes">
        {PIPELINE_FLOW_LANE_ORDER.map((layer) => {
          const nodes = nodesForLayer(layer);
          if (nodes.length === 0) {
            return null;
          }
          return (
            <section
              key={layer}
              className={`pipeline-flow__lane pipeline-flow__lane--${layer}`}
              style={{ '--lane-accent': LANE_ACCENT[layer] } as CSSProperties}
              aria-label={PIPELINE_FLOW_LANE_LABELS[layer]}
            >
              <h4 className="pipeline-flow__lane-title">{PIPELINE_FLOW_LANE_LABELS[layer]}</h4>
              <div className="pipeline-flow__lane-body">
                {nodes.map((node) => {
                  const status = nodeState[node.id] ?? 'pending';
                  return (
                    <div
                      key={node.id}
                      className={`pipeline-flow__node pipeline-flow__node--${status} ${
                        node.kind === 'satellite' ? 'pipeline-flow__node--satellite' : ''
                      }`}
                      aria-current={status === 'active' ? 'step' : undefined}
                    >
                      <span className="pipeline-flow__node-title">{node.label}</span>
                      {node.subtext ? (
                        <span className="pipeline-flow__node-sub">{node.subtext}</span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
