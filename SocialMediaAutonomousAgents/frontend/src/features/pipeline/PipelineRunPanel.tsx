import { useCallback, useState } from 'react';
import { useAppContext } from '../../app/AppContext';
import { usePipelineRunStream } from '../../hooks/usePipelineRunStream';
import { applyFlowProgress, initialFlowState } from '../../lib/pipeline/flowReducer';
import type { FlowNodeState } from '../../types/pipelineProgress';
import { PipelineFlowDiagram } from './PipelineFlowDiagram';

type PipelineRunPanelProps = {
  accountId?: string;
  onComplete?: () => void;
};

export function PipelineRunPanel({ accountId, onComplete }: PipelineRunPanelProps) {
  const { apiBase } = useAppContext();
  const [nodeState, setNodeState] = useState<FlowNodeState>(initialFlowState);

  const handleProgress = useCallback((event: Parameters<typeof applyFlowProgress>[1]) => {
    setNodeState((prev) => applyFlowProgress(prev, event));
  }, []);

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
    setNodeState(initialFlowState());
    void run();
  }, [run]);

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
      <PipelineFlowDiagram nodeState={nodeState} running={running} error={error} />
    </>
  );
}
