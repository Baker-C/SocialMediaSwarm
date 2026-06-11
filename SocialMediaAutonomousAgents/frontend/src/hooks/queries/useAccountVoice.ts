import { useQuery } from '@tanstack/react-query';
import { fetchAccountVoice } from '../../api/endpoints/accounts';
import type { AccountVoiceDetail } from '../../types';

export function useAccountVoice(accountId: string | undefined) {
  return useQuery<AccountVoiceDetail, Error>({
    queryKey: ['accountVoice', accountId],
    queryFn: () => fetchAccountVoice(accountId as string),
    enabled: Boolean(accountId),
  });
}
