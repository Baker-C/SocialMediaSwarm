import { useQuery } from '@tanstack/react-query';
import { fetchVoiceRevisions } from '../../api/endpoints/voice';

export function useVoiceRevisions(accountId: string | undefined) {
  return useQuery({
    queryKey: ['voiceRevisions', accountId],
    queryFn: () => fetchVoiceRevisions(accountId!),
    enabled: Boolean(accountId),
  });
}
