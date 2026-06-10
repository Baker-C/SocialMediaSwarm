import { useQuery } from '@tanstack/react-query';
import { fetchTrackedPosts } from '../../api/endpoints/posts';
import type { PostFilterParams } from '../../types';

export function useTrackedPosts(accountId: string | undefined, filters?: PostFilterParams) {
  return useQuery({
    queryKey: ['trackedPosts', accountId, filters?.since],
    queryFn: () =>
      fetchTrackedPosts(accountId!, {
        since: filters?.since,
        limit: 500,
      }),
    enabled: Boolean(accountId),
  });
}
