import { apiFetch } from '../client';
import type { PipelineOutcome } from '../../types';
import type { PipelineFilterParams } from '../../types/domain/filters';

export type PipelineOutcomesResponse = {
  account_id?: string;
  count: number;
  outcomes: PipelineOutcome[];
};

function buildQuery(params?: PipelineFilterParams): string {
  if (!params) {
    return '';
  }
  const qs = new URLSearchParams();
  if (params.since) {
    qs.set('since', params.since);
  }
  if (params.limit) {
    qs.set('limit', String(params.limit));
  }
  if (params.phase) {
    qs.set('phase', params.phase);
  }
  if (params.status) {
    qs.set('status', params.status);
  }
  if (params.accountId) {
    qs.set('account_id', params.accountId);
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}

export async function fetchAccountPipelineOutcomes(
  accountId: string,
  params?: PipelineFilterParams
): Promise<PipelineOutcomesResponse> {
  return apiFetch<PipelineOutcomesResponse>(
    `/accounts/${encodeURIComponent(accountId)}/pipeline-outcomes${buildQuery(params)}`
  );
}

export async function fetchFleetPipelineOutcomes(
  params?: PipelineFilterParams
): Promise<PipelineOutcomesResponse> {
  return apiFetch<PipelineOutcomesResponse>(`/pipeline-outcomes${buildQuery(params)}`);
}
