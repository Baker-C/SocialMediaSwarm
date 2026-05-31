import React, { useEffect, useMemo, useState } from 'react';
import { apiPrefix, parseHttpError } from '../lib/api';
import { formatShortDate } from '../lib/format';
import type { AccountEditPayload } from '../types';

const SECRET_PLACEHOLDER = 'Leave blank to keep stored credentials unchanged';

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

        {!payload && !loadError ? <p className="modal-loading">Loading account…</p> : null}

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
