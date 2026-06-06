import type { ReactNode } from 'react';
import type { TabId } from '../navigation/tabs';
import { tabKey } from '../navigation/tabs';
import type { AccountSummary, ApiState } from '../types';
import { AccountPanel } from './AccountPanel';
import { OverviewPanel } from './OverviewPanel';

export type PanelContext = {
  apiBase: string;
  activeAccounts: number | null;
  accounts: AccountSummary[];
  apiData: ApiState;
  onOpenAccount: (tab: TabId) => void;
  onUpdateClick: (accountId: string) => void;
  onForcePostComplete?: () => void;
};

/** Map each TabId kind to its panel. Add new tab kinds here. */
export function renderPanel(tab: TabId, ctx: PanelContext): ReactNode {
  const panelId = `panel-${tabKey(tab)}`;

  switch (tab.kind) {
    case 'overview':
      return (
        <div
          key={panelId}
          id={panelId}
          role="tabpanel"
          aria-labelledby="tab-overview"
          className="main-panel__content"
        >
          <OverviewPanel
            apiBase={ctx.apiBase}
            activeAccounts={ctx.activeAccounts}
            accounts={ctx.accounts}
            apiData={ctx.apiData}
            onOpenAccount={ctx.onOpenAccount}
            onForcePostComplete={ctx.onForcePostComplete}
          />
        </div>
      );
    case 'account': {
      const account = ctx.accounts.find((a) => a.account_id === tab.accountId);
      if (!account) {
        return (
          <div key={panelId} id={panelId} role="tabpanel" className="main-panel__content">
            <p className="accounts-section__empty">Account not found.</p>
          </div>
        );
      }
      const tabControlId = `tab-account:${tab.accountId}`;
      return (
        <div
          key={panelId}
          id={panelId}
          role="tabpanel"
          aria-labelledby={tabControlId}
          className="main-panel__content"
        >
          <AccountPanel account={account} onUpdateClick={ctx.onUpdateClick} />
        </div>
      );
    }
    default: {
      const _exhaustive: never = tab;
      return _exhaustive;
    }
  }
}
