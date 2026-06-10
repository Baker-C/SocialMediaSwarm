import { useQuery } from '@tanstack/react-query';
import { apiBaseUrl } from '../../api/client';
import { fetchOAuthStatus } from '../../api/endpoints/oauth';

export function useOAuthStatus(accountId: string | undefined) {
  const apiBase = apiBaseUrl();
  return useQuery({
    queryKey: ['oauthStatus', accountId],
    queryFn: () => fetchOAuthStatus(apiBase, accountId!),
    enabled: Boolean(accountId),
  });
}
