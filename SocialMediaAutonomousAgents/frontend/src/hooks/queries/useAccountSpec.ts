import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { fetchAccountSpec } from '../../api/endpoints/pipelineSpec';
import type { PipelineSpec } from '../../types/domain/pipelineSpec';

export function useAccountSpec(
  accountId: string | undefined,
  status: 'champion' | 'challenger' = 'champion',
  enabled = true
): UseQueryResult<PipelineSpec> {
  return useQuery({
    queryKey: ['accountSpec', accountId, status],
    queryFn: async () => {
      if (!accountId) throw new Error('accountId is required');
      return fetchAccountSpec(accountId, status);
    },
    enabled: enabled && !!accountId,
  });
}
