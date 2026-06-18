import { apiFetch } from '../client';
import type { PipelineSpec } from '../../types/domain/pipelineSpec';
import type { ValidationReport } from '../../types/domain/validation';

export async function fetchAccountSpec(
  accountId: string,
  status: 'champion' | 'challenger' = 'champion'
): Promise<PipelineSpec> {
  return apiFetch<PipelineSpec>(
    `/accounts/${encodeURIComponent(accountId)}/pipeline/spec?status=${status}`
  );
}

export async function validateAccountSpec(accountId: string): Promise<ValidationReport> {
  return apiFetch<ValidationReport>(
    `/accounts/${encodeURIComponent(accountId)}/pipeline/spec/validate`,
    { method: 'POST' }
  );
}
