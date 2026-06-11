import { useState } from 'react';
import { Outlet, useLocation, useParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '../components/ui/button';
import { ErrorBanner } from '../components/layout/ErrorBanner';
import { useAccounts } from '../hooks/queries/useAccounts';
import { apiBaseUrl } from '../api/client';
import { Sidebar } from '../navigation/Sidebar';
import { OAuthRedirectHandler } from './OAuthRedirectHandler';

function pageTitle(pathname: string, accountId?: string): string {
  if (!accountId) {
    return 'OVERVIEW';
  }
  const id = accountId.toUpperCase();
  if (pathname.endsWith('/settings')) {
    return `${id} / SETTINGS`;
  }
  if (pathname.includes('/posts/')) {
    return `${id} / POST`;
  }
  if (pathname.endsWith('/posts')) {
    return `${id} / POSTS`;
  }
  if (pathname.endsWith('/references')) {
    return `${id} / REFERENCES`;
  }
  if (pathname.endsWith('/pipeline')) {
    return `${id} / PIPELINE`;
  }
  if (pathname.endsWith('/voice')) {
    return `${id} / VOICE`;
  }
  return `${id} / HQ`;
}

export function AppLayout() {
  const apiBase = apiBaseUrl();
  const location = useLocation();
  const { accountId } = useParams();
  const accountsQuery = useAccounts();
  const queryClient = useQueryClient();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const accounts = accountsQuery.data ?? [];
  const mainTitle = pageTitle(location.pathname, accountId);

  return (
    <div className="flex h-screen bg-black">
      <OAuthRedirectHandler />
      <Sidebar
        accounts={accounts}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((prev) => !prev)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Toolbar */}
        <header className="h-16 flex-shrink-0 bg-neutral-800 border-b border-neutral-700 flex items-center justify-between px-6 gap-4">
          <div className="text-sm text-neutral-400 tracking-wider truncate">
            SOCIAL MEDIA OPS / <span className="text-orange-500">{mainTitle}</span>
          </div>
          <div className="flex items-center gap-4 flex-shrink-0">
            <div className="text-xs text-neutral-500 hidden md:block">
              API: {apiBase || 'DEV PROXY → 127.0.0.1:8000'}
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Refresh data"
              onClick={() => void queryClient.invalidateQueries()}
              className="text-neutral-400 hover:text-orange-500"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          {accountsQuery.isLoading ? (
            <p className="text-xs text-neutral-500 tracking-wider animate-pulse">
              LOADING API DATA…
            </p>
          ) : null}
          {accountsQuery.isError ? (
            <ErrorBanner
              message="Could not load accounts. Is the backend running on port 8000? Start it from `SocialMediaAutonomousAgents/backend`, then restart `npm start` in `frontend`."
            />
          ) : null}

          {!accountsQuery.isLoading ? <Outlet /> : null}
        </main>
      </div>
    </div>
  );
}
