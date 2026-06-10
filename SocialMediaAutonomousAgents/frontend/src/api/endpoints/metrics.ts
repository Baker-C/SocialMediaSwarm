import { apiFetch } from '../client';

export async function fetchAccountMetrics(accountId: string): Promise<unknown> {
  return apiFetch(`/metrics/${encodeURIComponent(accountId)}`);
}
