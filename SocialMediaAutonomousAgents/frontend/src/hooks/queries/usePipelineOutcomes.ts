import { useQuery } from '@tanstack/react-query';
import {
  fetchAccountPipelineOutcomes,
  fetchFleetPipelineOutcomes,
} from '../../api/endpoints/pipeline';
import type { PipelineFilterParams } from '../../types';

export function usePipelineOutcomes(
  accountId: string | undefined,
  filters?: PipelineFilterParams
) {
  return useQuery({
    queryKey: ['pipelineOutcomes', accountId, filters],
    queryFn: () => fetchAccountPipelineOutcomes(accountId!, filters),
    enabled: Boolean(accountId),
  });
}

export function useFleetPipelineOutcomes(filters?: PipelineFilterParams) {
  return useQuery({
    queryKey: ['pipelineOutcomes', 'fleet', filters],
    queryFn: () => fetchFleetPipelineOutcomes(filters),
  });
}
