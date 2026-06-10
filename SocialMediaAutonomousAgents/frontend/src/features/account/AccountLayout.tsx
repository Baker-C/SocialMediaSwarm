import { useCallback, useState } from 'react';
import { Outlet, NavLink, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ACCOUNT_SUB_NAV, accountSubNavPath } from '../../navigation/navItems';
import { useAppContext } from '../../app/AppContext';

const ACCOUNT_QUERY_PREFIXES = (accountId: string) =>
  [
    ['accounts'],
    ['dashboard'],
    ['accountMetrics', accountId],
    ['trackedPosts', accountId],
    ['post', accountId],
    ['postSnapshots', accountId],
    ['pulledTweets', accountId],
    ['pipelineOutcomes', accountId],
    ['pipelineOutcomes', 'fleet'],
    ['voiceRevisions', accountId],
    ['accountSnapshots', accountId],
    ['oauthStatus', accountId],
  ] as const;

export function AccountLayout() {
  const { accountId } = useParams();
  const queryClient = useQueryClient();
  const { setToast } = useAppContext();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refreshAccountData = useCallback(async () => {
    if (!accountId || isRefreshing) {
      return;
    }

    setIsRefreshing(true);
    try {
      await Promise.all(
        ACCOUNT_QUERY_PREFIXES(accountId).map((queryKey) =>
          queryClient.invalidateQueries({ queryKey })
        )
      );
      setToast('Refreshed');
    } finally {
      setIsRefreshing(false);
    }
  }, [accountId, isRefreshing, queryClient, setToast]);

  if (!accountId) {
    return null;
  }

  return (
    <div className="account-layout">
      <nav className="account-subnav" aria-label="Account sections">
        <div className="account-subnav__links">
          {ACCOUNT_SUB_NAV.map((sub) => (
            <NavLink
              key={sub.segment || 'hq'}
              to={accountSubNavPath(accountId, sub.segment)}
              end={sub.end}
              className={({ isActive }) =>
                `account-subnav__link${isActive ? ' account-subnav__link--active' : ''}`
              }
            >
              {sub.label}
            </NavLink>
          ))}
        </div>
        <button
          type="button"
          className="btn btn--ghost account-subnav__refresh"
          aria-label="Refresh account data"
          disabled={isRefreshing}
          onClick={() => void refreshAccountData()}
        >
          {isRefreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </nav>
      <div className="account-layout__content">
        <Outlet />
      </div>
    </div>
  );
}
