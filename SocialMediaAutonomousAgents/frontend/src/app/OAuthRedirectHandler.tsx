import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppContext } from './AppContext';

export function OAuthRedirectHandler() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setToast, openUpdateModal } = useAppContext();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get('oauth_error')?.trim();
    if (oauthError) {
      setToast(`X connection failed: ${oauthError}`);
      const accountId = params.get('account_id')?.trim();
      if (accountId) {
        navigate(`/accounts/${accountId}/settings`, { replace: true });
        openUpdateModal(accountId);
      }
      const url = new URL(window.location.href);
      url.search = '';
      window.history.replaceState({}, '', url.pathname);
      return;
    }
    if (params.get('connected') !== '1') {
      return;
    }
    const accountId = params.get('account_id')?.trim();
    if (accountId) {
      const xUsername = params.get('x_username')?.trim().replace(/^@/, '');
      const unverified = params.get('unverified') === '1';
      if (unverified) {
        setToast(`Connected X for ${accountId} (identity unverified)`);
      } else if (xUsername) {
        setToast(`Connected as @${xUsername} for ${accountId}`);
      } else {
        setToast(`Connected X for ${accountId}`);
      }
      navigate(`/accounts/${accountId}/settings`, { replace: true });
      void queryClient.invalidateQueries({ queryKey: ['accounts'] });
      void queryClient.invalidateQueries({ queryKey: ['oauthStatus', accountId] });
    }
    const url = new URL(window.location.href);
    url.search = '';
    window.history.replaceState({}, '', url.pathname);
  }, [navigate, openUpdateModal, queryClient, setToast]);

  return null;
}
