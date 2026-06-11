import { useQuery } from '@tanstack/react-query';
import { fetchAccountMetricsDoc } from '../../api/endpoints/accountMetrics';

export function useAccountMetrics(accountId: string | undefined) {
  return useQuery({
    queryKey: ['accountMetrics', accountId],
    queryFn: () => fetchAccountMetricsDoc(accountId!),
    enabled: Boolean(accountId),
  });
}
