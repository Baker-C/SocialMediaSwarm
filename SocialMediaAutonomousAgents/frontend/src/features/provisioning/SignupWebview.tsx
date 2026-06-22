import { useEffect, useRef, useState } from 'react';
import { apiBaseUrl, apiPrefix } from '../../api/client';
import { authHeaders } from '../../api/auth';
import { Button } from '../../components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../../components/ui/card';
import { ErrorBanner } from '../../components/layout/ErrorBanner';

// X signup flow entry point.
const SIGNUP_URL = 'https://x.com/i/flow/signup';

// Detect the Electron host (the desktop/ shell). In a plain browser this is
// undefined, so the component renders the fallback note instead of a <webview>.
export function isElectron(): boolean {
  if (typeof window === 'undefined') return false;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any;
  // Primary: flag from the desktop host preload (reliable under contextIsolation).
  // Fallback: window.process (only present when contextIsolation is off).
  return Boolean(w.xprovDesktop === true || w.process?.versions?.electron);
}

// Minimal typing for the Electron <webview> element we use.
interface WebviewElement extends HTMLElement {
  src: string;
  loadURL?: (url: string) => Promise<void>;
}

/**
 * Electron-only embedded X-signup webview.
 *
 * - Renders <webview partition="persist:acct_<id>"> so each account signs up in
 *   its OWN isolated session (cookies/localStorage walled off from every other
 *   account and from the operator's normal browser).
 * - The desktop main process injects the autofill preload onto the webview, which
 *   fills the fields from the backend. The operator clicks Next + solves CAPTCHA.
 * - "Continue → connect" fetches the OAuth authorize URL for THIS account and
 *   navigates the SAME webview to it, so consent runs in the same partition and
 *   the token binds to this account (the structural fix for cross-account posting).
 */
export function SignupWebview({ accountId }: { accountId: string }) {
  const webviewRef = useRef<WebviewElement | null>(null);
  const [status, setStatus] = useState('loading signup…');
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const partition = `persist:acct_${accountId}`;
  // The preload reads the account id from the URL hash (#xprov=<id>).
  const signupUrl = `${SIGNUP_URL}#xprov=${encodeURIComponent(accountId)}`;

  useEffect(() => {
    const el = webviewRef.current;
    if (!el) return;
    const onStart = () => setStatus('navigating…');
    const onStop = () => setStatus('autofill watching for fields…');
    const onFail = () => setStatus('page failed to load (X may have gated the webview)');
    el.addEventListener('did-start-loading', onStart);
    el.addEventListener('did-stop-loading', onStop);
    el.addEventListener('did-fail-load', onFail);
    return () => {
      el.removeEventListener('did-start-loading', onStart);
      el.removeEventListener('did-stop-loading', onStop);
      el.removeEventListener('did-fail-load', onFail);
    };
  }, []);

  const connect = async () => {
    setError(null);
    setConnecting(true);
    try {
      // Fetch this account's authorize URL from the backend (signed PKCE state).
      const prefix = apiPrefix(apiBaseUrl());
      const res = await fetch(
        `${prefix}/oauth/x/authorize?account_id=${encodeURIComponent(accountId)}`,
        { headers: { ...authHeaders() } },
      );
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} fetching authorize URL`);
      }
      const data = (await res.json()) as { authorization_url?: string };
      const url = data.authorization_url;
      if (!url) throw new Error('backend returned no authorization_url');

      // Navigate the SAME partition/webview to consent → token binds to THIS account.
      const el = webviewRef.current;
      if (!el) throw new Error('webview not ready');
      if (el.loadURL) {
        await el.loadURL(url);
      } else {
        el.src = url;
      }
      setStatus('on OAuth consent — approve to connect this account');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnecting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Sign up {accountId}</CardTitle>
        <CardDescription>
          Isolated session <code>{partition}</code>. Fields autofill from the
          backend — you only click Next and solve the CAPTCHA.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-xs tracking-wider text-neutral-400">STATUS: {status}</div>

        {/* The Electron <webview> tag. Typed as `any` for JSX since it is not a
            standard DOM element; see global.d.ts augmentation. */}
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {(() => {
          const Webview = 'webview' as unknown as React.FC<
            React.HTMLAttributes<HTMLElement> & {
              src: string;
              partition: string;
              preload?: string;
              ref?: React.Ref<WebviewElement>;
              allowpopups?: string;
            }
          >;
          return (
            <Webview
              ref={webviewRef}
              src={signupUrl}
              partition={partition}
              // Main overrides this with the trusted absolute path, but the
              // attribute must be present for the webview to attach a preload.
              preload="autofill-preload.js"
              allowpopups="true"
              style={{ width: '100%', height: '640px', border: '1px solid #333', borderRadius: 6 }}
            />
          );
        })()}

        {error ? <ErrorBanner message={error} /> : null}

        <div className="flex items-center gap-2">
          <Button onClick={() => void connect()} disabled={connecting}>
            {connecting ? 'Connecting…' : 'Continue → connect this account'}
          </Button>
          <span className="text-xs text-neutral-500">
            Click after the signup completes to bind OAuth to this account.
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Non-Electron fallback: a small note pointing the operator at the browser
 * extension flow. Keeps the web dashboard working unchanged.
 */
export function SignupWebviewFallback() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Embedded signup unavailable</CardTitle>
        <CardDescription>This view requires the desktop (Electron) app.</CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-foreground space-y-2">
        <p>
          You are using the web dashboard. The embedded autofill webview only runs
          in the desktop shell (<code>desktop/</code>). To provision here, use the
          standalone browser extension (<code>provisioning-extension/</code>) in
          real Chrome, or launch the desktop app and reopen this page.
        </p>
      </CardContent>
    </Card>
  );
}
