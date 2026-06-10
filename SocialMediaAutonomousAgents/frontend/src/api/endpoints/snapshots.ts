import { apiFetch } from '../client';
import type { AccountSnapshot } from '../../types';

export type AccountSnapshotsResponse = {
  account_id: string;
  count: number;
  snapshots: AccountSnapshot[];
};

export async function fetchAccountSnapshots(
  accountId: string,
  limit = 100
): Promise<AccountSnapshotsResponse> {
  return apiFetch<AccountSnapshotsResponse>(
    `/accounts/${encodeURIComponent(accountId)}/snapshots?limit=${limit}`
  );
}
