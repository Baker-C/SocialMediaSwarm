import type { OAuthAuthorizeResponse, OAuthStatus } from '../../types';
import { apiPrefix, parseHttpError } from '../client';

export async function fetchOAuthAuthorizeUrl(
  apiBase: string,
  accountId: string
): Promise<OAuthAuthorizeResponse> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(
    `${prefix}/oauth/x/authorize?account_id=${encodeURIComponent(accountId)}`
  );
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  return (await res.json()) as OAuthAuthorizeResponse;
}

export async function fetchOAuthStatus(apiBase: string, accountId: string): Promise<OAuthStatus> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/oauth/x/status/${encodeURIComponent(accountId)}`);
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  return (await res.json()) as OAuthStatus;
}

export async function disconnectOAuth(apiBase: string, accountId: string): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/oauth/x/disconnect/${encodeURIComponent(accountId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
}
