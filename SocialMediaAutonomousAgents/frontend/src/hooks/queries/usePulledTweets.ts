import { useQuery } from '@tanstack/react-query';
import { fetchPulledTweets } from '../../api/endpoints/references';

export function usePulledTweets(
  accountId: string | undefined,
  since?: string
) {
  return useQuery({
    queryKey: ['pulledTweets', accountId, since],
    queryFn: () => fetchPulledTweets(accountId!, { limit: 500, since }),
    enabled: Boolean(accountId),
  });
}
