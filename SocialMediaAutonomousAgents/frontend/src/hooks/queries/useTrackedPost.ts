import { useQuery } from '@tanstack/react-query';
import { fetchTrackedPost } from '../../api/endpoints/posts';

export function useTrackedPost(accountId: string | undefined, tweetId: string | undefined) {
  return useQuery({
    queryKey: ['post', accountId, tweetId],
    queryFn: () => fetchTrackedPost(accountId!, tweetId!),
    enabled: Boolean(accountId && tweetId),
  });
}
