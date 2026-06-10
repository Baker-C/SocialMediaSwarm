import { apiFetch } from '../client';
import type { VoiceRevision } from '../../types';

export type VoiceRevisionsResponse = {
  account_id: string;
  count: number;
  revisions: VoiceRevision[];
};

export async function fetchVoiceRevisions(accountId: string): Promise<VoiceRevisionsResponse> {
  return apiFetch<VoiceRevisionsResponse>(
    `/accounts/${encodeURIComponent(accountId)}/voice-revisions`
  );
}
