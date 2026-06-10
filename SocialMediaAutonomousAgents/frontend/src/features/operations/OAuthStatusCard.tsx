import { useCallback } from 'react';
import {
  disconnectOAuth,
  fetchOAuthAuthorizeUrl,
} from '../../api/endpoints/oauth';
import type { OAuthStatus } from '../../types';
import { formatShortDate } from '../../lib/format';
import { useQueryClient } from '@tanstack/react-query';
import { useAppContext } from '../../app/AppContext';

type OAuthStatusCardProps = {
  accountId: string;
  status: OAuthStatus | undefined;
  loading: boolean;
  hasCredentials: boolean;
};

export function OAuthStatusCard({
  accountId,
  status,
  loading,
  hasCredentials,
}: OAuthStatusCardProps) {
  const queryClient = useQueryClient();
  const { apiBase } = useAppContext();

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['oauthStatus', accountId] });
    void queryClient.invalidateQueries({ queryKey: ['accounts'] });
  }, [queryClient, accountId]);

  const handleConnect = async () => {
    const { authorization_url } = await fetchOAuthAuthorizeUrl(apiBase, accountId);
    window.location.href = authorization_url;
  };

  const handleDisconnect = async () => {
    await disconnectOAuth(apiBase, accountId);
    refresh();
  };

  const connected = status?.connected ?? hasCredentials;

  return (
    <div className="oauth-card">
      <h3 className="oauth-card__title">X OAuth</h3>
      {loading ? (
        <p className="oauth-card__status">Checking connection…</p>
      ) : connected ? (
        <>
          <p className="oauth-card__status oauth-card__status--ok">Connected</p>
          {status?.expires_at ? (
            <p className="oauth-card__meta">Expires {formatShortDate(status.expires_at)}</p>
          ) : null}
          <button type="button" className="btn btn--ghost" onClick={() => void handleDisconnect()}>
            Disconnect
          </button>
        </>
      ) : (
        <>
          <p className="oauth-card__status oauth-card__status--warn">Not connected</p>
          <button type="button" className="btn btn--primary" onClick={() => void handleConnect()}>
            Connect with X
          </button>
        </>
      )}
    </div>
  );
}
