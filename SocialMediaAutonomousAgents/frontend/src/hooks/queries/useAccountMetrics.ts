import { useQuery } from '@tanstack/react-query';
import { fetchAccountMetricsDoc, fetchMetricsLegacy } from '../../api/endpoints/accountMetrics';

export function useAccountMetrics(accountId: string | undefined) {
  return useQuery({
    queryKey: ['accountMetrics', accountId],
    queryFn: async () => {
      try {
        return await fetchAccountMetricsDoc(accountId!);
      } catch {
        return fetchMetricsLegacy(accountId!);
      }
    },
    enabled: Boolean(accountId),
  });
}
