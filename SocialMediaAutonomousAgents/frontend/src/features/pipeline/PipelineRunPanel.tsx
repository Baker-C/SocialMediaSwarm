import { useCallback, useMemo, useState } from 'react';
import { useAppContext } from '../../app/AppContext';
import { usePipelineRunStream } from '../../hooks/usePipelineRunStream';
import { useAccountSpec } from '../../hooks/queries/useAccountSpec';
import { applyFlowProgress, initialFlowState } from '../../lib/pipeline/flowReducer';
import { sectionStepIds } from '../../lib/pipeline/flowGraph';
import { flowFromSpec } from '../../lib/pipeline/specToFlow';
import type { FlowNodeState } from '../../types/pipelineProgress';
import { PipelineFlowDiagram } from './PipelineFlowDiagram';

type PipelineRunPanelProps = {
  accountId?: string;
  onComplete?: () => void;
};

export function PipelineRunPanel({ accountId, onComplete }: PipelineRunPanelProps) {
  const { apiBase } = useAppContext();

  // The live view is built from this account's pipeline spec.
  const specQuery = useAccountSpec(accountId, 'champion');
  const spec = specQuery.data;
  const sections = useMemo(() => (spec ? flowFromSpec(spec) : []), [spec]);
  const stepIds = useMemo(() => sectionStepIds(sections), [sections]);
  const validIds = useMemo(() => new Set(stepIds), [stepIds]);

  const [nodeState, setNodeState] = useState<FlowNodeState>({});

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
            disabled={running || !accountId.trim() || !spec}
          >
            {running ? 'Running…' : 'Run pipeline'}
          </button>
        ) : (
          <p className="page-hint">Open an account to watch live flow.</p>
        )}
      </div>
      {accountId ? (
        specQuery.isLoading ? (
          <p className="page-hint">Loading pipeline…</p>
        ) : specQuery.error ? (
          <p className="page-hint">Failed to load pipeline spec.</p>
        ) : spec ? (
          <PipelineFlowDiagram
            nodeState={nodeState}
            running={running}
            error={error}
            sections={sections}
          />
        ) : null
      ) : null}
    </>
  );
}
