import React, { useCallback, useEffect, useMemo, useState } from 'react';
import './App.css';
import { UpdateAccountModal } from './components/UpdateAccountModal';
import { apiBaseUrl, apiPrefix, parseAccounts, readActiveAccountCount } from './lib/api';
import { buildNavItems } from './navigation/tabs';
import type { TabId } from './navigation/tabs';
import { Sidebar } from './navigation/Sidebar';
import { renderPanel } from './panels/renderPanel';
import type { ApiState } from './types';

function App() {
  const apiBase = useMemo(() => apiBaseUrl(), []);
  const [data, setData] = useState<ApiState>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [endpointErrors, setEndpointErrors] = useState<string[]>([]);
  const [updateAccountId, setUpdateAccountId] = useState<string | null>(null);
  const [toast, setToast] = useState('');
  const [activeTab, setActiveTab] = useState<TabId>({ kind: 'overview' });

  const loadApi = useCallback(async () => {
    setLoading(true);
    setError('');
    setEndpointErrors([]);
    const endpoints = ['health', 'accounts', 'posts', 'patterns', 'dashboard'] as const;
    const prefix = apiPrefix(apiBase);
    const next: ApiState = {};
    const failures: string[] = [];
    let anyOk = false;

    await Promise.all(
      endpoints.map(async (name) => {
        const url = `${prefix}/${name}`;
        try {
          const res = await fetch(url);
          if (!res.ok) {
            failures.push(`${name}: HTTP ${res.status}`);
            return;
          }
          const body: unknown = await res.json();
          anyOk = true;
          next[name] = body;
        } catch (err) {
          const detail =
            err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
          failures.push(`${name}: ${detail}`);
        }
      })
    );

    setData(next);
    setEndpointErrors(failures);
    if (!anyOk) {
      setError(
        'Could not load any API data. Is the backend running on port 8000? ' +
          'Start it from `SocialMediaAutonomousAgents/backend`, then restart `npm start` in `frontend`.'
      );
    }
    setLoading(false);
  }, [apiBase]);

  useEffect(() => {
    loadApi();
  }, [loadApi]);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const t = window.setTimeout(() => setToast(''), 3800);
    return () => window.clearTimeout(t);
  }, [toast]);

  const activeAccounts = readActiveAccountCount(data.dashboard);
  const accounts = useMemo(() => parseAccounts(data.accounts), [data.accounts]);
  const navItems = useMemo(() => buildNavItems(accounts), [accounts]);

  useEffect(() => {
    if (activeTab.kind !== 'account') {
      return;
    }
    const exists = accounts.some((a) => a.account_id === activeTab.accountId);
    if (!exists) {
      setActiveTab({ kind: 'overview' });
    }
  }, [accounts, activeTab]);

  const handleAccountSaved = useCallback(() => {
    setUpdateAccountId(null);
    setToast('Updated Account Successfully');
    void loadApi();
  }, [loadApi]);

  const panelContext = useMemo(
    () => ({
      activeAccounts,
      accounts,
      apiData: data,
      onOpenAccount: setActiveTab,
      onUpdateClick: setUpdateAccountId,
    }),
    [activeAccounts, accounts, data]
  );

  const mainTitle =
    activeTab.kind === 'overview'
      ? 'Overview'
      : `Account · ${activeTab.accountId}`;

  return (
    <div className="App">
      {toast ? (
        <div className="toast" role="status">
          {toast}
        </div>
      ) : null}

      {updateAccountId ? (
        <UpdateAccountModal
          apiBase={apiBase}
          accountId={updateAccountId}
          onClose={() => setUpdateAccountId(null)}
          onSaved={handleAccountSaved}
        />
      ) : null}

      <div className="app-shell">
        <Sidebar items={navItems} activeTab={activeTab} onSelect={setActiveTab} />

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

          {loading ? <p className="App-loading">Loading API data…</p> : null}
          {error ? <p className="error">{error}</p> : null}
          {!loading && endpointErrors.length > 0 && !error ? (
            <div className="App-warn" role="status">
              <p className="App-warn-title">Some endpoints failed (others may still load):</p>
              <ul className="App-warn-list">
                {endpointErrors.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {!loading ? renderPanel(activeTab, panelContext) : null}
        </main>
      </div>
    </div>
  );
}

export default App;
