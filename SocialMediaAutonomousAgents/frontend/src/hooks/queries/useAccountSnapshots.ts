import { useQuery } from '@tanstack/react-query';
import { fetchAccountSnapshots } from '../../api/endpoints/snapshots';

export function useAccountSnapshots(accountId: string | undefined) {
  return useQuery({
    queryKey: ['accountSnapshots', accountId],
    queryFn: () => fetchAccountSnapshots(accountId!),
    enabled: Boolean(accountId),
  });
}
