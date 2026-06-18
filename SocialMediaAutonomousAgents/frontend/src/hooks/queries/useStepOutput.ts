import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { fetchStepOutput } from '../../api/endpoints/stepOutputs';
import type { StepOutputDocument } from '../../types/domain/stepOutput';

export function useStepOutput(
  runId: string | undefined,
  stepId: string | undefined,
  enabled = true
): UseQueryResult<StepOutputDocument> {
  return useQuery({
    queryKey: ['stepOutput', runId, stepId],
    queryFn: async () => {
      if (!runId || !stepId) throw new Error('runId and stepId are required');
      return fetchStepOutput(runId, stepId);
    },
    enabled: enabled && !!runId && !!stepId,
  });
}
