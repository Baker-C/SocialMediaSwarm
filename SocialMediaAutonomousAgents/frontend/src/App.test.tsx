import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import App from './App';

const jsonResponse = (body: unknown) =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  } as Response);

const sampleAccount = {
  account_id: 'demo',
  niche: 'Test niche',
  twitter_handle: '@demo',
  status: 'active',
  followers: 42,
  posts_total: 3,
  has_credentials: true,
  registered_at: '2026-01-01T00:00:00.000Z',
  follower_growth_vs_registered: 42,
  last_post_slot: '2026-05-13-12',
  recent_post: {
    snippet: 'Hello world post text',
    posted_at: '2026-05-13T11:00:00.000Z',
    post_id: '99',
    views: null as number | null,
  },
};

beforeEach(() => {
  global.fetch = jest.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.endsWith('/api/health')) {
      return jsonResponse({ status: 'ok' });
    }
    if (url.endsWith('/api/accounts')) {
      return jsonResponse([sampleAccount]);
    }
    if (url.endsWith('/api/posts')) {
      return jsonResponse([]);
    }
    if (url.endsWith('/api/patterns')) {
      return jsonResponse([]);
    }
    if (url.endsWith('/api/dashboard')) {
      return jsonResponse({ active_accounts: 3, top_niche: 'n/a', avg_engagement: 0 });
    }
    return jsonResponse({});
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('renders application title', async () => {
  render(<App />);
  expect(screen.getByText(/Social Media Autonomous Agents/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.queryByText(/Loading API data/i)).not.toBeInTheDocument();
  });
});

test('shows active account count from dashboard API', async () => {
  render(<App />);
  await waitFor(() => {
    const overview = screen.getByLabelText('Dashboard overview');
    expect(within(overview).getByText('3')).toBeInTheDocument();
  });
  expect(screen.getByText(/Active accounts/i)).toBeInTheDocument();
});

test('renders an account card from accounts API', async () => {
  render(<App />);
  const accountsSection = await screen.findByLabelText('Registered accounts');
  await waitFor(() => {
    expect(within(accountsSection).getByRole('heading', { name: 'demo' })).toBeInTheDocument();
  });
  expect(within(accountsSection).getByText('Test niche')).toBeInTheDocument();
  expect(within(accountsSection).getByText(/Hello world post text/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Accounts', level: 2 })).toBeInTheDocument();
});

test('shows empty state when no accounts', async () => {
  (global.fetch as jest.Mock).mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.endsWith('/api/health')) {
      return jsonResponse({ status: 'ok' });
    }
    if (url.endsWith('/api/accounts')) {
      return jsonResponse([]);
    }
    if (url.endsWith('/api/posts')) {
      return jsonResponse([]);
    }
    if (url.endsWith('/api/patterns')) {
      return jsonResponse([]);
    }
    if (url.endsWith('/api/dashboard')) {
      return jsonResponse({ active_accounts: 0, top_niche: 'n/a', avg_engagement: 0 });
    }
    return jsonResponse({});
  });
  render(<App />);
  await waitFor(() => {
    expect(screen.getByText(/No accounts returned from the API/i)).toBeInTheDocument();
  });
});
