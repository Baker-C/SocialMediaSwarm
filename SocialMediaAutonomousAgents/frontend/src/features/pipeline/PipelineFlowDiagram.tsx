/* ────────────────────────────────────────────────────────────────────────────
 * ⚠️  KEEP IN SYNC WITH THE BACKEND RUNBOOK.
 *
 * This component renders the post-tick pipeline defined in
 *   backend/app/pipeline/runbooks/post_tick.py  (POST_TICK_REFERENCE_STEPS).
 * The flow it draws comes from ./lib/pipeline/flowGraph.ts, which mirrors that
 * runbook step-for-step. If you change the runbook, update flowGraph.ts (and
 * therefore this display); if you change the display, make sure it still matches
 * the runbook. One should never drift from the other.
 * ──────────────────────────────────────────────────────────────────────────── */
import { Fragment } from 'react';
import {
  EXTERNAL_LABELS,
  PIPELINE_FLOW,
  type FlowNodeDef,
  type FlowRow,
} from '../../lib/pipeline/flowGraph';
import type { FlowNodeState, FlowNodeStatus } from '../../types/pipelineProgress';

type PipelineFlowDiagramProps = {
  nodeState: FlowNodeState;
  running: boolean;
  error: string | null;
};

function statusOf(nodeState: FlowNodeState, id: string): FlowNodeStatus {
  return nodeState[id] ?? 'pending';
}

function NodeCard({ node, status }: { node: FlowNodeDef; status: FlowNodeStatus }) {
  return (
    <div
      className={`pflow-node pflow-node--${status}`}
      aria-current={status === 'active' ? 'step' : undefined}
    >
      <span className="pflow-node__title">{node.label}</span>
      {node.subtext ? <span className="pflow-node__sub">{node.subtext}</span> : null}
      {node.external ? (
        <span className={`pflow-node__ext pflow-node__ext--${status}`}>
          {EXTERNAL_LABELS[node.external]}
        </span>
      ) : null}
    </div>
  );
}

const Arrow = () => <div className="pflow-arrow" aria-hidden="true" />;

function Row({ row, nodeState }: { row: FlowRow; nodeState: FlowNodeState }) {
  if (row.type === 'step') {
    return <NodeCard node={row.node} status={statusOf(nodeState, row.node.id)} />;
  }
  return (
    <div className="pflow-parallel">
      <div className="pflow-parallel__head">
        <span className="pflow-parallel__badge">∥ parallel</span>
        <span className="pflow-parallel__note">{row.note}</span>
      </div>
      <div className="pflow-parallel__branches">
        {row.branches.map((branch) => (
          <div key={branch.id} className="pflow-branch">
            <span className="pflow-branch__label">{branch.label}</span>
            {branch.steps.map((step, i) => (
              <Fragment key={step.id}>
                {i > 0 ? <Arrow /> : null}
                <NodeCard node={step} status={statusOf(nodeState, step.id)} />
              </Fragment>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
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

      <div className="pflow">
        {PIPELINE_FLOW.map((section, sIdx) => (
          <Fragment key={section.id}>
            {sIdx > 0 ? <Arrow /> : null}
            <section
              className={`pflow-section ${section.label ? 'pflow-section--labelled' : ''}`}
              aria-label={section.label}
            >
              {section.label ? <h4 className="pflow-section__label">{section.label}</h4> : null}
              {section.rows.map((row, rIdx) => (
                <Fragment key={row.type === 'step' ? row.node.id : row.id}>
                  {rIdx > 0 ? <Arrow /> : null}
                  <Row row={row} nodeState={nodeState} />
                </Fragment>
              ))}
            </section>
          </Fragment>
        ))}
      </div>
    </div>
  );
}
