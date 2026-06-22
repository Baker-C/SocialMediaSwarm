import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../../components/ui/card';
import { isElectron } from '../provisioning/SignupWebview';

/**
 * Per-account embedded X session shown in the account HQ.
 *
 * Each account renders a <webview> bound to its OWN persist:acct_<id> partition,
 * so it always shows THAT account's logged-in X (cookies/session isolated from
 * every other account and from the operator's browser). A fresh instance loads
 * whenever the HQ page for an account is visited.
 *
 * Electron-only (the <webview> tag); in the plain web dashboard it shows a note.
 * Main attaches the autofill preload only to signup webviews, so this one is a
 * clean, view-only session.
 */
export function AccountWebview({ accountId }: { accountId: string }) {
  const partition = `persist:acct_${accountId}`;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">X session — {accountId}</CardTitle>
        <CardDescription>
          Live X for this account, isolated session <code>{partition}</code>.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isElectron() ? (
          (() => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const Webview = 'webview' as unknown as React.FC<
              React.HTMLAttributes<HTMLElement> & {
                src: string;
                partition: string;
                allowpopups?: string;
              }
            >;
            return (
              <Webview
                src="https://x.com/home"
                partition={partition}
                allowpopups="true"
                style={{ width: '100%', height: '720px', border: '1px solid #333', borderRadius: 6 }}
              />
            );
          })()
        ) : (
          <p className="text-sm text-neutral-400">
            Open the desktop app to view this account&apos;s X session here.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
