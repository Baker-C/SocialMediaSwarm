import { useQuery } from '@tanstack/react-query';
import { fetchVoiceRevisions, type VoiceRevisionsResponse } from '../../api/endpoints/voice';

export function useVoiceRevisions(accountId: string | undefined) {
  return useQuery<VoiceRevisionsResponse, Error>({
    queryKey: ['voiceRevisions', accountId],
    queryFn: () => fetchVoiceRevisions(accountId!),
    enabled: Boolean(accountId),
  });
}
