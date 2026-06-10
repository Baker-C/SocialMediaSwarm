import { Outlet, useLocation, useParams } from 'react-router-dom';
import { ErrorBanner } from '../components/layout/ErrorBanner';
import { useAccounts } from '../hooks/queries/useAccounts';
import { apiBaseUrl } from '../lib/api';
import { Sidebar } from '../navigation/Sidebar';
import { OAuthRedirectHandler } from './OAuthRedirectHandler';

function pageTitle(pathname: string, accountId?: string): string {
  if (!accountId) {
    return 'Overview';
  }
  if (pathname.endsWith('/settings')) {
    return `Account · ${accountId} · Settings`;
  }
  if (pathname.includes('/posts/')) {
    return `Account · ${accountId} · Post`;
  }
  if (pathname.endsWith('/posts')) {
    return `Account · ${accountId} · Posts`;
  }
  if (pathname.endsWith('/references')) {
    return `Account · ${accountId} · References`;
  }
  if (pathname.endsWith('/pipeline')) {
    return `Account · ${accountId} · Pipeline`;
  }
  if (pathname.endsWith('/voice')) {
    return `Account · ${accountId} · Voice`;
  }
  return `Account · ${accountId}`;
}

export function AppLayout() {
  const apiBase = apiBaseUrl();
  const location = useLocation();
  const { accountId } = useParams();
  const accountsQuery = useAccounts();

  const accounts = accountsQuery.data ?? [];
  const mainTitle = pageTitle(location.pathname, accountId);

  return (
    <div className="app-shell">
      <OAuthRedirectHandler />
      <Sidebar accounts={accounts} />

      <main className="main-panel">
        <header className="main-panel__header">
          <h1>Social Media Autonomous Agents</h1>
          <p className="main-panel__page-title">{mainTitle}</p>
          <p className="App-meta">
            API: {apiBase || '(dev proxy → http://127.0.0.1:8000)'}
          </p>
          {process.env.NODE_ENV === 'development' ? (
            <p className="App-meta-hint">
              Open <strong>http://localhost:3000/</strong> (path <code>/</code> only). If you open{' '}
              <code>/api/health</code> or another <code>/api/…</code> URL in the address bar, the
              dev server proxies that path and the browser shows raw JSON instead of this dashboard.
            </p>
          ) : null}
        </header>

        {accountsQuery.isLoading ? <p className="App-loading">Loading API data…</p> : null}
        {accountsQuery.isError ? (
          <ErrorBanner
            message="Could not load accounts. Is the backend running on port 8000? Start it from `SocialMediaAutonomousAgents/backend`, then restart `npm start` in `frontend`."
          />
        ) : null}

        {!accountsQuery.isLoading ? <Outlet /> : null}
      </main>
    </div>
  );
}
