import { apiFetch } from '../client';
import type { PipelineRun } from '../../types/domain/pipelineRun';

export type PipelineRunsResponse = {
  count: number;
  runs: PipelineRun[];
};

export async function fetchAccountPipelineRuns(
  accountId: string,
  limit = 1
): Promise<PipelineRunsResponse> {
  return apiFetch<PipelineRunsResponse>(
    `/accounts/${encodeURIComponent(accountId)}/pipeline/runs?limit=${limit}`
  );
}

export async function fetchPipelineRun(runId: string): Promise<PipelineRun> {
  return apiFetch<PipelineRun>(`/pipeline/runs/${encodeURIComponent(runId)}`);
}
