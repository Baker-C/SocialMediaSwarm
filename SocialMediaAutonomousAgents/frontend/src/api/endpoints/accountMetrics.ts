import { apiFetch } from '../client';
import type { AccountMetrics } from '../../types';

export async function fetchAccountMetricsDoc(accountId: string): Promise<AccountMetrics> {
  return apiFetch<AccountMetrics>(`/accounts/${encodeURIComponent(accountId)}/account-metrics`);
}
