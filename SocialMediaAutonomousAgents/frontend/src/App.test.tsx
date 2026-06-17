import React from 'react';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import App from './App';
import { router } from './app/routes';

const jsonResponse = (body: unknown) =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  } as Response);

const sampleAccount = {
  account_id: 'demo',
  category: 'Test niche',
  twitter_handle: '@demo',
  status: 'active',
  followers: 42,
  posts_total: 3,
  has_credentials: true,
  registered_at: '2026-01-01T00:00:00.000Z',
  follower_growth_vs_registered: 42,
  last_interval_slot: '2026-05-13-12',
  recent_post: {
    snippet: 'Hello world post text',
    posted_at: '2026-05-13T11:00:00.000Z',
    post_id: '99',
    views: null as number | null,
  },
};

function mockFetch(handler?: (url: string) => unknown) {
  global.fetch = jest.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (handler) {
      const custom = handler(url);
      if (custom !== undefined) {
        return jsonResponse(custom);
      }
    }
    if (url.includes('/api/accounts/demo/account-metrics')) {
      return jsonResponse({ avg_engagement_rate: 0.02 });
    }
    if (url.includes('/api/accounts/demo/snapshots')) {
      return jsonResponse({ account_id: 'demo', count: 0, snapshots: [] });
    }
    if (url.includes('/api/oauth/x/status/demo')) {
      return jsonResponse({ connected: true });
    }
    if (url.endsWith('/api/accounts')) {
      return jsonResponse([sampleAccount]);
    }
    if (url.endsWith('/api/dashboard')) {
      return jsonResponse({ active_accounts: 3, top_niche: 'n/a', avg_engagement: 0 });
    }
    return jsonResponse({});
  }) as jest.Mock;
}

beforeEach(async () => {
  await router.navigate('/', { replace: true });
  mockFetch();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('renders application title', async () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /Solomon's Swarm/i })).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.queryByText(/Loading API data/i)).not.toBeInTheDocument();
  });
});

test('shows active account count on overview tab', async () => {
  render(<App />);
  await waitFor(() => {
    const overview = screen.getByLabelText('Swarm KPIs');
    expect(within(overview).getByText('3')).toBeInTheDocument();
  });
  expect(screen.getByText(/Active accounts/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Overview/i })).toHaveAttribute('aria-current', 'page');
});

test('overview lists accounts with leaderboard', async () => {
  render(<App />);
  const leaderboard = await screen.findByLabelText('Account leaderboard');
  await waitFor(() => {
    expect(within(leaderboard).getByText('demo')).toBeInTheDocument();
  });
  expect(within(leaderboard).getByText('Test niche')).toBeInTheDocument();
});

test('account tab shows account HQ', async () => {
  render(<App />);
  await waitFor(() => {
    expect(screen.queryByText(/Loading API data/i)).not.toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole('link', { name: /demo Test niche/i }));

  await waitFor(() => {
    expect(screen.getByRole('heading', { name: 'demo' })).toBeInTheDocument();
  });
  expect(screen.getByLabelText('Account KPIs')).toBeInTheDocument();
  expect(screen.getByText(/DEMO \/ HQ/i)).toBeInTheDocument();
});

test('shows empty leaderboard when no accounts', async () => {
  await router.navigate('/', { replace: true });
  mockFetch((url) => {
    if (url.endsWith('/api/accounts')) {
      return [];
    }
    if (url.endsWith('/api/dashboard')) {
      return { active_accounts: 0, top_niche: 'n/a', avg_engagement: 0 };
    }
    return undefined;
  });
  render(<App />);
  fireEvent.click(await screen.findByRole('link', { name: /Overview/i }));
  await waitFor(() => {
    expect(screen.getByText(/No accounts to rank/i)).toBeInTheDocument();
  });
  expect(screen.queryByRole('link', { name: /demo/i })).not.toBeInTheDocument();
});
