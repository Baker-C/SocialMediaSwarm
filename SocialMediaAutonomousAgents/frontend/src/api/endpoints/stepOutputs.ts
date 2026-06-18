import { apiFetch } from '../client';
import type { StepOutputDocument } from '../../types/domain/stepOutput';

export async function fetchStepOutput(
  runId: string,
  stepId: string
): Promise<StepOutputDocument> {
  return apiFetch<StepOutputDocument>(
    `/pipeline/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}`
  );
}
