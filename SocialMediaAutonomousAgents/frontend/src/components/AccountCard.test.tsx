import { render, screen } from '@testing-library/react';
import { AccountCard } from './AccountCard';
import type { AccountSummary } from '../types';

function makeAccount(overrides: Partial<AccountSummary> = {}): AccountSummary {
  return {
    account_id: 'acct-1',
    category: 'tech',
    twitter_handle: 'devhandle',
    status: 'active',
    followers: 100,
    posts_total: 5,
    ...overrides,
  };
}

const noop = () => {};

describe('AccountCard X profile link', () => {
  it('renders a safe external link in the verified state', () => {
    render(
      <AccountCard
        account={makeAccount({
          has_credentials: true,
          x_user_id: '2054643922534875136',
          x_username: 'devhandle',
        })}
        onUpdateClick={noop}
      />
    );
    const link = screen.getByRole('link', { name: '@devhandle' });
    expect(link).toHaveAttribute('href', 'https://x.com/i/user/2054643922534875136');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders no link when connected but identity is missing', () => {
    render(
      <AccountCard
        account={makeAccount({ has_credentials: true, x_user_id: null, x_username: null })}
        onUpdateClick={noop}
      />
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText(/profile link unavailable/i)).toBeInTheDocument();
  });

  it('renders no link in the not-connected state', () => {
    render(
      <AccountCard account={makeAccount({ has_credentials: false })} onUpdateClick={noop} />
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText(/Not connected/i)).toBeInTheDocument();
  });

  it('renders no link in the not-provisioned state', () => {
    render(<AccountCard account={makeAccount()} onUpdateClick={noop} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows both the verified username and the differing handle marked unverified', () => {
    render(
      <AccountCard
        account={makeAccount({
          has_credentials: true,
          twitter_handle: 'oldhandle',
          x_user_id: '999',
          x_username: 'realuser',
        })}
        onUpdateClick={noop}
      />
    );
    expect(screen.getByRole('link', { name: '@realuser' })).toBeInTheDocument();
    expect(screen.getByText(/oldhandle/)).toBeInTheDocument();
    expect(screen.getByText(/unverified/i)).toBeInTheDocument();
  });
});
