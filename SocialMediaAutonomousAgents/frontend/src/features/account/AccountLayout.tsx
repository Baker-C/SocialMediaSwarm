import { useCallback, useMemo, useState } from 'react';
import { Outlet, useLocation, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAppContext } from '../../app/AppContext';
import { useTrackedPost } from '../../hooks/queries/useTrackedPost';
import { formatShortDate } from '../../lib/format';

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

type AccountSection =
  | 'hq'
  | 'posts'
  | 'post-detail'
  | 'references'
  | 'pipeline'
  | 'voice'
  | 'settings';

function resolveAccountSection(pathname: string, accountId: string): AccountSection {
  const base = `/accounts/${accountId}`;
  if (pathname.includes(`${base}/posts/`)) {
    return 'post-detail';
  }
  if (pathname.endsWith('/posts')) {
    return 'posts';
  }
  if (pathname.endsWith('/references')) {
    return 'references';
  }
  if (pathname.endsWith('/pipeline')) {
    return 'pipeline';
  }
  if (pathname.endsWith('/voice')) {
    return 'voice';
  }
  if (pathname.endsWith('/settings')) {
    return 'settings';
  }
  return 'hq';
}

function sectionHeader(
  section: AccountSection,
  accountId: string,
  tweetId?: string,
  postPostedAt?: string | null
): { title: string; subtitle?: string } {
  switch (section) {
    case 'posts':
      return {
        title: 'Posts Explorer',
        subtitle: 'Tracked posts with filters and export',
      };
    case 'post-detail':
      return {
        title: `Post ${tweetId ?? ''}`,
        subtitle: postPostedAt ? formatShortDate(postPostedAt) : undefined,
      };
    case 'references':
      return {
        title: 'References Lab',
        subtitle: 'Pulled tweets, funnel, and query yield',
      };
    case 'pipeline':
      return {
        title: 'Pipeline Ops',
        subtitle: 'Outcomes, skips, and phase health',
      };
    case 'voice':
      return {
        title: 'Voice & Experiments',
        subtitle: 'Revision history and performance by voice version',
      };
    case 'settings':
      return {
        title: 'Account Settings',
        subtitle: `Profile, credentials, and OAuth for ${accountId}`,
      };
    case 'hq':
    default:
      return {
        title: 'Account HQ',
        subtitle: `Operational overview for ${accountId}`,
      };
  }
}

export function AccountLayout() {
  const { accountId, tweetId } = useParams();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { setToast } = useAppContext();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const postQuery = useTrackedPost(accountId, tweetId);

  const section = useMemo(
    () => (accountId ? resolveAccountSection(location.pathname, accountId) : 'hq'),
    [accountId, location.pathname]
  );

  const header = useMemo(
    () =>
      accountId
        ? sectionHeader(section, accountId, tweetId, postQuery.data?.posted_at)
        : { title: '', subtitle: undefined },
    [accountId, section, tweetId, postQuery.data?.posted_at]
  );

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
      <div className="account-subnav" aria-label="Account section">
        <div className="page-header__text">
          <h2 className="page-header__title">{header.title}</h2>
          {header.subtitle ? <p className="page-header__subtitle">{header.subtitle}</p> : null}
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
      </div>
      <div className="account-layout__content">
        <Outlet />
      </div>
    </div>
  );
}
