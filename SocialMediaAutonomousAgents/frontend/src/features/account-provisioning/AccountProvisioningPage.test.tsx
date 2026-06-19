import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { AccountProvisioningPage } from './AccountProvisioningPage';
import * as personaChatApi from '../../api/endpoints/personaChat';
import * as provisioningApi from '../../api/endpoints/provisioning';
import type { PersonaSpec, PersonaStreamEvent } from '../../types/domain/persona';
import type { ProvisioningStatusEvent } from '../../types/domain/persona';

jest.mock('../../api/endpoints/personaChat');
jest.mock('../../api/endpoints/provisioning');

const spec: PersonaSpec = {
  handle: 'oracle',
  display_name: 'The Oracle',
  bio: 'Sees all.',
  category: 'mystic',
  personality: 'cryptic',
  posting_prompt: 'speak in riddles',
  avatar_prompt: 'glowing eyes',
  header_prompt: 'cosmic banner',
};

function renderPage() {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AccountProvisioningPage />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe('AccountProvisioningPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (personaChatApi.mediaUrl as jest.Mock).mockImplementation((id: string) => `/api/media/${id}`);
  });

  it('shows the assistant reply and persona preview after sending a message', async () => {
    const streamMock = personaChatApi.streamPersonaChat as jest.Mock;
    streamMock.mockImplementation(async (_apiBase, _req, onEvent) => {
      onEvent({ type: 'assistant_message', text: 'Here is a persona.' } as PersonaStreamEvent);
      onEvent({ type: 'persona_preview', spec } as PersonaStreamEvent);
      onEvent({ type: 'done' } as PersonaStreamEvent);
    });

    renderPage();

    fireEvent.change(screen.getByLabelText('ACCOUNT ID'), {
      target: { value: 'midnight_oracle' },
    });
    fireEvent.change(screen.getByPlaceholderText('Describe the account…'), {
      target: { value: 'A mystic tarot account' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText('Here is a persona.')).toBeInTheDocument();
    });
    // persona_preview rendered the spec in the right pane
    expect(screen.getByText('@oracle')).toBeInTheDocument();
    expect(streamMock).toHaveBeenCalled();
  });

  it('renders the Continue button on awaiting_captcha and calls sendControl', async () => {
    const streamMock = personaChatApi.streamPersonaChat as jest.Mock;
    streamMock.mockImplementation(async (_apiBase, req, onEvent) => {
      if (req.approve) {
        onEvent({ type: 'images_generating' } as PersonaStreamEvent);
        onEvent({
          type: 'images_ready',
          avatar_asset_id: 'a1',
          header_asset_id: 'h1',
        } as PersonaStreamEvent);
        onEvent({ type: 'account_written', account_id: 'midnight_oracle' } as PersonaStreamEvent);
        onEvent({ type: 'done' } as PersonaStreamEvent);
      } else {
        onEvent({ type: 'assistant_message', text: 'Here is a persona.' } as PersonaStreamEvent);
        onEvent({ type: 'persona_preview', spec } as PersonaStreamEvent);
        onEvent({ type: 'done' } as PersonaStreamEvent);
      }
    });

    (provisioningApi.startProvisioning as jest.Mock).mockResolvedValue({ ok: true });
    (provisioningApi.sendControl as jest.Mock).mockResolvedValue({ ok: true });
    (provisioningApi.streamProvisioningStatus as jest.Mock).mockImplementation(
      async (_apiBase, _accountId, onEvent) => {
        onEvent({
          type: 'status',
          status: 'awaiting_captcha',
          current_page: 'signup',
          step_log: ['opened signup page'],
        } as ProvisioningStatusEvent);
      }
    );

    renderPage();

    fireEvent.change(screen.getByLabelText('ACCOUNT ID'), {
      target: { value: 'midnight_oracle' },
    });
    fireEvent.change(screen.getByPlaceholderText('Describe the account…'), {
      target: { value: 'A mystic tarot account' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    // chat -> review
    await waitFor(() => expect(screen.getByText('@oracle')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Review & edit' }));

    // review -> approve -> provisioning
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Approve & provision' })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: 'Approve & provision' }));

    // provisioning stage with awaiting_captcha
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    );
    expect(screen.getByText('CAPTCHA required')).toBeInTheDocument();
    expect(provisioningApi.startProvisioning).toHaveBeenCalledWith('midnight_oracle');

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() =>
      expect(provisioningApi.sendControl).toHaveBeenCalledWith('midnight_oracle', 'continue')
    );
  });
});
