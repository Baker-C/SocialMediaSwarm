import { useQuery } from '@tanstack/react-query';
import { fetchAccountPipelineRuns } from '../../api/endpoints/pipelineRuns';

// Latest pipeline run for an account (the run behind the most recent post).
export function useLatestPipelineRun(accountId: string | undefined) {
  return useQuery({
    queryKey: ['pipelineRuns', accountId, 'latest'],
    queryFn: () => fetchAccountPipelineRuns(accountId!, 1),
    enabled: Boolean(accountId),
    // A run that's still in-flight should refresh so steps fill in live-ish.
    refetchInterval: (query) => {
      const run = query.state.data?.runs?.[0];
      return run && run.status === 'running' ? 4000 : false;
    },
  });
}
