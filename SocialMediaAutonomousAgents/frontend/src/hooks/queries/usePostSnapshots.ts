import { useQuery } from '@tanstack/react-query';
import { fetchPostSnapshots } from '../../api/endpoints/posts';

export function usePostSnapshots(
  accountId: string | undefined,
  tweetId: string | undefined
) {
  return useQuery({
    queryKey: ['postSnapshots', accountId, tweetId],
    queryFn: () => fetchPostSnapshots(accountId!, tweetId!),
    enabled: Boolean(accountId && tweetId),
  });
}
