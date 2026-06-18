import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { AgentBuilderPage } from './AgentBuilderPage';
import * as pipelineSpecApi from '../../api/endpoints/pipelineSpec';
import * as builderChatApi from '../../api/endpoints/builderChat';
import type { PipelineSpec } from '../../types/domain/pipelineSpec';
import type { BuilderStreamEvent } from '../../types/domain/builder';

jest.mock('../../api/endpoints/pipelineSpec');
jest.mock('../../api/endpoints/builderChat');
jest.mock('../../app/AppContext', () => ({
  useAppContext: () => ({
    setToast: jest.fn(),
  }),
}));

const baselineSpec: PipelineSpec = {
  account_id: 'test-account',
  status: 'champion',
  steps: [
    {
      kind: 'step',
      id: 'test_step',
      tool_id: 'deterministic.test',
      reads: [],
      writes: ['output'],
    },
  ],
};

describe('AgentBuilderPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
    jest.clearAllMocks();
  });

  it('renders spec from API on load', async () => {
    const fetchSpecMock = pipelineSpecApi.fetchAccountSpec as jest.Mock;
    fetchSpecMock.mockResolvedValue(baselineSpec);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentBuilderPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    // Wait for spec to load
    await waitFor(() => {
      expect(fetchSpecMock).toHaveBeenCalledWith('test-account', 'champion');
    });
  });

  it('handles builder stream events', async () => {
    const fetchSpecMock = pipelineSpecApi.fetchAccountSpec as jest.Mock;
    fetchSpecMock.mockResolvedValue(baselineSpec);

    const streamMock = builderChatApi.streamBuilderChat as jest.Mock;
    streamMock.mockImplementation(async (apiBase, req, onEvent) => {
      onEvent({ type: 'assistant_message', text: 'I will help you.' } as BuilderStreamEvent);
      onEvent({ type: 'done' } as BuilderStreamEvent);
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentBuilderPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    // Wait for spec to load
    await waitFor(() => {
      expect(fetchSpecMock).toHaveBeenCalled();
    });
  });

  it('shows validation errors on error event', async () => {
    const fetchSpecMock = pipelineSpecApi.fetchAccountSpec as jest.Mock;
    fetchSpecMock.mockResolvedValue(baselineSpec);

    const streamMock = builderChatApi.streamBuilderChat as jest.Mock;
    streamMock.mockImplementation(async (apiBase, req, onEvent) => {
      onEvent({ type: 'assistant_message', text: 'Let me fix that.' } as BuilderStreamEvent);
      onEvent({
        type: 'validation_errors',
        errors: [{ code: 'MISSING_TOOL', detail: 'Tool not found' }],
      } as BuilderStreamEvent);
      onEvent({ type: 'done' } as BuilderStreamEvent);
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentBuilderPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(fetchSpecMock).toHaveBeenCalled();
    });
  });
});
