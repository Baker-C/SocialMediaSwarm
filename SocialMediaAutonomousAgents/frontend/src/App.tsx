import React, { useCallback, useEffect, useMemo, useState } from 'react';
import './App.css';

type RecentPost = {
  snippet?: string;
  posted_at?: string | null;
  post_id?: string | null;
  views?: number | null;
};

type AccountSummary = {
  account_id: string;
  niche: string;
  twitter_handle: string;
  status: string;
  followers: number;
  posts_total: number;
  has_credentials?: boolean;
  registered_at?: string | null;
  follower_growth_vs_registered?: number | null;
  last_post_slot?: string | null;
  recent_post?: RecentPost | null;
};

type AccountEditPayload = {
  account_id: string;
  niche: string;
  twitter_handle: string;
  status: string;
  system_prompt: string;
  buffer_organization_id: string;
  buffer_channel_id: string;
  followers: number;
  posts_total: number;
  registered_at?: string | null;
  last_post_slot?: string | null;
  last_post_id?: string | null;
  credential_mode: string;
};

type ApiState = {
  health?: unknown;
  accounts?: unknown;
  posts?: unknown;
  patterns?: unknown;
  dashboard?: unknown;
};

type DashboardPayload = {
  active_accounts?: number;
  top_niche?: string;
  avg_engagement?: number;
};

const SECRET_PLACEHOLDER = 'Leave blank to keep stored credentials unchanged';

function apiBaseUrl(): string {
  const fromEnv = process.env.REACT_APP_API_URL?.trim();
  if (fromEnv) {
    return fromEnv.replace(/\/$/, '');
  }
  if (process.env.NODE_ENV === 'development') {
    return '';
  }
  return '';
}

function apiPrefix(apiBase: string): string {
  return apiBase ? `${apiBase}/api` : '/api';
}

function readActiveAccountCount(dashboard: unknown): number | null {
  if (!dashboard || typeof dashboard !== 'object') {
    return null;
  }
  const d = dashboard as DashboardPayload;
  if (typeof d.active_accounts !== 'number' || Number.isNaN(d.active_accounts)) {
    return null;
  }
  return d.active_accounts;
}

function parseAccounts(raw: unknown): AccountSummary[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((row): row is AccountSummary => {
    if (!row || typeof row !== 'object') {
      return false;
    }
    const r = row as Record<string, unknown>;
    return typeof r.account_id === 'string';
  }) as AccountSummary[];
}

function formatAge(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return '—';
  }
  const ms = Date.now() - t;
  const days = Math.floor(ms / 86400000);
  if (days >= 30) {
    return `${Math.floor(days / 30)}mo`;
  }
  if (days >= 1) {
    return `${days}d`;
  }
  const hours = Math.floor(ms / 3600000);
  if (hours >= 1) {
    return `${hours}h`;
  }
  const mins = Math.floor(ms / 60000);
  return `${Math.max(0, mins)}m`;
}

function formatShortDate(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return '—';
  }
  return new Date(t).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatGrowth(n: number | null | undefined): string {
  if (n === null || n === undefined) {
    return 'Not tracked yet';
  }
  if (n === 0) {
    return '±0 vs baseline';
  }
  const sign = n > 0 ? '+' : '';
  return `${sign}${n} vs baseline`;
}

async function parseHttpError(res: Response): Promise<string> {
  const text = await res.text();
  let detail: unknown;
  try {
    detail = JSON.parse(text).detail;
  } catch {
    return `${res.status} ${res.statusText}${text ? `: ${text}` : ''}`;
  }
  if (typeof detail === 'string') {
    return `${res.status}: ${detail}`;
  }
  if (Array.isArray(detail)) {
    return `${res.status}: ${detail.map((d) => JSON.stringify(d)).join('; ')}`;
  }
  if (detail && typeof detail === 'object') {
    return `${res.status}: ${JSON.stringify(detail)}`;
  }
  return `${res.status} ${res.statusText}`;
}

type UpdateModalProps = {
  apiBase: string;
  accountId: string;
  onClose: () => void;
  onSaved: () => void;
};

function UpdateAccountModal({ apiBase, accountId, onClose, onSaved }: UpdateModalProps) {
  const prefix = useMemo(() => apiPrefix(apiBase), [apiBase]);
  const [loadError, setLoadError] = useState('');
  const [payload, setPayload] = useState<AccountEditPayload | null>(null);
  const [niche, setNiche] = useState('');
  const [twitterHandle, setTwitterHandle] = useState('');
  const [status, setStatus] = useState('active');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [followers, setFollowers] = useState(0);
  const [postsTotal, setPostsTotal] = useState(0);
  const [bufferOrg, setBufferOrg] = useState('');
  const [bufferChannel, setBufferChannel] = useState('');
  const [twitterApiKey, setTwitterApiKey] = useState('');
  const [twitterApiSecret, setTwitterApiSecret] = useState('');
  const [twitterAccessToken, setTwitterAccessToken] = useState('');
  const [twitterAccessTokenSecret, setTwitterAccessTokenSecret] = useState('');
  const [twitterOauth2Access, setTwitterOauth2Access] = useState('');
  const [twitterOauth2Refresh, setTwitterOauth2Refresh] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoadError('');
      try {
        const res = await fetch(`${prefix}/accounts/${encodeURIComponent(accountId)}/edit`);
        if (!res.ok) {
          const msg = await parseHttpError(res);
          if (!cancelled) {
            setLoadError(msg);
          }
          return;
        }
        const data = (await res.json()) as AccountEditPayload;
        if (cancelled) {
          return;
        }
        setPayload(data);
        setNiche(data.niche ?? '');
        setTwitterHandle(data.twitter_handle ?? '');
        setStatus(data.status || 'active');
        setSystemPrompt(data.system_prompt ?? '');
        setFollowers(typeof data.followers === 'number' ? data.followers : 0);
        setPostsTotal(typeof data.posts_total === 'number' ? data.posts_total : 0);
        setBufferOrg(data.buffer_organization_id ?? '');
        setBufferChannel(data.buffer_channel_id ?? '');
        setTwitterApiKey('');
        setTwitterApiSecret('');
        setTwitterAccessToken('');
        setTwitterAccessTokenSecret('');
        setTwitterOauth2Access('');
        setTwitterOauth2Refresh('');
        setSaveError('');
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
        if (!cancelled) {
          setLoadError(detail);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [accountId, prefix]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError('');
    setSaving(true);
    try {
      const body = {
        niche,
        twitter_handle: twitterHandle,
        status,
        system_prompt: systemPrompt,
        buffer_organization_id: bufferOrg,
        buffer_channel_id: bufferChannel,
        followers,
        posts_total: postsTotal,
        twitter_api_key: twitterApiKey,
        twitter_api_secret: twitterApiSecret,
        twitter_access_token: twitterAccessToken,
        twitter_access_token_secret: twitterAccessTokenSecret,
        twitter_oauth2_access_token: twitterOauth2Access,
        twitter_oauth2_refresh_token: twitterOauth2Refresh,
      };
      const res = await fetch(`${prefix}/accounts/${encodeURIComponent(accountId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const msg = await parseHttpError(res);
        setSaveError(msg);
        return;
      }
      onSaved();
    } catch (err) {
      const detail =
        err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
      setSaveError(detail);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-root" role="presentation">
      <button type="button" className="modal-backdrop" aria-label="Close dialog" onClick={onClose} />
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-account-title"
      >
        <header className="modal-head">
          <h2 id="update-account-title">Update account</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {loadError ? (
          <p className="modal-error" role="alert">
            {loadError}
          </p>
        ) : null}

        {!payload && !loadError ? (
          <p className="modal-loading">Loading account…</p>
        ) : null}

        {payload ? (
          <form className="modal-form" onSubmit={handleSubmit}>
            <p className="modal-meta">
              Account id <strong>{payload.account_id}</strong>
              {payload.credential_mode ? (
                <>
                  {' '}
                  · credentials: <code>{payload.credential_mode}</code>
                </>
              ) : null}
            </p>

            <label className="modal-field">
              <span>Niche</span>
              <input value={niche} onChange={(ev) => setNiche(ev.target.value)} autoComplete="off" />
            </label>

            <label className="modal-field">
              <span>Twitter handle</span>
              <input
                value={twitterHandle}
                onChange={(ev) => setTwitterHandle(ev.target.value)}
                placeholder="@handle or handle"
                autoComplete="off"
              />
            </label>

            <label className="modal-field">
              <span>Status</span>
              <select value={status} onChange={(ev) => setStatus(ev.target.value)}>
                <option value="active">active</option>
                <option value="inactive">inactive</option>
              </select>
            </label>

            <label className="modal-field modal-field--tall">
              <span>System prompt</span>
              <textarea
                value={systemPrompt}
                onChange={(ev) => setSystemPrompt(ev.target.value)}
                rows={5}
                spellCheck={false}
              />
            </label>

            <div className="modal-row2">
              <label className="modal-field">
                <span>Followers</span>
                <input
                  type="number"
                  min={0}
                  value={followers}
                  onChange={(ev) => setFollowers(Number(ev.target.value) || 0)}
                />
              </label>
              <label className="modal-field">
                <span>Posts (total)</span>
                <input
                  type="number"
                  min={0}
                  value={postsTotal}
                  onChange={(ev) => setPostsTotal(Number(ev.target.value) || 0)}
                />
              </label>
            </div>

            <label className="modal-field">
              <span>Buffer organization id (optional)</span>
              <input
                value={bufferOrg}
                onChange={(ev) => setBufferOrg(ev.target.value)}
                placeholder="Optional"
                autoComplete="off"
              />
            </label>

            <label className="modal-field">
              <span>Buffer channel id (optional)</span>
              <input
                value={bufferChannel}
                onChange={(ev) => setBufferChannel(ev.target.value)}
                placeholder="Optional"
                autoComplete="off"
              />
            </label>

            <fieldset className="modal-fieldset">
              <legend>OAuth 1.0a (X API key + user token)</legend>
              <p className="modal-hint">
                Stored keys are never shown. Use these fields only to replace all four values at once.
              </p>
              <label className="modal-field">
                <span>API key (consumer key)</span>
                <input
                  type="password"
                  value={twitterApiKey}
                  onChange={(ev) => setTwitterApiKey(ev.target.value)}
                  placeholder={SECRET_PLACEHOLDER}
                  autoComplete="off"
                />
              </label>
              <label className="modal-field">
                <span>API secret (consumer secret)</span>
                <input
                  type="password"
                  value={twitterApiSecret}
                  onChange={(ev) => setTwitterApiSecret(ev.target.value)}
                  placeholder={SECRET_PLACEHOLDER}
                  autoComplete="off"
                />
              </label>
              <label className="modal-field">
                <span>Access token</span>
                <input
                  type="password"
                  value={twitterAccessToken}
                  onChange={(ev) => setTwitterAccessToken(ev.target.value)}
                  placeholder={SECRET_PLACEHOLDER}
                  autoComplete="off"
                />
              </label>
              <label className="modal-field">
                <span>Access token secret</span>
                <input
                  type="password"
                  value={twitterAccessTokenSecret}
                  onChange={(ev) => setTwitterAccessTokenSecret(ev.target.value)}
                  placeholder={SECRET_PLACEHOLDER}
                  autoComplete="off"
                />
              </label>
            </fieldset>

            <fieldset className="modal-fieldset">
              <legend>OAuth 2.0 user (Bearer access)</legend>
              <p className="modal-hint">
                If you paste a new user access token here, OAuth 1.0a fields on the account are cleared.
                Leave both blank to keep the current OAuth2 tokens.
              </p>
              <label className="modal-field">
                <span>OAuth2 access token</span>
                <input
                  type="password"
                  value={twitterOauth2Access}
                  onChange={(ev) => setTwitterOauth2Access(ev.target.value)}
                  placeholder={SECRET_PLACEHOLDER}
                  autoComplete="off"
                />
              </label>
              <label className="modal-field">
                <span>OAuth2 refresh token (optional)</span>
                <input
                  type="password"
                  value={twitterOauth2Refresh}
                  onChange={(ev) => setTwitterOauth2Refresh(ev.target.value)}
                  placeholder={SECRET_PLACEHOLDER}
                  autoComplete="off"
                />
              </label>
            </fieldset>

            <p className="modal-readonly">
              Registered: {formatShortDate(payload.registered_at ?? undefined)} · Last slot:{' '}
              {payload.last_post_slot ?? '—'}
              {payload.last_post_id ? ` · Last post id ${payload.last_post_id}` : ''}
            </p>

            {saveError ? (
              <p className="modal-error" role="alert">
                {saveError}
              </p>
            ) : null}

            <div className="modal-actions">
              <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>
                Cancel
              </button>
              <button type="submit" className="btn btn--primary" disabled={saving || !!loadError}>
                {saving ? 'Saving…' : 'Save and close'}
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </div>
  );
}

type AccountCardProps = {
  account: AccountSummary;
  onUpdateClick: (accountId: string) => void;
};

function AccountCard({ account, onUpdateClick }: AccountCardProps) {
  const handle = account.twitter_handle?.trim();
  const growth = formatGrowth(account.follower_growth_vs_registered);
  const recent = account.recent_post;
  const viewsLabel =
    recent?.views !== null && recent?.views !== undefined ? String(recent.views) : '—';

  return (
    <article className="account-card" aria-labelledby={`acct-${account.account_id}-title`}>
      <header className="account-card__head">
        <div>
          <h2 className="account-card__title" id={`acct-${account.account_id}-title`}>
            {account.account_id}
          </h2>
          <p className="account-card__niche">{account.niche}</p>
        </div>
        <span className={`account-card__status account-card__status--${account.status}`}>
          {account.status}
        </span>
      </header>

      <p className="account-card__growth" title="Change in follower count since registration baseline">
        <span className="account-card__growth-label">Growth</span>
        <span className="account-card__growth-value">{growth}</span>
      </p>

      <section className="account-card__recap" aria-label="Most recent post">
        <h3 className="account-card__recap-title">Latest post</h3>
        {recent?.snippet ? (
          <>
            <p className="account-card__recap-text">{recent.snippet}</p>
            <p className="account-card__recap-meta">
              {formatShortDate(recent.posted_at ?? undefined)}
              {recent.post_id ? (
                <span className="account-card__recap-id"> · id {recent.post_id}</span>
              ) : null}
            </p>
            <p className="account-card__recap-views">
              Views (last post): <strong>{viewsLabel}</strong>
            </p>
          </>
        ) : (
          <p className="account-card__recap-empty">No posts recorded yet for this account.</p>
        )}
      </section>

      <dl className="account-card__stats">
        <div className="account-card__stat">
          <dt>Followers</dt>
          <dd>{account.followers}</dd>
        </div>
        <div className="account-card__stat">
          <dt>Posts (total)</dt>
          <dd>{account.posts_total}</dd>
        </div>
        <div className="account-card__stat">
          <dt>Time on platform</dt>
          <dd>{formatAge(account.registered_at)}</dd>
        </div>
        <div className="account-card__stat">
          <dt>Registered</dt>
          <dd>{formatShortDate(account.registered_at ?? undefined)}</dd>
        </div>
        <div className="account-card__stat account-card__stat--wide">
          <dt>Last hourly slot</dt>
          <dd>{account.last_post_slot ?? '—'}</dd>
        </div>
        {handle ? (
          <div className="account-card__stat account-card__stat--wide">
            <dt>Handle</dt>
            <dd>{handle}</dd>
          </div>
        ) : null}
        {account.has_credentials === false ? (
          <div className="account-card__stat account-card__stat--wide">
            <dt>Credentials</dt>
            <dd className="account-card__warn">Incomplete</dd>
          </div>
        ) : null}
      </dl>

      <div className="account-card__actions">
        <button
          type="button"
          className="account-card__btn"
          onClick={() => onUpdateClick(account.account_id)}
        >
          Update account
        </button>
      </div>
    </article>
  );
}

function App() {
  const apiBase = useMemo(() => apiBaseUrl(), []);
  const [data, setData] = useState<ApiState>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [endpointErrors, setEndpointErrors] = useState<string[]>([]);
  const [updateAccountId, setUpdateAccountId] = useState<string | null>(null);
  const [toast, setToast] = useState('');

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

  const handleAccountSaved = useCallback(() => {
    setUpdateAccountId(null);
    setToast('Updated Account Successfully');
    void loadApi();
  }, [loadApi]);

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

      <main className="App-main">
        <h1>Social Media Autonomous Agents</h1>
        <p className="App-meta">
          API: {apiBase || '(dev proxy → http://127.0.0.1:8000)'}
        </p>
        {process.env.NODE_ENV === 'development' ? (
          <p className="App-meta-hint">
            Open <strong>http://localhost:3000/</strong> (path <code>/</code> only). If you open{' '}
            <code>/api/health</code> or another <code>/api/…</code> URL in the address bar, the dev
            server proxies that path and the browser shows raw JSON instead of this dashboard.
          </p>
        ) : null}
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
        {!loading ? (
          <>
            <section className="bento" aria-label="Dashboard overview">
              <div className="bento-grid">
                <article className="bento-tile bento-tile--stat">
                  <span className="bento-tile-kicker">Database</span>
                  <h2 className="bento-tile-title">Active accounts</h2>
                  <p className="bento-tile-value" aria-live="polite">
                    {activeAccounts === null ? '—' : activeAccounts}
                  </p>
                  <p className="bento-tile-caption">
                    Accounts with <code>status = active</code> in RavenDB.
                  </p>
                </article>
              </div>
            </section>

            <section className="accounts-section" aria-label="Registered accounts">
              <h2 className="accounts-section__title">Accounts</h2>
              {accounts.length === 0 ? (
                <p className="accounts-section__empty">No accounts returned from the API.</p>
              ) : (
                <div className="account-cards">
                  {accounts.map((a) => (
                    <AccountCard key={a.account_id} account={a} onUpdateClick={setUpdateAccountId} />
                  ))}
                </div>
              )}
            </section>

            <details className="App-debug">
              <summary>Raw API responses</summary>
              <pre>{JSON.stringify(data, null, 2)}</pre>
            </details>
          </>
        ) : null}
      </main>
    </div>
  );
}

export default App;
