import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  apiPrefix,
  parseHttpError,
} from '../api/client';
import {
  disconnectOAuth,
  fetchOAuthAuthorizeUrl,
  fetchOAuthStatus,
} from '../api/endpoints/oauth';
import { formatShortDate } from '../lib/format';
import type { AccountEditPayload } from '../types';

type UpdateModalProps = {
  apiBase: string;
  accountId: string;
  onClose: () => void;
  onSaved: () => void;
};

export function UpdateAccountModal({ apiBase, accountId, onClose, onSaved }: UpdateModalProps) {
  const prefix = useMemo(() => apiPrefix(apiBase), [apiBase]);
  const [loadError, setLoadError] = useState('');
  const [payload, setPayload] = useState<AccountEditPayload | null>(null);
  const [niche, setNiche] = useState('');
  const [twitterHandle, setTwitterHandle] = useState('');
  const [status, setStatus] = useState('active');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [followers, setFollowers] = useState(0);
  const [postsTotal, setPostsTotal] = useState(0);
  const [oauthConnected, setOauthConnected] = useState(false);
  const [oauthExpiresAt, setOauthExpiresAt] = useState<string | null>(null);
  const [oauthRedirectUri, setOauthRedirectUri] = useState('');
  const [oauthBusy, setOauthBusy] = useState(false);
  const [oauthError, setOauthError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  const refreshOAuthStatus = useCallback(async () => {
    try {
      const oauth = await fetchOAuthStatus(apiBase, accountId);
      setOauthConnected(oauth.connected);
      setOauthExpiresAt(oauth.expires_at ?? null);
      setOauthError('');
    } catch (err) {
      const detail =
        err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
      setOauthError(detail);
    }
  }, [apiBase, accountId]);

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
        setOauthConnected(Boolean(data.oauth_connected));
        setOauthExpiresAt(data.oauth_expires_at ?? null);
        setSaveError('');
        setOauthError('');
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
        if (!cancelled) {
          setLoadError(detail);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [accountId, prefix]);

  const handleConnectX = async () => {
    setOauthError('');
    setOauthBusy(true);
    try {
      const result = await fetchOAuthAuthorizeUrl(apiBase, accountId);
      if (result.redirect_uri) {
        setOauthRedirectUri(result.redirect_uri);
      }
      window.open(result.authorization_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      const detail =
        err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
      setOauthError(detail);
    } finally {
      setOauthBusy(false);
    }
  };

  const handleDisconnectX = async () => {
    setOauthError('');
    setOauthBusy(true);
    try {
      await disconnectOAuth(apiBase, accountId);
      setOauthConnected(false);
      setOauthExpiresAt(null);
      await refreshOAuthStatus();
    } catch (err) {
      const detail =
        err instanceof Error ? err.message : typeof err === 'string' ? err : 'Unknown error';
      setOauthError(detail);
    } finally {
      setOauthBusy(false);
    }
  };

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
        followers,
        posts_total: postsTotal,
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

        {!payload && !loadError ? <p className="modal-loading">Loading account…</p> : null}

        {payload ? (
          <form className="modal-form" onSubmit={handleSubmit}>
            <p className="modal-meta">
              Account id <strong>{payload.account_id}</strong>
            </p>

            <fieldset className="modal-fieldset">
              <legend>X connection</legend>
              <p className="modal-hint">
                Connect opens X in a new tab. After you authorize, return here and close/reopen
                this dialog to refresh connection status (or reload the dashboard).
              </p>
              <p className="modal-hint modal-hint--checklist">
                In X Developer Portal → <strong>User authentication settings → Edit</strong>:
              </p>
              <ul className="modal-hint-list">
                <li>
                  Callback URI:{' '}
                  <code>{oauthRedirectUri || 'http://localhost:8000/api/oauth/x/callback'}</code>
                </li>
                <li>
                  Website URL (https://, TLD, <strong>no port</strong>):{' '}
                  <code>https://example.com</code>
                </li>
              </ul>
              <p className="modal-hint">
                If you stay on the X authorize page after login, the callback URL is usually missing
                or mismatched in User authentication settings. Log into x.com in a normal tab first,
                disable ad-blockers for x.com, then try Connect again.
              </p>
              <p className="modal-oauth-status">
                Status:{' '}
                <strong className={oauthConnected ? 'modal-oauth-status--ok' : 'modal-oauth-status--warn'}>
                  {oauthConnected ? 'Connected' : 'Not connected'}
                </strong>
                {oauthExpiresAt ? (
                  <>
                    {' '}
                    · access expires {formatShortDate(oauthExpiresAt)}
                  </>
                ) : null}
              </p>
              <div className="modal-oauth-actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void handleConnectX()}
                  disabled={oauthBusy || saving}
                >
                  {oauthBusy ? 'Working…' : oauthConnected ? 'Reconnect X' : 'Connect with X'}
                </button>
                {oauthConnected ? (
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => void handleDisconnectX()}
                    disabled={oauthBusy || saving}
                  >
                    Disconnect
                  </button>
                ) : null}
              </div>
              {oauthError ? (
                <p className="modal-error" role="alert">
                  {oauthError}
                </p>
              ) : null}
            </fieldset>

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

            <p className="modal-readonly">
              Registered: {formatShortDate(payload.registered_at ?? undefined)} · Last slot:{' '}
              {payload.last_interval_slot ?? '—'}
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
