import type { AccountSummary, ApiState } from '../types';
import type { TabId } from '../navigation/tabs';

type OverviewPanelProps = {
  activeAccounts: number | null;
  accounts: AccountSummary[];
  apiData: ApiState;
  onOpenAccount: (tab: TabId) => void;
};

export function OverviewPanel({
  activeAccounts,
  accounts,
  apiData,
  onOpenAccount,
}: OverviewPanelProps) {
  return (
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
          <article className="bento-tile bento-tile--stat">
            <span className="bento-tile-kicker">Fleet</span>
            <h2 className="bento-tile-title">Registered accounts</h2>
            <p className="bento-tile-value" aria-live="polite">
              {accounts.length}
            </p>
            <p className="bento-tile-caption">All accounts returned from the API.</p>
          </article>
        </div>
      </section>

      <section className="accounts-section" aria-label="Registered accounts">
        <h2 className="accounts-section__title">Accounts</h2>
        {accounts.length === 0 ? (
          <p className="accounts-section__empty">No accounts returned from the API.</p>
        ) : (
          <ul className="overview-account-list">
            {accounts.map((a) => (
              <li key={a.account_id} className="overview-account-list__item">
                <div className="overview-account-list__main">
                  <span className="overview-account-list__id">{a.account_id}</span>
                  <span className="overview-account-list__niche">{a.niche}</span>
                  <span
                    className={`overview-account-list__status overview-account-list__status--${a.status}`}
                  >
                    {a.status}
                  </span>
                </div>
                <button
                  type="button"
                  className="overview-account-list__open"
                  onClick={() => onOpenAccount({ kind: 'account', accountId: a.account_id })}
                >
                  Open
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <details className="App-debug">
        <summary>Raw API responses</summary>
        <pre>{JSON.stringify(apiData, null, 2)}</pre>
      </details>
    </>
  );
}
