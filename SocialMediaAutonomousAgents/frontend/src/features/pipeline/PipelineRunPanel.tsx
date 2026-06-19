import { useCallback, useMemo, useState } from 'react';
import { useAppContext } from '../../app/AppContext';
import { usePipelineRunStream } from '../../hooks/usePipelineRunStream';
import { useAccountSpec } from '../../hooks/queries/useAccountSpec';
import { applyFlowProgress, initialFlowState } from '../../lib/pipeline/flowReducer';
import { PIPELINE_FLOW, sectionStepIds } from '../../lib/pipeline/flowGraph';
import { flowFromSpec } from '../../lib/pipeline/specToFlow';
import type { FlowNodeState } from '../../types/pipelineProgress';
import { PipelineFlowDiagram } from './PipelineFlowDiagram';

type PipelineRunPanelProps = {
  accountId?: string;
  onComplete?: () => void;
};

export function PipelineRunPanel({ accountId, onComplete }: PipelineRunPanelProps) {
  const { apiBase } = useAppContext();

  // Render this account's actual pipeline spec; fall back to the static graph
  // until the spec loads (or when no account is open).
  const specQuery = useAccountSpec(accountId, 'champion');
  const sections = useMemo(
    () => (specQuery.data ? flowFromSpec(specQuery.data) : PIPELINE_FLOW),
    [specQuery.data]
  );
  const stepIds = useMemo(() => sectionStepIds(sections), [sections]);
  const validIds = useMemo(() => new Set(stepIds), [stepIds]);

  const [nodeState, setNodeState] = useState<FlowNodeState>(() => initialFlowState());

  const handleProgress = useCallback(
    (event: Parameters<typeof applyFlowProgress>[1]) => {
      setNodeState((prev) => applyFlowProgress(prev, event, validIds));
    },
    [validIds]
  );

  const handleComplete = useCallback(
    (_result: unknown, failure: string | null) => {
      if (!failure) {
        onComplete?.();
      }
    },
    [onComplete]
  );

  const { running, error, run } = usePipelineRunStream({
    apiBase,
    accountId: accountId ?? '',
    onProgress: handleProgress,
    onComplete: handleComplete,
  });

  const handleRun = useCallback(() => {
    setNodeState(initialFlowState(stepIds));
    void run();
  }, [run, stepIds]);

  return (
    <>
      <div className="pipeline-flow-panel__header">
        <h3 className="hq-panel__title">Pipeline flow</h3>
        {accountId ? (
          <button
            type="button"
            className="force-post-section__btn"
            onClick={handleRun}
            disabled={running || !accountId.trim()}
          >
            {running ? 'Running…' : 'Run pipeline'}
          </button>
        ) : (
          <p className="page-hint">Open an account to watch live flow.</p>
        )}
      </div>
      <PipelineFlowDiagram nodeState={nodeState} running={running} error={error} sections={sections} />
    </>
  );
}
