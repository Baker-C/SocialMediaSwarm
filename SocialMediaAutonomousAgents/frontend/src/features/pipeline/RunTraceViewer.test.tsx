import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RunTraceViewer } from './RunTraceViewer';
import * as stepOutputsApi from '../../api/endpoints/stepOutputs';
import type { PipelineRun } from '../../types/domain/pipelineRun';
import type { StepOutputDocument } from '../../types/domain/stepOutput';

jest.mock('../../api/endpoints/stepOutputs');

const mockStepOutput: StepOutputDocument = {
  run_id: 'run-1',
  account_id: 'test-account',
  step_id: 'test_step',
  scope: 'runbook',
  seq: 1,
  status: 'ok',
  inputs: [
    { artifact: 'input1', present: true, value: 'test input' },
  ],
  outputs: [
    { artifact: 'output1', present: true, value: 'test output' },
  ],
};

describe('RunTraceViewer', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
    jest.clearAllMocks();
  });

  it('renders chain from step_links when present', () => {
    const run: PipelineRun = {
      run_id: 'run-1',
      account_id: 'test-account',
      slot: 'daily',
      mode: 'force-post',
      niche: 'tech',
      status: 'ok',
      step_count: 2,
      steps: [],
      step_links: [
        { step_id: 'step1', scope: 'runbook', seq: 1, status: 'ok', duration_ms: 100, doc_id: 'doc1' },
        { step_id: 'step2', scope: 'runbook', seq: 2, status: 'ok', duration_ms: 200, doc_id: 'doc2' },
      ],
    };

    render(
      <QueryClientProvider client={queryClient}>
        <RunTraceViewer run={run} />
      </QueryClientProvider>
    );

    expect(screen.getByText('step1')).toBeInTheDocument();
    expect(screen.getByText('step2')).toBeInTheDocument();
  });

  it('falls back to nested steps when step_links is empty', () => {
    const run: PipelineRun = {
      run_id: 'run-1',
      account_id: 'test-account',
      slot: 'daily',
      mode: 'force-post',
      niche: 'tech',
      status: 'ok',
      step_count: 1,
      steps: [
        {
          step_id: 'legacy_step',
          scope: 'runbook',
          status: 'ok',
          inputs: [],
          outputs: [],
        },
      ],
    };

    render(
      <QueryClientProvider client={queryClient}>
        <RunTraceViewer run={run} />
      </QueryClientProvider>
    );

    expect(screen.getByText('legacy_step')).toBeInTheDocument();
  });

  it('fetches step output on row click', async () => {
    const fetchStepOutputMock = stepOutputsApi.fetchStepOutput as jest.Mock;
    fetchStepOutputMock.mockResolvedValue(mockStepOutput);

    const run: PipelineRun = {
      run_id: 'run-1',
      account_id: 'test-account',
      slot: 'daily',
      mode: 'force-post',
      niche: 'tech',
      status: 'ok',
      step_count: 1,
      steps: [],
      step_links: [
        { step_id: 'test_step', scope: 'runbook', seq: 1, status: 'ok', doc_id: 'doc1' },
      ],
    };

    render(
      <QueryClientProvider client={queryClient}>
        <RunTraceViewer run={run} />
      </QueryClientProvider>
    );

    const stepRow = screen.getByText('test_step').closest('li');
    fireEvent.click(stepRow!);

    // Wait for fetch
    await new Promise((r) => setTimeout(r, 100));

    expect(fetchStepOutputMock).toHaveBeenCalledWith('run-1', 'test_step');
  });
});
